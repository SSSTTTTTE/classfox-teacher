"""
结构化课堂状态服务
==================
把课堂上下文收口为可裁剪的结构化状态，供问答、总结和 HUD 共用。
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from typing import Any, Iterable

from config import DATA_DIR
from services.session_storage_service import session_storage_service


class ClassroomStateService:
    """维护结构化课堂状态，并持久化到 data 目录。"""

    MAX_RECENT_TRANSCRIPT_LINES = int(os.getenv("CLASSROOM_STATE_MAX_TRANSCRIPT_LINES", "14"))
    MAX_RECENT_QUESTIONS = int(os.getenv("CLASSROOM_STATE_MAX_RECENT_QUESTIONS", "6"))
    MAX_RECENT_ANSWERS = int(os.getenv("CLASSROOM_STATE_MAX_RECENT_ANSWERS", "6"))
    MAX_CONFUSION_POINTS = int(os.getenv("CLASSROOM_STATE_MAX_CONFUSION_POINTS", "6"))
    MAX_TOPIC_SUMMARY_CHARS = int(os.getenv("CLASSROOM_STATE_MAX_TOPIC_SUMMARY_CHARS", "240"))
    MAX_MATERIAL_CHARS = int(os.getenv("CLASSROOM_STATE_MAX_MATERIAL_CHARS", "420"))
    MAX_TEXT_CHARS = int(os.getenv("CLASSROOM_STATE_MAX_TEXT_CHARS", "120"))
    MAX_TOTAL_CONTEXT_CHARS = int(os.getenv("CLASSROOM_STATE_MAX_TOTAL_CONTEXT_CHARS", "1500"))
    MAX_SUMMARY_CARDS = int(os.getenv("CLASSROOM_STATE_MAX_SUMMARY_CARDS", "3"))
    MAX_SUMMARY_POINTS = int(os.getenv("CLASSROOM_STATE_MAX_SUMMARY_POINTS", "3"))
    RESET_RECOMMENDATION_RATIO = float(os.getenv("CLASSROOM_STATE_RESET_RECOMMENDATION_RATIO", "0.85"))

    def __init__(self) -> None:
        self._path = os.path.join(DATA_DIR, "classroom_state.json")
        self._lock = threading.RLock()
        self._state = self._default_state()
        self._load_from_disk()

    def _primary_path(self) -> str:
        return session_storage_service.get_session_path("classroom_state.json") or self._path

    def _default_state(self) -> dict[str, Any]:
        return {
            "subject": "",
            "course_name": "",
            "current_topic": "",
            "topic_summary": "",
            "summary_cards": [],
            "recent_questions": [],
            "recent_answers": [],
            "student_confusion_points": [],
            "current_material": "",
            "material_name": "",
            "recent_transcript_window": [],
            "question_type": "",
            "llm_ready": False,
        }

    def _load_from_disk(self) -> None:
        primary_path = self._primary_path()
        if not os.path.exists(primary_path):
            return

        try:
            with open(primary_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except Exception:
            return

        if not isinstance(payload, dict):
            return

        self._state.update({key: payload.get(key, value) for key, value in self._default_state().items()})

    def _persist_locked(self) -> None:
        primary_path = self._primary_path()
        try:
            os.makedirs(os.path.dirname(primary_path), exist_ok=True)
            with open(primary_path, "w", encoding="utf-8") as file_obj:
                json.dump(self._state, file_obj, ensure_ascii=False, indent=2)
            if primary_path != self._path:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as file_obj:
                    json.dump(self._state, file_obj, ensure_ascii=False, indent=2)
        except Exception:
            # 状态文件只是辅助快照，写失败不应阻断主链路。
            pass

    def _context_char_count_locked(self) -> int:
        total = 0
        total += len(str(self._state.get("current_topic", "")))
        total += len(str(self._state.get("topic_summary", "")))
        for card in self._state.get("summary_cards", []):
            if not isinstance(card, dict):
                continue
            total += len(str(card.get("section_title", "")))
            for point in card.get("points", []) or []:
                total += len(str(point))
        total += len(str(self._state.get("current_material", "")))
        total += len(str(self._state.get("material_name", "")))
        total += len(str(self._state.get("question_type", "")))

        for item in self._state.get("recent_questions", []):
            total += len(str(item.get("question", ""))) if isinstance(item, dict) else len(str(item))
        for item in self._state.get("recent_answers", []):
            total += len(str(item.get("answer", ""))) if isinstance(item, dict) else len(str(item))
        for item in self._state.get("student_confusion_points", []):
            total += len(str(item))
        for item in self._state.get("recent_transcript_window", []):
            if isinstance(item, dict):
                total += len(str(item.get("text", "")))
        return total

    def _apply_context_limits_locked(self) -> None:
        self._state["current_topic"] = self._trim_text(self._state.get("current_topic", ""), 60)
        self._state["topic_summary"] = self._trim_text(
            self._state.get("topic_summary", ""),
            self.MAX_TOPIC_SUMMARY_CHARS,
        )
        self._state["summary_cards"] = self._normalize_summary_cards(self._state.get("summary_cards", []))
        self._state["current_material"] = self._trim_text(
            self._state.get("current_material", ""),
            self.MAX_MATERIAL_CHARS,
        )
        self._state["material_name"] = self._trim_text(self._state.get("material_name", ""), 80)
        self._state["question_type"] = self._trim_text(self._state.get("question_type", ""), 20)

        self._state["recent_questions"] = list(self._state.get("recent_questions", []))[-self.MAX_RECENT_QUESTIONS:]
        self._state["recent_answers"] = list(self._state.get("recent_answers", []))[-self.MAX_RECENT_ANSWERS:]
        self._state["student_confusion_points"] = self._dedupe_strings(
            self._state.get("student_confusion_points", []),
            limit=self.MAX_CONFUSION_POINTS,
        )
        self._state["recent_transcript_window"] = list(self._state.get("recent_transcript_window", []))[
            -self.MAX_RECENT_TRANSCRIPT_LINES:
        ]

        while self._context_char_count_locked() > self.MAX_TOTAL_CONTEXT_CHARS:
            if len(self._state["recent_transcript_window"]) > 4:
                self._state["recent_transcript_window"] = self._state["recent_transcript_window"][1:]
                continue
            if len(self._state["recent_questions"]) > 2:
                self._state["recent_questions"] = self._state["recent_questions"][1:]
                continue
            if len(self._state["recent_answers"]) > 2:
                self._state["recent_answers"] = self._state["recent_answers"][1:]
                continue
            if len(self._state["student_confusion_points"]) > 2:
                self._state["student_confusion_points"] = self._state["student_confusion_points"][1:]
                continue
            current_material = str(self._state.get("current_material", ""))
            if len(current_material) > 220:
                self._state["current_material"] = self._trim_text(current_material, max(220, len(current_material) - 80))
                continue
            topic_summary = str(self._state.get("topic_summary", ""))
            if len(topic_summary) > 160:
                self._state["topic_summary"] = self._trim_text(topic_summary, max(160, len(topic_summary) - 40))
                continue
            break

    def _trim_text(self, text: str, limit: int) -> str:
        cleaned = " ".join((text or "").strip().split())
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit].rstrip()}…"

    def _normalize_summary_cards(self, cards: Iterable[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for card in cards or []:
            if not isinstance(card, dict):
                continue
            title = self._trim_text(card.get("section_title", ""), 40)
            points = [
                self._trim_text(item, self.MAX_TEXT_CHARS)
                for item in (card.get("points", []) or [])
                if isinstance(item, str) and item.strip()
            ][: self.MAX_SUMMARY_POINTS]
            if not title and not points:
                continue
            normalized.append({"section_title": title, "points": points})
            if len(normalized) >= self.MAX_SUMMARY_CARDS:
                break
        return normalized

    def _append_bounded(self, items: list[Any], value: Any, *, limit: int) -> list[Any]:
        items.append(value)
        if len(items) > limit:
            del items[:-limit]
        return items

    def _dedupe_strings(self, values: Iterable[str], *, limit: int) -> list[str]:
        seen: list[str] = []
        for value in values:
            cleaned = self._trim_text(value, self.MAX_TEXT_CHARS)
            if not cleaned or cleaned in seen:
                continue
            seen.append(cleaned)
        return seen[-limit:]

    def reset_for_class(
        self,
        *,
        subject: str,
        course_name: str,
        material_name: str = "",
        material_excerpt: str = "",
        llm_ready: bool = False,
    ) -> None:
        with self._lock:
            self._state = self._default_state()
            self._state.update(
                {
                    "subject": self._trim_text(subject, 40),
                    "course_name": self._trim_text(course_name, 80),
                    "current_topic": self._trim_text(course_name, 60),
                    "current_material": self._trim_text(material_excerpt, self.MAX_MATERIAL_CHARS),
                    "material_name": self._trim_text(material_name, 80),
                    "llm_ready": llm_ready,
                }
            )
            self._apply_context_limits_locked()
            self._persist_locked()

    def reset_context_preserving_summary(self, *, llm_ready: bool = False) -> dict[str, Any]:
        with self._lock:
            preserved = {
                "subject": self._state.get("subject", ""),
                "course_name": self._state.get("course_name", ""),
                "current_topic": self._state.get("current_topic", ""),
                "topic_summary": self._state.get("topic_summary", ""),
                "summary_cards": self._state.get("summary_cards", []),
                "current_material": self._state.get("current_material", ""),
                "material_name": self._state.get("material_name", ""),
            }
            self._state = self._default_state()
            self._state.update(preserved)
            self._state["llm_ready"] = bool(llm_ready)
            self._apply_context_limits_locked()
            self._persist_locked()
            return self.get_context_status()

    def set_llm_ready(self, ready: bool) -> None:
        with self._lock:
            self._state["llm_ready"] = bool(ready)
            self._apply_context_limits_locked()
            self._persist_locked()

    def replace_latest_transcript_entry(self, timestamp: str, text: str) -> None:
        cleaned = self._trim_text(text, self.MAX_TEXT_CHARS)
        if not cleaned:
            return

        with self._lock:
            window = self._state["recent_transcript_window"]
            item = {"timestamp": timestamp, "text": cleaned}
            if window:
                window[-1] = item
            else:
                window.append(item)
            self._apply_context_limits_locked()
            self._persist_locked()

    def add_transcript_entry(self, timestamp: str, text: str) -> None:
        cleaned = self._trim_text(text, self.MAX_TEXT_CHARS)
        if not cleaned:
            return

        with self._lock:
            window = self._state["recent_transcript_window"]
            if window and window[-1].get("text") == cleaned:
                window[-1]["timestamp"] = timestamp
            else:
                self._append_bounded(
                    window,
                    {"timestamp": timestamp, "text": cleaned},
                    limit=self.MAX_RECENT_TRANSCRIPT_LINES,
                )
            self._apply_context_limits_locked()
            self._persist_locked()

    def update_summary(self, summary_text: str = "", cards: list[dict[str, Any]] | None = None) -> None:
        cards = cards or []
        current_topic = ""

        for card in reversed(cards):
            if not isinstance(card, dict):
                continue
            current_topic = (
                (card.get("section_title") or "").strip()
                or (card.get("flow_title") or "").strip()
            )
            if current_topic:
                break

        with self._lock:
            self._state["topic_summary"] = self._trim_text(summary_text, self.MAX_TOPIC_SUMMARY_CHARS)
            self._state["summary_cards"] = self._normalize_summary_cards(cards)
            if current_topic:
                self._state["current_topic"] = self._trim_text(current_topic, 60)
            self._apply_context_limits_locked()
            self._persist_locked()

    def record_interaction(
        self,
        *,
        student_question: str,
        teacher_answer: str,
        question_type: str = "",
        used_subject: str = "",
        confidence: str = "",
        answer_mode: str = "",
    ) -> None:
        question_text = self._trim_text(student_question, self.MAX_TEXT_CHARS)
        answer_text = self._trim_text(teacher_answer, self.MAX_TEXT_CHARS)
        if not question_text and not answer_text:
            return

        with self._lock:
            if used_subject:
                self._state["subject"] = self._trim_text(used_subject, 40)
            if question_type:
                self._state["question_type"] = self._trim_text(question_type, 20)

            if question_text:
                self._append_bounded(
                    self._state["recent_questions"],
                    {
                        "question": question_text,
                        "question_type": self._state["question_type"],
                    },
                    limit=self.MAX_RECENT_QUESTIONS,
                )

            if answer_text:
                self._append_bounded(
                    self._state["recent_answers"],
                    {
                        "answer": answer_text,
                        "answer_mode": self._trim_text(answer_mode, 20),
                    },
                    limit=self.MAX_RECENT_ANSWERS,
                )

            confusion_points = list(self._state["student_confusion_points"])
            if confidence == "low" or answer_mode == "cautious":
                marker = question_text or answer_text
                if marker:
                    confusion_points.append(marker)
            self._state["student_confusion_points"] = self._dedupe_strings(
                confusion_points,
                limit=self.MAX_CONFUSION_POINTS,
            )
            self._apply_context_limits_locked()
            self._persist_locked()

    def get_recent_transcript_text(self, *, max_lines: int = 8) -> str:
        with self._lock:
            window = self._state.get("recent_transcript_window", [])[-max_lines:]
            return "\n".join(
                f"[{item.get('timestamp', '--:--:--')}] {item.get('text', '').strip()}"
                for item in window
                if item.get("text")
            )

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)

    def get_context_status(self) -> dict[str, Any]:
        with self._lock:
            total_chars = self._context_char_count_locked()
            return {
                "subject": str(self._state.get("subject", "")),
                "course_name": str(self._state.get("course_name", "")),
                "question_type": str(self._state.get("question_type", "")),
                "llm_ready": bool(self._state.get("llm_ready")),
                "char_count": total_chars,
                "char_limit": self.MAX_TOTAL_CONTEXT_CHARS,
                "usage_ratio": round(total_chars / self.MAX_TOTAL_CONTEXT_CHARS, 3),
                "reset_recommended": total_chars >= int(self.MAX_TOTAL_CONTEXT_CHARS * self.RESET_RECOMMENDATION_RATIO),
                "recent_transcript_lines": len(self._state.get("recent_transcript_window", [])),
                "recent_questions": len(self._state.get("recent_questions", [])),
                "recent_answers": len(self._state.get("recent_answers", [])),
                "confusion_points": len(self._state.get("student_confusion_points", [])),
                "topic_summary_chars": len(str(self._state.get("topic_summary", ""))),
                "material_chars": len(str(self._state.get("current_material", ""))),
                "limits": {
                    "max_recent_transcript_lines": self.MAX_RECENT_TRANSCRIPT_LINES,
                    "max_recent_questions": self.MAX_RECENT_QUESTIONS,
                    "max_recent_answers": self.MAX_RECENT_ANSWERS,
                    "max_confusion_points": self.MAX_CONFUSION_POINTS,
                    "max_topic_summary_chars": self.MAX_TOPIC_SUMMARY_CHARS,
                    "max_material_chars": self.MAX_MATERIAL_CHARS,
                    "max_text_chars": self.MAX_TEXT_CHARS,
                },
            }


session_state_service = ClassroomStateService()
