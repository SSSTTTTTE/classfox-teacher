"""
问题事件服务
============
统一管理 detected -> answered -> confirmed_valid -> linked_to_tree 的问题状态机，
并维护兼容的时间轴镜像。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from services.knowledge_tree_service import knowledge_tree_service
from services.session_storage_service import session_storage_service


QUESTION_STATUS_ORDER = {
    "detected": 0,
    "answered": 1,
    "confirmed_valid": 2,
    "linked_to_tree": 3,
    "unresolved_link": 3,
}

QUESTION_STATUS_FOLDERS = (
    "detected",
    "answered",
    "confirmed_valid",
    "linked_to_tree",
    "unresolved_link",
)

VALID_QUESTION_STATUSES = {"confirmed_valid", "linked_to_tree", "unresolved_link"}


class QuestionEventService:
    """统一管理问题状态、问题轨迹与会话级持久化。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def _questions_dir(self) -> str:
        return session_storage_service.ensure_session_subdir("questions")

    def _status_dir(self, status: str) -> str:
        base_dir = self._questions_dir()
        return os.path.join(base_dir, status) if base_dir else ""

    def _index_path(self) -> str:
        base_dir = self._questions_dir()
        return os.path.join(base_dir, "question_index.json") if base_dir else ""

    def _timeline_path(self) -> str:
        return session_storage_service.get_session_path("timeline", "current_session.json")

    def _slugify(self, value: str) -> str:
        cleaned = re.sub(r"\s+", "_", (value or "").strip())
        cleaned = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff-]+", "_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
        return cleaned[:60] or "question"

    def _normalize_question(self, value: str) -> str:
        normalized = re.sub(r"\s+", "", (value or "").strip())
        normalized = re.sub(r"[？?]", "", normalized)
        return normalized

    def _status_rank(self, status: str) -> int:
        return QUESTION_STATUS_ORDER.get((status or "").strip(), -1)

    def _promote_status(self, current_status: str, target_status: str) -> str:
        return current_status if self._status_rank(current_status) > self._status_rank(target_status) else target_status

    def _load_index_locked(self) -> list[dict[str, Any]]:
        index_path = self._index_path()
        if not index_path or not os.path.exists(index_path):
            return []
        try:
            with open(index_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def _save_index_locked(self, rows: list[dict[str, Any]]) -> None:
        index_path = self._index_path()
        if not index_path:
            return
        rows.sort(
            key=lambda item: (
                str(item.get("trigger_time") or ""),
                str(item.get("answered_at") or ""),
                str(item.get("confirmed_at") or ""),
                str(item.get("question_id") or ""),
            )
        )
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        with open(index_path, "w", encoding="utf-8") as file_obj:
            json.dump(rows, file_obj, ensure_ascii=False, indent=2)

    def _write_record_locked(self, status: str, record: dict[str, Any]) -> str:
        status_dir = self._status_dir(status)
        if not status_dir:
            return ""
        os.makedirs(status_dir, exist_ok=True)
        path = os.path.join(status_dir, f"{record['question_id']}.json")
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(record, file_obj, ensure_ascii=False, indent=2)
        return path

    def _remove_stale_status_files_locked(self, question_id: str, keep_statuses: set[str]) -> None:
        base_dir = self._questions_dir()
        if not base_dir:
            return
        for folder in QUESTION_STATUS_FOLDERS:
            if folder in keep_statuses:
                continue
            path = os.path.join(base_dir, folder, f"{question_id}.json")
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _upsert_index_locked(self, record: dict[str, Any]) -> None:
        rows = self._load_index_locked()
        snapshot = {
            "question_id": record["question_id"],
            "status": record.get("status", ""),
            "raw_text": record.get("raw_text", ""),
            "question_text": record.get("question_text", ""),
            "normalized_question": record.get("normalized_question", ""),
            "trigger_time": record.get("trigger_time", ""),
            "detected_at": record.get("detected_at", ""),
            "answered_at": record.get("answered_at", ""),
            "confirmed_at": record.get("confirmed_at", ""),
            "linked_topic_id": record.get("linked_topic_id", ""),
            "linked_topic_title": record.get("linked_topic_title", ""),
            "answer_id": record.get("linked_answer_id", ""),
            "question_node_id": record.get("question_node_id", ""),
            "window_id": record.get("window_id", ""),
            "question_type": record.get("question_type", ""),
            "used_subject": record.get("used_subject", ""),
            "confidence": record.get("confidence", ""),
            "answer_mode": record.get("answer_mode", ""),
        }
        for index, row in enumerate(rows):
            if row.get("question_id") == record["question_id"]:
                rows[index] = snapshot
                self._save_index_locked(rows)
                return
        rows.append(snapshot)
        self._save_index_locked(rows)

    def _generate_question_id(self, trigger_time: str, question_text: str) -> str:
        now = datetime.now().astimezone()
        time_part = (trigger_time or now.strftime("%H:%M:%S")).replace(":", "")
        return f"q_{now.strftime('%Y%m%d')}_{time_part}_{now.strftime('%f')[:4]}_{self._slugify(question_text)[:18]}"

    def _generate_answer_id(self, trigger_time: str) -> str:
        now = datetime.now().astimezone()
        time_part = (trigger_time or now.strftime("%H:%M:%S")).replace(":", "")
        return f"answer_{now.strftime('%Y%m%d')}_{time_part}_{now.strftime('%f')[:4]}"

    def _find_related_window_id(self, trigger_time: str) -> str:
        windows_dir = session_storage_service.ensure_session_subdir("windows")
        if not windows_dir or not os.path.exists(windows_dir):
            return ""

        candidates: list[tuple[str, dict[str, Any]]] = []
        for filename in sorted(os.listdir(windows_dir)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(windows_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as file_obj:
                    payload = json.load(file_obj)
            except Exception:
                continue
            if isinstance(payload, dict):
                candidates.append((filename[:-5], payload))

        if not candidates:
            return ""

        if not trigger_time:
            return candidates[-1][0]

        for window_id, payload in candidates:
            start_time = str(payload.get("start_time") or "")
            end_time = str(payload.get("end_time") or "")
            if start_time and end_time and start_time <= trigger_time <= end_time:
                return window_id

        return candidates[-1][0]

    def _load_timeline_locked(self) -> list[dict[str, Any]]:
        timeline_path = self._timeline_path() or session_storage_service.get_legacy_timeline_path()
        os.makedirs(os.path.dirname(timeline_path), exist_ok=True)
        if not os.path.exists(timeline_path):
            return []
        try:
            with open(timeline_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def _save_timeline_locked(self, nodes: list[dict[str, Any]]) -> None:
        session_timeline_path = self._timeline_path()
        legacy_path = session_storage_service.get_legacy_timeline_path()
        for path in [p for p in [session_timeline_path, legacy_path] if p]:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as file_obj:
                json.dump(nodes, file_obj, ensure_ascii=False, indent=2)

    def _record_to_timeline_node(self, record: dict[str, Any]) -> dict[str, Any]:
        status = str(record.get("status") or "").strip()
        bookmarked = status in VALID_QUESTION_STATUSES
        return {
            "node_id": record["question_id"],
            "question_id": record["question_id"],
            "timestamp": record.get("trigger_time", ""),
            "text": record.get("raw_text", ""),
            "student_question": record.get("question_text", ""),
            "one_sentence_answer": record.get("one_sentence_answer", ""),
            "teacher_speakable_answer": record.get("teacher_speakable_answer", ""),
            "bookmarked": bookmarked,
            "expanded": bookmarked,
            "repeat_count": 1,
            "status": status,
            "question_status": status,
            "linked_topic_id": record.get("linked_topic_id", ""),
            "linked_topic_title": record.get("linked_topic_title", ""),
            "window_id": record.get("window_id", ""),
            "answer_id": record.get("linked_answer_id", ""),
            "question_node_id": record.get("question_node_id", ""),
            "confidence": record.get("confidence", ""),
            "question_type": record.get("question_type", ""),
            "created_at": (
                record.get("answered_at")
                or record.get("detected_at")
                or record.get("confirmed_at")
                or datetime.now().astimezone().isoformat(timespec="seconds")
            ),
        }

    def _upsert_timeline_locked(self, record: dict[str, Any]) -> None:
        nodes = self._load_timeline_locked()
        timeline_node = self._record_to_timeline_node(record)

        for index, node in enumerate(nodes):
            if node.get("node_id") == record["question_id"]:
                repeat_count = max(int(node.get("repeat_count", 1)), int(timeline_node["repeat_count"]))
                nodes[index] = {**node, **timeline_node, "repeat_count": repeat_count}
                self._save_timeline_locked(nodes)
                return

        nodes.append(timeline_node)
        nodes.sort(key=lambda item: (str(item.get("timestamp") or ""), str(item.get("created_at") or ""), str(item.get("node_id") or "")))
        self._save_timeline_locked(nodes)

    def _load_question_record_locked(self, question_id: str) -> Optional[dict[str, Any]]:
        base_dir = self._questions_dir()
        if not base_dir:
            return None
        for folder in QUESTION_STATUS_FOLDERS:
            path = os.path.join(base_dir, folder, f"{question_id}.json")
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as file_obj:
                    payload = json.load(file_obj)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _find_matching_record_locked(
        self,
        *,
        trigger_time: str,
        normalized_question: str,
        raw_text: str,
    ) -> Optional[dict[str, Any]]:
        rows = self._load_index_locked()
        raw_fallback = self._normalize_question(raw_text)
        for row in reversed(rows):
            row_trigger_time = str(row.get("trigger_time") or "")
            row_normalized = str(row.get("normalized_question") or "")
            if trigger_time and row_trigger_time != trigger_time:
                continue
            if normalized_question and row_normalized and row_normalized == normalized_question:
                return self._load_question_record_locked(str(row.get("question_id") or "")) or dict(row)
            if raw_fallback and row_normalized and row_normalized == raw_fallback:
                return self._load_question_record_locked(str(row.get("question_id") or "")) or dict(row)
        return None

    def _candidate_titles_for_question(self, window_id: str) -> list[str]:
        if not window_id:
            return []
        window_path = session_storage_service.get_session_path("windows", f"{window_id}.json")
        if not window_path or not os.path.exists(window_path):
            return []
        try:
            with open(window_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        titles: list[str] = []
        for key in ("extracted_topics", "extracted_subtopics", "extracted_concepts", "candidate_question_links"):
            for item in payload.get(key, []) or []:
                title = str(item).strip()
                if title and title not in titles:
                    titles.append(title)
        return titles

    def _append_question_to_window_locked(self, question_id: str, window_id: str) -> None:
        if not question_id or not window_id:
            return
        window_path = session_storage_service.get_session_path("windows", f"{window_id}.json")
        if not window_path or not os.path.exists(window_path):
            return
        try:
            with open(window_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        linked_question_ids = payload.setdefault("linked_question_ids", [])
        if question_id not in linked_question_ids:
            linked_question_ids.append(question_id)
            with open(window_path, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, ensure_ascii=False, indent=2)

    def record_detected_question(
        self,
        *,
        raw_text: str,
        trigger_time: str,
        confidence: str = "low",
    ) -> dict[str, Any]:
        normalized_question = self._normalize_question(raw_text)
        if not normalized_question:
            return {}

        now = datetime.now().astimezone().isoformat(timespec="seconds")
        window_id = self._find_related_window_id(trigger_time)

        with self._lock:
            existing = self._find_matching_record_locked(
                trigger_time=trigger_time,
                normalized_question=normalized_question,
                raw_text=raw_text,
            )
            if existing and self._status_rank(str(existing.get("status") or "")) >= self._status_rank("answered"):
                return deepcopy(existing)

            record = dict(existing or {})
            question_id = str(record.get("question_id") or self._generate_question_id(trigger_time, raw_text))
            record.update(
                {
                    "question_id": question_id,
                    "session_id": session_storage_service.get_active_session_id(),
                    "event_id": record.get("event_id") or f"question_detected_{trigger_time.replace(':', '') or datetime.now().strftime('%H%M%S')}",
                    "raw_text": (raw_text or record.get("raw_text") or "").strip(),
                    "question_text": (record.get("question_text") or raw_text).strip(),
                    "normalized_question": normalized_question,
                    "trigger_time": trigger_time,
                    "detected_at": record.get("detected_at") or now,
                    "answered_at": record.get("answered_at", ""),
                    "confirmed_at": record.get("confirmed_at", ""),
                    "confirmed_by_teacher_action": bool(record.get("confirmed_by_teacher_action", False)),
                    "linked_topic_id": record.get("linked_topic_id", ""),
                    "linked_topic_title": record.get("linked_topic_title", ""),
                    "linked_answer_id": record.get("linked_answer_id", ""),
                    "question_node_id": record.get("question_node_id", ""),
                    "status": self._promote_status(str(record.get("status") or ""), "detected"),
                    "window_id": record.get("window_id") or window_id,
                    "one_sentence_answer": record.get("one_sentence_answer", ""),
                    "teacher_speakable_answer": record.get("teacher_speakable_answer", ""),
                    "question_type": record.get("question_type", ""),
                    "used_subject": record.get("used_subject", ""),
                    "confidence": (confidence or record.get("confidence") or "low").strip(),
                    "answer_mode": record.get("answer_mode", ""),
                }
            )
            self._write_record_locked(str(record.get("status") or "detected"), record)
            self._remove_stale_status_files_locked(question_id, {str(record.get("status") or "detected")})
            self._upsert_index_locked(record)
            self._upsert_timeline_locked(record)
            return deepcopy(record)

    def record_answered_question(
        self,
        *,
        raw_text: str,
        question_text: str,
        one_sentence_answer: str,
        teacher_speakable_answer: str,
        trigger_time: str,
        question_type: str = "",
        used_subject: str = "",
        confidence: str = "",
        answer_mode: str = "",
    ) -> dict[str, Any]:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        normalized_question = self._normalize_question(question_text or raw_text)
        window_id = self._find_related_window_id(trigger_time)

        with self._lock:
            existing = self._find_matching_record_locked(
                trigger_time=trigger_time,
                normalized_question=normalized_question,
                raw_text=raw_text or question_text,
            )
            record = dict(existing or {})
            question_id = str(record.get("question_id") or self._generate_question_id(trigger_time, question_text or raw_text))
            answer_id = str(record.get("linked_answer_id") or self._generate_answer_id(trigger_time))
            target_status = self._promote_status(str(record.get("status") or ""), "answered")

            record.update(
                {
                    "question_id": question_id,
                    "session_id": session_storage_service.get_active_session_id(),
                    "event_id": record.get("event_id") or f"question_detected_{trigger_time.replace(':', '') or datetime.now().strftime('%H%M%S')}",
                    "raw_text": (raw_text or question_text or record.get("raw_text") or "").strip(),
                    "question_text": (question_text or raw_text or record.get("question_text") or "").strip(),
                    "normalized_question": normalized_question,
                    "trigger_time": trigger_time or record.get("trigger_time", ""),
                    "detected_at": record.get("detected_at", ""),
                    "answered_at": record.get("answered_at") or now,
                    "confirmed_at": record.get("confirmed_at", ""),
                    "confirmed_by_teacher_action": bool(record.get("confirmed_by_teacher_action", False)),
                    "linked_topic_id": record.get("linked_topic_id", ""),
                    "linked_topic_title": record.get("linked_topic_title", ""),
                    "linked_answer_id": answer_id,
                    "question_node_id": record.get("question_node_id", ""),
                    "status": target_status,
                    "window_id": record.get("window_id") or window_id,
                    "one_sentence_answer": (one_sentence_answer or teacher_speakable_answer or record.get("one_sentence_answer") or "").strip(),
                    "teacher_speakable_answer": (teacher_speakable_answer or one_sentence_answer or record.get("teacher_speakable_answer") or "").strip(),
                    "question_type": (question_type or record.get("question_type") or "").strip(),
                    "used_subject": (used_subject or record.get("used_subject") or "").strip(),
                    "confidence": (confidence or record.get("confidence") or "").strip(),
                    "answer_mode": (answer_mode or record.get("answer_mode") or "").strip(),
                }
            )
            self._write_record_locked(str(record.get("status") or "answered"), record)
            self._remove_stale_status_files_locked(question_id, {str(record.get("status") or "answered")})
            self._upsert_index_locked(record)
            self._upsert_timeline_locked(record)
            return deepcopy(record)

    def get_recent_valid_questions(self, *, limit: int = 4) -> list[str]:
        with self._lock:
            rows = self._load_index_locked()
            valid = [
                str(row.get("question_text") or row.get("raw_text") or "").strip()
                for row in rows
                if row.get("status") in VALID_QUESTION_STATUSES
            ]
            return [item for item in valid if item][-limit:]

    def list_question_records(
        self,
        *,
        status: str = "",
        bookmarked_only: bool = False,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._load_index_locked()
            records: list[dict[str, Any]] = []
            for row in rows:
                row_status = str(row.get("status") or "")
                if status and row_status != status:
                    continue
                if bookmarked_only and row_status not in VALID_QUESTION_STATUSES:
                    continue
                record = self._load_question_record_locked(str(row.get("question_id") or ""))
                if record is None:
                    record = dict(row)
                records.append(record)
            records.sort(
                key=lambda item: (
                    str(item.get("trigger_time") or ""),
                    str(item.get("answered_at") or ""),
                    str(item.get("confirmed_at") or ""),
                    str(item.get("question_id") or ""),
                )
            )
            return deepcopy(records)

    def get_question_trajectory(
        self,
        *,
        status: str = "",
        bookmarked_only: bool = False,
    ) -> list[dict[str, Any]]:
        records = self.list_question_records(status=status, bookmarked_only=bookmarked_only)
        return [self._record_to_timeline_node(record) for record in records]

    def get_trajectory_summary(self) -> dict[str, Any]:
        records = self.list_question_records()
        status_counts: dict[str, int] = {}
        for record in records:
            record_status = str(record.get("status") or "unknown")
            status_counts[record_status] = status_counts.get(record_status, 0) + 1

        valid_records = [record for record in records if record.get("status") in VALID_QUESTION_STATUSES]
        unresolved_records = [record for record in records if record.get("status") == "unresolved_link"]

        lines: list[str] = []
        for record in valid_records:
            repeat_hint = ""
            status = str(record.get("status") or "")
            if status == "unresolved_link":
                repeat_hint = "（待确认挂载）"
            elif record.get("linked_topic_title"):
                repeat_hint = f"（已挂到 {record.get('linked_topic_title')}）"
            lines.append(
                f"[{record.get('trigger_time', '')}] "
                f"{record.get('question_text') or record.get('raw_text', '')}"
                f" → {record.get('one_sentence_answer', '')}{repeat_hint}"
            )

        return {
            "total_questions": len(records),
            "valid_questions": len(valid_records),
            "linked_questions": status_counts.get("linked_to_tree", 0),
            "pending_links": len(unresolved_records),
            "status_counts": status_counts,
            "trajectory": "\n".join(lines),
            "records": valid_records,
        }

    def clear_current_session(self) -> dict[str, Any]:
        with self._lock:
            questions_dir = self._questions_dir()
            if questions_dir and os.path.exists(questions_dir):
                for folder in QUESTION_STATUS_FOLDERS:
                    folder_path = os.path.join(questions_dir, folder)
                    if os.path.exists(folder_path):
                        shutil.rmtree(folder_path, ignore_errors=True)
                    os.makedirs(folder_path, exist_ok=True)
                index_path = self._index_path()
                if index_path:
                    with open(index_path, "w", encoding="utf-8") as file_obj:
                        json.dump([], file_obj, ensure_ascii=False, indent=2)
            self._save_timeline_locked([])
        return {"status": "success", "message": "问题轨迹已清空"}

    def confirm_valid_question(
        self,
        *,
        question_id: str,
        answer_id: str,
        confirmed_by_teacher_action: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._load_question_record_locked(question_id)
            if record is None:
                raise ValueError("未找到对应的问题记录")
            if answer_id and record.get("linked_answer_id") and record.get("linked_answer_id") != answer_id:
                raise ValueError("answer_id 与问题记录不匹配")

            record["confirmed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            record["confirmed_by_teacher_action"] = bool(confirmed_by_teacher_action)
            record["status"] = self._promote_status(str(record.get("status") or ""), "confirmed_valid")
            self._write_record_locked(str(record.get("status") or "confirmed_valid"), record)

        preferred_titles = self._candidate_titles_for_question(str(record.get("window_id") or ""))
        link_result = knowledge_tree_service.link_valid_question(record, preferred_titles=preferred_titles)
        record["status"] = link_result["status"]
        record["linked_topic_id"] = link_result.get("linked_topic_id", "")
        record["linked_topic_title"] = link_result.get("linked_topic_title", "")
        record["question_node_id"] = link_result.get("question_node_id", "")

        with self._lock:
            self._write_record_locked(record["status"], record)
            self._remove_stale_status_files_locked(question_id, {"confirmed_valid", record["status"]})
            self._upsert_index_locked(record)
            self._upsert_timeline_locked(record)
            self._append_question_to_window_locked(question_id, str(record.get("window_id") or ""))

        return {
            **deepcopy(record),
            "knowledge_tree_snapshot": link_result.get("knowledge_tree_snapshot", {}),
        }


question_event_service = QuestionEventService()
