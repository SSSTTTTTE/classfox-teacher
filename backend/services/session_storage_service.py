"""
Session 级存储服务
=================
负责生成 session_id、创建目录骨架，并为各服务提供当前 session 路径。
"""

from __future__ import annotations

import json
import os
import re
import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from config import DATA_DIR, SESSIONS_DIR


class SessionStorageService:
    """统一管理当前课堂 session 的目录和元信息。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_marker_path = os.path.join(SESSIONS_DIR, "_active_session.json")
        self._active_session_id = ""
        self._active_session_meta: dict[str, Any] = {}
        self._load_active_session()

    def _load_active_session(self) -> None:
        if not os.path.exists(self._active_marker_path):
            return

        try:
            with open(self._active_marker_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except Exception:
            return

        if not isinstance(payload, dict):
            return

        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            return

        self._active_session_id = session_id
        self._active_session_meta = payload

    def _persist_active_marker_locked(self) -> None:
        payload = {
            "session_id": self._active_session_id,
            **self._active_session_meta,
        }
        try:
            with open(self._active_marker_path, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _write_json(self, path: str, payload: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)

    def _slugify(self, value: str, *, fallback: str) -> str:
        cleaned = re.sub(r"\s+", "_", (value or "").strip())
        cleaned = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff-]+", "_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
        return cleaned[:40] or fallback

    def start_session(
        self,
        *,
        subject: str,
        course_name: str,
        material_name: str,
        chat_model: str,
        final_summary_model: str,
    ) -> dict[str, Any]:
        now = datetime.now().astimezone()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        course_slug = self._slugify(course_name, fallback="class")
        subject_slug = self._slugify(subject, fallback="general")
        session_id = f"{timestamp}_{subject_slug}_{course_slug}"
        session_dir = os.path.join(SESSIONS_DIR, session_id)

        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(os.path.join(session_dir, "timeline"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "windows"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "windows", "debug"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "questions"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "questions", "detected"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "questions", "answered"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "questions", "confirmed_valid"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "questions", "linked_to_tree"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "questions", "unresolved_link"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "knowledge_tree"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "knowledge_tree", "snapshots"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "debug"), exist_ok=True)
        os.makedirs(os.path.join(session_dir, "summaries"), exist_ok=True)

        metadata = {
            "session_id": session_id,
            "subject": (subject or "").strip(),
            "course_name": (course_name or "").strip(),
            "material_name": (material_name or "").strip(),
            "started_at": now.isoformat(timespec="seconds"),
            "ended_at": "",
            "chat_model": (chat_model or "").strip(),
            "final_summary_model": (final_summary_model or "").strip(),
            "status": "active",
        }

        self._write_json(os.path.join(session_dir, "session_meta.json"), metadata)
        self._write_json(os.path.join(session_dir, "timeline", "current_session.json"), [])

        with self._lock:
            self._active_session_id = session_id
            self._active_session_meta = metadata
            self._persist_active_marker_locked()

        return deepcopy(metadata)

    def finalize_current_session(self, *, status: str = "completed") -> dict[str, Any]:
        with self._lock:
            if not self._active_session_id:
                return {}

            metadata = deepcopy(self._active_session_meta)
            metadata["status"] = status
            metadata["ended_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            self._active_session_meta = metadata
            self._persist_active_marker_locked()

        session_meta_path = self.get_session_path("session_meta.json")
        if session_meta_path:
            try:
                self._write_json(session_meta_path, metadata)
            except Exception:
                pass

        return metadata

    def get_active_session_id(self) -> str:
        with self._lock:
            return self._active_session_id

    def get_active_session_meta(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._active_session_meta)

    def get_session_dir(self, session_id: Optional[str] = None) -> str:
        resolved_session_id = (session_id or self.get_active_session_id()).strip()
        if not resolved_session_id:
            return ""
        return os.path.join(SESSIONS_DIR, resolved_session_id)

    def get_session_path(self, *parts: str, session_id: Optional[str] = None) -> str:
        session_dir = self.get_session_dir(session_id=session_id)
        if not session_dir:
            return ""
        return os.path.join(session_dir, *parts)

    def ensure_session_subdir(self, *parts: str, session_id: Optional[str] = None) -> str:
        target_dir = self.get_session_path(*parts, session_id=session_id)
        if not target_dir:
            return ""
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    def write_session_json(self, relative_path: str, payload: dict[str, Any] | list[Any]) -> str:
        target_path = self.get_session_path(relative_path)
        if not target_path:
            return ""

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        return target_path

    def write_session_text(self, relative_path: str, content: str) -> str:
        target_path = self.get_session_path(relative_path)
        if not target_path:
            return ""

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(content)
        return target_path

    def get_legacy_timeline_path(self) -> str:
        return os.path.join(DATA_DIR, "timeline", "current_session.json")


session_storage_service = SessionStorageService()
