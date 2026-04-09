"""
转录文本服务
============
管理课堂转录文本和课程资料的读写
"""

import os
import re
import shutil
from datetime import datetime, timedelta
from typing import Optional

from config import DATA_DIR, MATERIALS_DIR
from services.session_storage_service import session_storage_service


class TranscriptService:
    """转录文本管理服务"""

    SUMMARY_START_MARKER = "=== 历史摘要 开始 ==="
    SUMMARY_END_MARKER = "=== 历史摘要 结束 ==="

    def __init__(self):
        self.transcript_path = os.path.join(DATA_DIR, "class_transcript.txt")
        self.material_path = os.path.join(DATA_DIR, "current_class_material.txt")
        self.cite_dir = MATERIALS_DIR

    def get_legacy_transcript_path(self) -> str:
        return self.transcript_path

    def get_session_transcript_path(self) -> str:
        return session_storage_service.get_session_path("class_transcript.txt")

    def get_active_transcript_path(self) -> str:
        return self.get_session_transcript_path() or self.transcript_path

    def get_active_material_snapshot_path(self) -> str:
        return session_storage_service.get_session_path("current_class_material.txt")

    def _read_transcript_lines(self, *, use_legacy: bool = False) -> list[str]:
        transcript_path = self.transcript_path if use_legacy else self.get_active_transcript_path()
        if not os.path.exists(transcript_path):
            return []

        with open(transcript_path, "r", encoding="utf-8") as f:
            return f.readlines()

    def get_recent_transcript(self, minutes: int = 2) -> str:
        """
        获取最近 N 分钟的转录文本

        Args:
            minutes: 向前回溯的分钟数，默认 2 分钟

        Returns:
            最近的转录文本
        """
        lines = self._read_transcript_lines()
        if not lines:
            return ""

        # 解析带有时间戳的行，筛选最近 N 分钟的内容
        now = datetime.now()
        cutoff = now - timedelta(minutes=minutes)
        recent_lines = []
        in_summary_block = False

        for line in lines:
            line = line.strip()
            if not line or line.startswith("==="):
                if line == self.SUMMARY_START_MARKER:
                    in_summary_block = True
                elif line == self.SUMMARY_END_MARKER:
                    in_summary_block = False
                continue

            if in_summary_block:
                continue

            # 尝试解析时间戳格式 [HH:MM:SS]
            if line.startswith("[") and "]" in line:
                try:
                    time_str = line[1:line.index("]")]
                    line_time = datetime.strptime(time_str, "%H:%M:%S").replace(
                        year=now.year, month=now.month, day=now.day
                    )
                    if line_time >= cutoff:
                        recent_lines.append(line)
                except ValueError:
                    recent_lines.append(line)  # 解析失败则保留
            else:
                recent_lines.append(line)

        return "\n".join(recent_lines)

    def get_full_transcript(self) -> str:
        """获取完整的课堂转录文本"""
        lines = self._read_transcript_lines()
        return "".join(lines)

    def get_transcript_metadata(self) -> dict:
        """从转录文件头部提取课程和资料元数据。"""
        metadata = {
            "subject": "",
            "course_name": "",
            "material_name": "",
        }

        transcript_path = self.transcript_path if session_storage_service.get_active_session_id() else self.get_active_transcript_path()
        if not os.path.exists(transcript_path):
            return metadata

        with open(transcript_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("科目："):
                    metadata["subject"] = line.split("科目：", 1)[1].strip()
                    continue
                if line.startswith("课程："):
                    metadata["course_name"] = line.split("课程：", 1)[1].strip()
                    continue
                if line.startswith("参考资料："):
                    metadata["material_name"] = line.split("参考资料：", 1)[1].strip()
                    continue
                if re.match(r"^\[\d{2}:\d{2}:\d{2}\]", line):
                    break

        return metadata

    def get_class_material(self) -> str:
        """获取课程 PPT 资料文本"""
        if not os.path.exists(self.material_path):
            return ""

        with open(self.material_path, "r", encoding="utf-8") as f:
            return f.read()

    def get_class_material_excerpt(self, max_chars: int = 480) -> str:
        material = re.sub(r"\s+", " ", self.get_class_material()).strip()
        if len(material) <= max_chars:
            return material
        return f"{material[:max_chars].rstrip()}…"

    def get_summary_context(self, max_recent_lines: int = 40) -> str:
        """
        获取用于课后总结的紧凑上下文：
        保留滚动摘要块，再附加最近若干条原始转录。
        """
        lines = self._read_transcript_lines(use_legacy=True)
        if not lines:
            return ""

        summary_lines: list[str] = []
        recent_lines: list[str] = []
        in_summary_block = False

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            if line == self.SUMMARY_START_MARKER:
                in_summary_block = True
                continue
            if line == self.SUMMARY_END_MARKER:
                in_summary_block = False
                continue

            if in_summary_block:
                summary_lines.append(line)
                continue

            if line.startswith("==="):
                continue

            if re.match(r"^\[\d{2}:\d{2}:\d{2}\]", line):
                recent_lines.append(line)

        blocks: list[str] = []
        if summary_lines:
            blocks.append("【历史滚动摘要】\n" + "\n".join(summary_lines))
        if recent_lines:
            blocks.append("【最近课堂记录】\n" + "\n".join(recent_lines[-max_recent_lines:]))
        return "\n\n".join(blocks).strip()

    def list_cite_files(self) -> list:
        """列出 cite 目录下可选的资料文本（.txt）。"""
        if not os.path.exists(self.cite_dir):
            return []

        items = []
        for name in os.listdir(self.cite_dir):
            if not name.lower().endswith(".txt"):
                continue
            file_path = os.path.join(self.cite_dir, name)
            stat = os.stat(file_path)
            items.append({
                "filename": name,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size": stat.st_size,
            })

        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return items

    def activate_cite_file(self, filename: Optional[str]) -> str:
        """将某个 cite 文本设为当前课程资料；None 表示清空。"""
        if not filename:
            with open(self.material_path, "w", encoding="utf-8") as f:
                f.write("")
            self.sync_material_snapshot_to_session()
            return ""

        source_path = os.path.join(self.cite_dir, filename)
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"未找到 cite 文件: {filename}")

        shutil.copyfile(source_path, self.material_path)
        self.sync_material_snapshot_to_session()
        return source_path

    def sync_material_snapshot_to_session(self) -> str:
        """把当前课堂资料镜像到 active session 目录，便于课后回放。"""
        session_material_path = self.get_active_material_snapshot_path()
        if not session_material_path:
            return ""

        os.makedirs(os.path.dirname(session_material_path), exist_ok=True)
        content = self.get_class_material()
        with open(session_material_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(content)
        return session_material_path
