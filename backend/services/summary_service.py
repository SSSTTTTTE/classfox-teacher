"""
课堂总结服务
============
复用现有转录与 LLM 逻辑，生成并保存课堂总结文件。
"""

import os
import re
from datetime import datetime

from typing import Awaitable, Callable, Optional

from config import DATA_DIR
from services.final_summary_packager import final_summary_packager
from services.llm_service import LLMService
from services.session_storage_service import session_storage_service
from services.session_state_service import session_state_service
from services.transcript_service import TranscriptService


class SummaryService:
    """负责生成并保存课堂总结。"""

    def __init__(self):
        self._llm_service = LLMService()
        self._transcript_service = TranscriptService()

    def _sanitize_filename(self, name: str) -> str:
        cleaned = re.sub(r'[\\/:*?"<>|]+', '_', (name or '').strip())
        cleaned = re.sub(r'\s+', '_', cleaned)
        return cleaned.strip('._') or '课堂笔记'

    async def generate_summary(self, course_name: Optional[str] = None) -> dict:
        return await self.generate_summary_with_progress(course_name=course_name)

    async def generate_summary_with_progress(
        self,
        course_name: Optional[str] = None,
        progress_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> dict:
        classroom_state = session_state_service.get_state()
        transcript_meta = self._transcript_service.get_transcript_metadata()
        summary_package = final_summary_packager.create_package()

        if not summary_package.get("window_summaries") and not summary_package.get("valid_questions"):
            raise ValueError("没有结构化课堂记录可供总结")

        resolved_course_name = (
            course_name
            or classroom_state.get("course_name")
            or summary_package.get("course_name")
            or transcript_meta.get("course_name")
            or "课堂笔记"
        ).strip()
        resolved_subject = (
            classroom_state.get("subject")
            or summary_package.get("subject")
            or transcript_meta.get("subject")
            or ""
        ).strip()

        summary_md = await self._llm_service.generate_class_summary(
            summary_package=summary_package,
            subject=resolved_subject,
            course_name=resolved_course_name,
            classroom_state=classroom_state,
            progress_callback=progress_callback,
        )

        if progress_callback is not None:
            await progress_callback(
                {
                    "phase": "saving",
                    "message": "Gemma4 已完成正文，正在写入课堂总结文件。",
                    "content_text": summary_md,
                }
            )

        summaries_dir = os.path.join(DATA_DIR, "summaries")
        os.makedirs(summaries_dir, exist_ok=True)

        now = datetime.now()
        date_part = now.strftime("%Y%m%d")
        time_part = now.strftime("%H%M%S")
        safe_course_name = self._sanitize_filename(resolved_course_name)
        filename = f"{safe_course_name}_{date_part}_{time_part}.md"
        session_summaries_dir = session_storage_service.ensure_session_subdir("summaries")
        primary_filepath = os.path.join(session_summaries_dir, filename) if session_summaries_dir else os.path.join(summaries_dir, filename)
        canonical_session_filepath = os.path.join(session_summaries_dir, "final_summary.md") if session_summaries_dir else primary_filepath
        mirror_filepath = os.path.join(summaries_dir, filename)

        os.makedirs(os.path.dirname(primary_filepath), exist_ok=True)
        with open(primary_filepath, "w", encoding="utf-8") as file_obj:
            file_obj.write(summary_md)
        if canonical_session_filepath and canonical_session_filepath != primary_filepath:
            with open(canonical_session_filepath, "w", encoding="utf-8") as file_obj:
                file_obj.write(summary_md)
        if primary_filepath != mirror_filepath:
            with open(mirror_filepath, "w", encoding="utf-8") as file_obj:
                file_obj.write(summary_md)

        if progress_callback is not None:
            await progress_callback(
                {
                    "phase": "completed",
                    "message": "课堂总结已生成并保存。",
                    "content_text": summary_md,
                    "filename": filename,
                    "course_name": resolved_course_name,
                    "package_path": session_storage_service.get_session_path("summaries", "final_summary_input_package.json"),
                }
            )

        return {
            "status": "success",
            "filename": filename,
            "summary": summary_md,
            "course_name": resolved_course_name,
            "package_path": session_storage_service.get_session_path("summaries", "final_summary_input_package.json"),
        }
