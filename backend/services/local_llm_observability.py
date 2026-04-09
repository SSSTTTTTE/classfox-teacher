"""
本地推理可观测性服务
====================
统一记录 Ollama 推理事件，并输出课堂场景评估指标快照。
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
from datetime import datetime
from statistics import mean, pstdev
from typing import Any

from config import DATA_DIR
from services.session_storage_service import session_storage_service

logger = logging.getLogger(__name__)


class LocalLLMObservability:
    """维护本地推理事件日志和聚合评估指标。"""

    AI_SELF_PATTERNS = (
        "作为ai",
        "作为 ai",
        "人工智能",
        "语言模型",
        "根据题目描述",
        "根据上下文",
        "以下是",
        "总的来说",
        "首先",
        "其次",
    )
    CAUTION_MARKERS = (
        "信息不足",
        "还不够完整",
        "先按现有信息",
        "先按现有内容",
        "大概率",
        "可能是",
        "先这样讲",
        "暂时只能",
        "缺少题干",
        "缺少条件",
        "需要更多条件",
    )

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events_path = os.path.join(DATA_DIR, "debug", "local_llm_events.jsonl")
        self._snapshot_path = os.path.join(DATA_DIR, "debug", "local_llm_metrics_snapshot.json")
        self._events: list[dict[str, Any]] = []
        self._load_events()

    def _load_events(self) -> None:
        if not os.path.exists(self._events_path):
            return

        loaded: list[dict[str, Any]] = []
        try:
            with open(self._events_path, "r", encoding="utf-8") as file_obj:
                for line in file_obj:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        loaded.append(payload)
        except Exception:
            logger.exception("读取本地推理日志失败")
            return

        with self._lock:
            self._events = loaded

    def record_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = dict(payload)
        event.setdefault("event_type", "generation")
        event.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
        event["task"] = str(event.get("task", "")).strip()
        event["model"] = str(event.get("model", "")).strip()
        event["subject"] = str(event.get("subject", "")).strip()
        event["question_type"] = str(event.get("question_type", "")).strip()
        event["primary_output"] = self._trim_preview(event.get("primary_output", ""))
        event["question_preview"] = self._trim_preview(event.get("question_preview", ""))
        event["error"] = self._trim_preview(event.get("error", ""), limit=240)

        with self._lock:
            self._events.append(event)
            self._append_event_locked(event)
            self._persist_snapshot_locked()

        compact = {
            "task": event.get("task"),
            "model": event.get("model"),
            "success": event.get("success"),
            "skipped": event.get("skipped"),
            "total_duration_ms": event.get("total_duration_ms"),
            "subject": event.get("subject"),
            "question_type": event.get("question_type"),
        }
        logger.info("local_llm_event %s", json.dumps(compact, ensure_ascii=False))
        return event

    def _append_event_locked(self, event: dict[str, Any]) -> None:
        try:
            with open(self._events_path, "a", encoding="utf-8") as file_obj:
                file_obj.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("写入本地推理日志失败")

        session_debug_path = session_storage_service.get_session_path("debug", "local_llm_events.jsonl")
        if not session_debug_path:
            return
        try:
            os.makedirs(os.path.dirname(session_debug_path), exist_ok=True)
            with open(session_debug_path, "a", encoding="utf-8") as file_obj:
                file_obj.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("写入 session 级本地推理日志失败")

    def _persist_snapshot_locked(self) -> None:
        try:
            snapshot = self._build_snapshot_locked(recent_limit=20)
            with open(self._snapshot_path, "w", encoding="utf-8") as file_obj:
                json.dump(snapshot, file_obj, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("写入本地推理指标快照失败")

    def _trim_preview(self, text: Any, *, limit: int = 160) -> str:
        cleaned = " ".join(str(text or "").strip().split())
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit].rstrip()}…"

    def _sentence_count(self, text: str) -> int:
        stripped = str(text or "").strip()
        if not stripped:
            return 0
        hits = re.findall(r"[。！？!?；;]", stripped)
        return len(hits) or 1

    def _has_ai_self_reference(self, text: str) -> bool:
        lowered = str(text or "").lower()
        return any(marker in lowered for marker in self.AI_SELF_PATTERNS)

    def _has_caution_trace(self, text: str) -> bool:
        cleaned = str(text or "")
        return any(marker in cleaned for marker in self.CAUTION_MARKERS)

    def _is_teacher_speakable(self, text: str) -> bool:
        cleaned = str(text or "").strip()
        if not cleaned:
            return False
        if len(cleaned) > 72:
            return False
        if self._sentence_count(cleaned) > 3:
            return False
        if self._has_ai_self_reference(cleaned):
            return False
        if any(token in cleaned for token in ("```", "#", "* ", "1.", "2.")):
            return False
        return True

    def _naturalness_score(self, text: str) -> float:
        cleaned = str(text or "").strip()
        if not cleaned:
            return 0.0

        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", cleaned))
        latin_chars = len(re.findall(r"[A-Za-z]", cleaned))
        punct_chars = len(re.findall(r"[，。！？；：“”‘’、]", cleaned))
        total_visible = max(chinese_chars + latin_chars + punct_chars, 1)
        chinese_ratio = chinese_chars / total_visible
        punct_ratio = min(punct_chars / max(len(cleaned), 1) * 20, 1.0)
        score = 0.55 * chinese_ratio + 0.2 * punct_ratio + 0.25

        if self._has_ai_self_reference(cleaned):
            score -= 0.35
        if len(cleaned) > 120:
            score -= 0.15
        if any(token in cleaned for token in ("```", "#", "* ", "1.", "2.")):
            score -= 0.2

        return round(max(0.0, min(score, 1.0)), 3)

    def _normalize_overlap_tokens(self, text: str) -> set[str]:
        cleaned = re.sub(r"\s+", "", str(text or "").lower())
        tokens = set(re.findall(r"[\u4e00-\u9fff]{1,4}|[a-z0-9]{2,12}", cleaned))
        return {token for token in tokens if len(token) >= 2}

    def _is_off_topic(self, question: str, answer: str, *, cautious: bool) -> bool:
        question_tokens = self._normalize_overlap_tokens(question)
        answer_tokens = self._normalize_overlap_tokens(answer)
        if not question_tokens or not answer_tokens:
            return False

        overlap = len(question_tokens & answer_tokens)
        overlap_ratio = overlap / max(len(question_tokens), 1)
        if overlap_ratio >= 0.15:
            return False
        if cautious and self._has_caution_trace(answer):
            return False
        return True

    def _length_stability_score(self, lengths: list[float]) -> float:
        if len(lengths) <= 1:
            return 1.0 if lengths else 0.0
        avg = mean(lengths)
        if avg <= 0:
            return 0.0
        cv = pstdev(lengths) / avg
        return round(max(0.0, 1 - min(cv, 1.0)), 3)

    def _metric_summary(self, values: list[float]) -> dict[str, float]:
        if not values:
            return {"avg": 0.0, "min": 0.0, "max": 0.0}
        return {
            "avg": round(mean(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
        }

    def _build_snapshot_locked(self, *, recent_limit: int) -> dict[str, Any]:
        events = list(self._events)
        generation_events = [event for event in events if event.get("event_type") == "generation"]
        success_events = [event for event in generation_events if event.get("success")]
        task_counts: dict[str, int] = {}
        for event in generation_events:
            task = str(event.get("task", "")).strip() or "unknown"
            task_counts[task] = task_counts.get(task, 0) + 1

        fallback_events = [
            event for event in success_events if event.get("task") == "fallback_answer"
        ]
        interactive_events = [
            event
            for event in success_events
            if event.get("task") in {"fallback_answer", "followup_answer", "status_answer"}
        ]
        total_durations = [
            float(event.get("total_duration_ms", 0) or 0)
            for event in success_events
            if event.get("total_duration_ms") is not None
        ]
        first_answer_latencies = [
            float(event.get("first_answer_ms", 0) or 0)
            for event in fallback_events
            if event.get("first_answer_ms") is not None
        ]
        output_lengths = [
            float(event.get("output_chars", 0) or 0)
            for event in interactive_events
            if event.get("output_chars") is not None
        ]
        naturalness_scores = [
            self._naturalness_score(str(event.get("primary_output", "")))
            for event in interactive_events
            if str(event.get("primary_output", "")).strip()
        ]
        speakable_values = [
            1.0 if self._is_teacher_speakable(str(event.get("primary_output", ""))) else 0.0
            for event in interactive_events
            if str(event.get("primary_output", "")).strip()
        ]
        off_topic_values = [
            1.0
            if self._is_off_topic(
                str(event.get("question_preview", "")),
                str(event.get("primary_output", "")),
                cautious=str(event.get("answer_mode", "")) == "cautious",
            )
            else 0.0
            for event in interactive_events
            if str(event.get("question_preview", "")).strip() and str(event.get("primary_output", "")).strip()
        ]
        insufficient_info_events = [
            event
            for event in interactive_events
            if event.get("question_type") == "信息不足型"
            or event.get("confidence") == "low"
            or event.get("answer_mode") == "cautious"
        ]
        insufficient_info_misanswers = [
            event
            for event in insufficient_info_events
            if event.get("answer_mode") == "direct"
            or event.get("confidence") == "high"
            or not self._has_caution_trace(str(event.get("primary_output", "")))
        ]

        recent_events = events[-recent_limit:]
        recent_events.reverse()

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "log_path": self._events_path,
            "snapshot_path": self._snapshot_path,
            "total_events": len(events),
            "generation_events": len(generation_events),
            "success_count": len(success_events),
            "failure_count": len(
                [event for event in generation_events if not event.get("success") and not event.get("skipped")]
            ),
            "skipped_count": len([event for event in generation_events if event.get("skipped")]),
            "task_counts": task_counts,
            "metrics": {
                "first_answer_latency_ms": self._metric_summary(first_answer_latencies),
                "average_response_duration_ms": self._metric_summary(total_durations),
                "output_length_chars": self._metric_summary(output_lengths),
                "length_stability_score": self._length_stability_score(output_lengths),
                "chinese_naturalness_score": round(mean(naturalness_scores), 3) if naturalness_scores else 0.0,
                "teacher_speakable_rate": round(mean(speakable_values), 3) if speakable_values else 0.0,
                "off_topic_rate": round(mean(off_topic_values), 3) if off_topic_values else 0.0,
                "insufficient_info_misanswer_rate": round(
                    len(insufficient_info_misanswers) / len(insufficient_info_events),
                    3,
                )
                if insufficient_info_events
                else 0.0,
            },
            "definitions": {
                "length_stability_score": "按互动回答输出长度的变异系数折算，越接近 1 越稳定。",
                "chinese_naturalness_score": "基于中文占比、标点完整度和 AI 套话惩罚的启发式得分。",
                "teacher_speakable_rate": "回答长度、句数和课堂口语化约束同时达标的比例。",
                "off_topic_rate": "问题与回答关键词重合度很低且不属于谨慎兜底的比例。",
                "insufficient_info_misanswer_rate": "信息不足型问题里仍然高置信直答或缺少谨慎提示的比例。",
            },
            "recent_events": recent_events,
        }

    def get_snapshot(self, *, recent_limit: int = 20) -> dict[str, Any]:
        with self._lock:
            return self._build_snapshot_locked(recent_limit=recent_limit)


local_llm_observability = LocalLLMObservability()
