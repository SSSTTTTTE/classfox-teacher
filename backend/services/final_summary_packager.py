"""
最终总结输入打包器
==================
把 session 内的知识树、窗口摘要、有效问题与关键原文片段整理成
Gemma4 最终总结可消费的统一输入包。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from services.question_event_service import VALID_QUESTION_STATUSES, question_event_service
from services.session_storage_service import session_storage_service
from services.transcript_service import TranscriptService


class FinalSummaryPackager:
    """生成并保存 final_summary_input_package.json。"""

    def __init__(self) -> None:
        self._transcript_service = TranscriptService()

    def _session_meta(self) -> dict[str, Any]:
        meta = session_storage_service.get_active_session_meta()
        if meta:
            return meta
        transcript_meta = self._transcript_service.get_transcript_metadata()
        return {
            "session_id": session_storage_service.get_active_session_id(),
            "course_name": transcript_meta.get("course_name", ""),
            "subject": transcript_meta.get("subject", ""),
            "material_name": transcript_meta.get("material_name", ""),
        }

    def _session_summaries_dir(self) -> str:
        return session_storage_service.ensure_session_subdir("summaries")

    def _package_path(self) -> str:
        summaries_dir = self._session_summaries_dir()
        return os.path.join(summaries_dir, "final_summary_input_package.json") if summaries_dir else ""

    def _tree_path(self) -> str:
        return session_storage_service.get_session_path("knowledge_tree", "current_tree.json")

    def _windows_dir(self) -> str:
        return session_storage_service.get_session_path("windows")

    def _collapse_text(self, text: str, *, char_limit: int = 220) -> str:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        if len(cleaned) <= char_limit:
            return cleaned
        return f"{cleaned[:char_limit].rstrip()}…"

    def _load_json(self, path: str, *, default: Any) -> Any:
        if not path or not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except Exception:
            return default
        return payload

    def _load_knowledge_tree_snapshot(self) -> dict[str, Any]:
        payload = self._load_json(self._tree_path(), default={})
        return payload if isinstance(payload, dict) else {}

    def _load_windows(self) -> list[dict[str, Any]]:
        windows_dir = self._windows_dir()
        if not windows_dir or not os.path.exists(windows_dir):
            return []

        rows: list[dict[str, Any]] = []
        for filename in sorted(os.listdir(windows_dir)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(windows_dir, filename)
            payload = self._load_json(path, default={})
            if isinstance(payload, dict):
                rows.append(payload)
        rows.sort(key=lambda item: (str(item.get("start_time") or ""), str(item.get("window_id") or "")))
        return rows

    def _build_window_summaries(self, windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for window in windows:
            summaries.append(
                {
                    "window_id": window.get("window_id", ""),
                    "start_time": window.get("start_time", ""),
                    "end_time": window.get("end_time", ""),
                    "main_topic": window.get("main_topic", ""),
                    "stage_summary": window.get("stage_summary", ""),
                    "subtopics": window.get("extracted_subtopics", []),
                    "concepts": window.get("extracted_concepts", []),
                    "facts": window.get("facts", []),
                    "linked_question_ids": window.get("linked_question_ids", []),
                }
            )
        return summaries

    def _build_valid_questions(self) -> list[dict[str, Any]]:
        records = question_event_service.list_question_records()
        valid_records = [record for record in records if record.get("status") in VALID_QUESTION_STATUSES]
        return [
            {
                "question_id": record.get("question_id", ""),
                "question_text": record.get("question_text", ""),
                "raw_text": record.get("raw_text", ""),
                "trigger_time": record.get("trigger_time", ""),
                "answered_at": record.get("answered_at", ""),
                "confirmed_at": record.get("confirmed_at", ""),
                "status": record.get("status", ""),
                "question_type": record.get("question_type", ""),
                "confidence": record.get("confidence", ""),
                "teacher_speakable_answer": record.get("teacher_speakable_answer", ""),
                "one_sentence_answer": record.get("one_sentence_answer", ""),
                "linked_topic_id": record.get("linked_topic_id", ""),
                "linked_topic_title": record.get("linked_topic_title", ""),
                "window_id": record.get("window_id", ""),
            }
            for record in valid_records
        ]

    def _build_question_links(self, valid_questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "question_id": item.get("question_id", ""),
                "question_text": item.get("question_text", ""),
                "status": item.get("status", ""),
                "linked_topic_id": item.get("linked_topic_id", ""),
                "linked_topic_title": item.get("linked_topic_title", ""),
                "window_id": item.get("window_id", ""),
            }
            for item in valid_questions
        ]

    def _build_topic_timeline(self, windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        topic_timeline: list[dict[str, Any]] = []
        previous_topic = ""
        for window in windows:
            main_topic = str(window.get("main_topic") or "").strip()
            if not main_topic:
                continue
            if topic_timeline and main_topic == previous_topic:
                topic_timeline[-1]["window_ids"].append(window.get("window_id", ""))
                topic_timeline[-1]["end_time"] = window.get("end_time", "")
                continue
            topic_timeline.append(
                {
                    "main_topic": main_topic,
                    "window_ids": [window.get("window_id", "")],
                    "start_time": window.get("start_time", ""),
                    "end_time": window.get("end_time", ""),
                    "stage_summary": window.get("stage_summary", ""),
                }
            )
            previous_topic = main_topic
        return topic_timeline

    def _build_key_raw_contexts(
        self,
        windows: list[dict[str, Any]],
        topic_timeline: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        context_window_ids: list[str] = []
        for item in topic_timeline[:4]:
            for window_id in item.get("window_ids", []):
                if window_id and window_id not in context_window_ids:
                    context_window_ids.append(window_id)
                    break
        for window in windows:
            if window.get("linked_question_ids"):
                window_id = str(window.get("window_id") or "")
                if window_id and window_id not in context_window_ids:
                    context_window_ids.append(window_id)
        selected_window_ids = set(context_window_ids[:6])

        contexts: list[dict[str, Any]] = []
        for window in windows:
            window_id = str(window.get("window_id") or "")
            if window_id not in selected_window_ids:
                continue
            focus = str(window.get("main_topic") or "").strip() or "课堂片段"
            if window.get("linked_question_ids"):
                focus = f"{focus} / 学生提问"
            contexts.append(
                {
                    "window_id": window_id,
                    "start_time": window.get("start_time", ""),
                    "end_time": window.get("end_time", ""),
                    "focus": focus,
                    "raw_excerpt": self._collapse_text(str(window.get("raw_text") or ""), char_limit=260),
                }
            )
        return contexts

    def create_package(self) -> dict[str, Any]:
        session_meta = self._session_meta()
        windows = self._load_windows()
        knowledge_tree_snapshot = self._load_knowledge_tree_snapshot()
        window_summaries = self._build_window_summaries(windows)
        valid_questions = self._build_valid_questions()
        question_links = self._build_question_links(valid_questions)
        topic_timeline = self._build_topic_timeline(windows)
        key_raw_contexts = self._build_key_raw_contexts(windows, topic_timeline)

        payload = {
            "session_id": session_meta.get("session_id", ""),
            "course_name": session_meta.get("course_name", ""),
            "subject": session_meta.get("subject", ""),
            "material_name": session_meta.get("material_name", ""),
            "knowledge_tree_snapshot": knowledge_tree_snapshot,
            "window_summaries": window_summaries,
            "valid_questions": valid_questions,
            "question_links": question_links,
            "topic_timeline": topic_timeline,
            "key_raw_contexts": key_raw_contexts,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

        package_path = self._package_path()
        if package_path:
            os.makedirs(os.path.dirname(package_path), exist_ok=True)
            with open(package_path, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, ensure_ascii=False, indent=2)

        return payload


final_summary_packager = FinalSummaryPackager()
