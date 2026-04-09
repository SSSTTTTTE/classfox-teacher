"""
监控服务（教师版）
==================
负责麦克风录音、ASR 转文字、学生提问检测与 WebSocket 事件推送
"""

import asyncio
from difflib import SequenceMatcher
import json
import logging
import os
import re
import threading
from datetime import datetime
from typing import List, Set, Optional, Tuple

from fastapi import WebSocket

from config import DATA_DIR
from services.asr_service import create_asr, BaseASR, LocalASR
from services.knowledge_tree_service import knowledge_tree_service
from services.llm_service import LLMService
from services.prompt_builder import resolve_subject_name
from services.question_event_service import question_event_service
from services.session_storage_service import session_storage_service
from services.session_state_service import session_state_service
from services.transcript_cleaner import transcript_cleaner
from services.transcript_service import TranscriptService

logger = logging.getLogger(__name__)


class MonitorService:
    """课堂监控服务 - 核心后台服务（教师版）"""

    SUMMARY_WINDOW_SECONDS = 30
    SUMMARY_TASK_TIMEOUT_SECONDS = 28
    ASR_FILLER_ONLY_TEXTS = {
        "嗯",
        "嗯嗯",
        "呃",
        "呃呃",
        "额",
        "啊",
        "啊啊",
        "哦",
        "哦哦",
        "那个",
        "这个",
        "就是",
        "然后",
        "然后呢",
        "就是说",
        "对吧",
        "是吧",
    }

    # 学生提问句型特征（用于快速预检）
    QUESTION_PATTERNS = [
        r"[？?]$",                     # 以问号结尾
        r"^(老师|请问|我想问|我有个问题)",  # 常见提问开头
        r"(什么|为什么|怎么|如何|是不是|对不对|能不能|可以吗|吗$|呢$)",  # 疑问词
        r"(不懂|不明白|不理解|没听懂|能解释|能说明)",  # 请求解释
    ]

    def __init__(self):
        # 学生提问检测状态
        self._last_question_time: float = 0
        self._question_cooldown: float = 10.0  # 10秒内不重复触发同一问题

        # 录音状态
        self.is_monitoring: bool = False
        self.is_paused: bool = False

        # ASR 实例
        self._asr: Optional[BaseASR] = None

        # 用于从 ASR 回调线程安全地广播到 WebSocket 的事件循环
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # WebSocket 连接池
        self._websockets: Set[WebSocket] = set()

        # 转录文件路径
        self._transcript_service = TranscriptService()
        self.transcript_path = os.path.join(DATA_DIR, "class_transcript.txt")
        self._llm_service = LLMService()
        self._transcript_cleaner = transcript_cleaner
        self._state_lock = threading.RLock()

        # 会话状态
        self._session_id: str = ""
        self._session_start_marker: str = ""
        self._session_end_marker: str = ""
        self._course_name: str = ""
        self._subject: str = ""
        self._active_material_name: str = ""
        self._partial_line: Optional[Tuple[str, str]] = None
        self._recent_entries: List[Tuple[str, str]] = []
        self._recent_normalized_entries: List[str] = []
        self._rolling_summary: str = ""
        self._summary_cards: List[dict] = []
        self._summary_source_entries: List[Tuple[str, str]] = []
        self._summary_task_running: bool = False
        self._window_queue: List[dict] = []
        self._window_started_at: Optional[datetime] = None
        self._window_started_timestamp: str = ""
        self._window_timer: Optional[threading.Timer] = None
        self._window_counter: int = 0
        self._final_summary_state: dict = {}

        # ASR 增量文本追踪
        self._last_asr_text: str = ""

    def _is_sentence_closed(self, text: str) -> bool:
        return bool(re.search(r"[。！？!?；;……]$", text.strip()))

    def _seconds_between_timestamps(self, earlier: str, later: str) -> Optional[float]:
        try:
            start = datetime.strptime(earlier, "%H:%M:%S")
            end = datetime.strptime(later, "%H:%M:%S")
        except ValueError:
            return None

        delta = (end - start).total_seconds()
        if delta < 0:
            delta += 24 * 60 * 60
        return delta

    def _replace_last_entry_locked(self, timestamp: str, text: str):
        if self._recent_entries:
            self._recent_entries[-1] = (timestamp, text)
        if self._summary_source_entries:
            self._summary_source_entries[-1] = (timestamp, text)
        session_state_service.replace_latest_transcript_entry(timestamp, text)

        dedupe_text = self._normalize_for_dedupe(text)
        if dedupe_text:
            if self._recent_normalized_entries:
                self._recent_normalized_entries[-1] = dedupe_text
            else:
                self._recent_normalized_entries.append(dedupe_text)

    def _append_or_merge_local_entry_locked(self, timestamp: str, text: str) -> tuple[bool, str]:
        cleaned = self._clean_asr_text(text)
        if not cleaned or not self._is_meaningful_text(cleaned):
            return False, ""

        if not self._summary_source_entries:
            return self._append_entry_locked(timestamp, cleaned), cleaned

        last_timestamp, last_text = self._summary_source_entries[-1]
        previous = self._clean_asr_text(last_text)
        if not previous:
            return self._append_entry_locked(timestamp, cleaned), cleaned

        gap_seconds = self._seconds_between_timestamps(last_timestamp, timestamp)
        can_try_merge = gap_seconds is not None and gap_seconds <= 3
        merged_text = ""

        if can_try_merge:
            if cleaned.startswith(previous) and len(cleaned) > len(previous):
                merged_text = cleaned
            elif (
                len(previous) <= 4
                or not self._is_sentence_closed(previous)
            ) and not self._is_near_duplicate_locked(cleaned):
                merged_text = f"{previous}{cleaned}".strip()

        if merged_text and self._is_meaningful_text(merged_text):
            self._replace_last_entry_locked(timestamp, merged_text)
            return True, merged_text

        appended = self._append_entry_locked(timestamp, cleaned)
        return appended, cleaned if appended else ""

    def get_all_keywords(self) -> List[str]:
        """保留兼容接口，返回空列表（教师版不使用关键词模式）"""
        return []

    def get_warning_keywords(self) -> List[str]:
        """保留兼容接口，返回空列表"""
        return []

    def update_custom_keywords(self, keywords: List[str]):
        """保留兼容接口（教师版不使用关键词）"""
        pass

    def _is_question_sentence(self, text: str) -> bool:
        """快速判断文本是否包含学生提问特征。"""
        for pattern in self.QUESTION_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

    def reload_keywords(self):
        """保留兼容接口"""
        return {"danger": [], "warning": []}

    def register_websocket(self, ws: WebSocket):
        """注册 WebSocket 连接"""
        self._websockets.add(ws)

    def unregister_websocket(self, ws: WebSocket):
        """注销 WebSocket 连接"""
        self._websockets.discard(ws)

    def get_realtime_summary(self) -> str:
        with self._state_lock:
            return self._rolling_summary.strip()

    def get_realtime_summary_payload(self) -> dict:
        runtime = self._llm_service.runtime_config()
        with self._state_lock:
            return {
                "summary_text": self._rolling_summary.strip(),
                "cards": [dict(card) for card in self._summary_cards],
                "realtime_summary_enabled": runtime["realtime_summary_enabled"],
                "realtime_summary_model": runtime["realtime_summary_model"],
            }

    def _empty_final_summary_state(self) -> dict:
        runtime = self._llm_service.runtime_config()
        return {
            "active": False,
            "phase": "idle",
            "message": "",
            "model": runtime["final_summary_model"],
            "course_name": self._course_name,
            "thinking_text": "",
            "content_text": "",
            "filename": "",
            "error": "",
            "started_at": "",
            "finished_at": "",
        }

    def get_final_summary_payload(self) -> dict:
        with self._state_lock:
            return dict(self._final_summary_state or self._empty_final_summary_state())

    async def update_final_summary_state(self, **changes) -> dict:
        with self._state_lock:
            if not self._final_summary_state:
                self._final_summary_state = self._empty_final_summary_state()
            self._final_summary_state.update(changes)
            snapshot = dict(self._final_summary_state)

        await self._broadcast_alert({"type": "final_summary_update", **snapshot})
        return snapshot

    def get_context_status(self) -> dict:
        runtime = self._llm_service.runtime_config()
        return {
            **session_state_service.get_context_status(),
            "realtime_summary_enabled": runtime["realtime_summary_enabled"],
            "realtime_summary_model": runtime["realtime_summary_model"],
        }

    async def _broadcast_alert(self, message: dict):
        """向所有已连接的 WebSocket 客户端广播警报"""
        dead_connections = set()
        for ws in self._websockets:
            try:
                await ws.send_text(json.dumps(message, ensure_ascii=False))
            except Exception:
                dead_connections.add(ws)
        # 清理断开的连接
        self._websockets -= dead_connections

    def _check_keywords(self, text: str, keywords: List[str]) -> List[str]:
        """保留兼容接口，教师版不使用。"""
        return []

    def _check_alerts(self, text: str) -> dict:
        """保留兼容接口，教师版不使用关键词警报。"""
        return {"danger": [], "warning": []}

    def _create_and_start_asr(self):
        self._asr = create_asr(on_text=self._on_asr_text)
        if isinstance(self._asr, LocalASR):
            self._asr.on_text = self._on_local_asr_text
        self._asr.start()

    async def start(self, course_name: str = "", material_name: str = "", subject: str = "") -> dict:
        """启动监控服务"""
        if self.is_monitoring:
            return {"status": "already_running", "message": "监控服务已在运行中"}

        self.is_monitoring = True
        self.is_paused = False

        # 保存当前事件循环引用，供 ASR 回调使用
        self._loop = asyncio.get_running_loop()

        self._course_name = course_name.strip()
        self._subject = resolve_subject_name(subject, course_name)
        self._active_material_name = material_name.strip()
        runtime = self._llm_service.runtime_config()
        session_meta = session_storage_service.start_session(
            subject=self._subject,
            course_name=self._course_name,
            material_name=self._active_material_name,
            chat_model=runtime["chat_model"],
            final_summary_model=runtime["final_summary_model"],
        )
        self._session_id = session_meta.get("session_id", "")
        self._reset_session_state()
        session_state_service.reset_for_class(
            subject=self._subject,
            course_name=self._course_name,
            material_name=self._active_material_name,
            material_excerpt=self._transcript_service.get_class_material_excerpt(),
            llm_ready=True,
        )
        self._transcript_service.sync_material_snapshot_to_session()
        try:
            os.makedirs(os.path.join(DATA_DIR, "timeline"), exist_ok=True)
            with open(session_storage_service.get_legacy_timeline_path(), "w", encoding="utf-8") as file_obj:
                json.dump([], file_obj, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("初始化兼容时间轴镜像失败")
        self._flush_transcript_file()

        # 创建 ASR 实例并启动
        # 本地 ASR 使用独立的回调（每句新建一行），线上 ASR 使用流式回调
        self._create_and_start_asr()

        return {
            "status": "started",
            "message": "课堂监听已启动 🎓 实时转录和学生提问检测已开始",
            "subject": self._subject,
            "session_id": self._session_id,
        }

    async def pause(self) -> dict:
        """暂停监控并释放当前 ASR。"""
        if not self.is_monitoring:
            return {"status": "not_running", "message": "监控服务未在运行"}

        if self.is_paused:
            return {"status": "already_paused", "message": "监控服务已暂停"}

        self.is_paused = True

        if self._asr:
            self._asr.stop()
            self._asr = None

        with self._state_lock:
            if self._partial_line and self._partial_line[1].strip():
                timestamp, text = self._partial_line
                appended = self._append_entry_locked(timestamp, text)
                self._partial_line = None
                if appended:
                    self._flush_transcript_file()

        return {"status": "paused", "message": "监控已暂停"}

    async def resume(self) -> dict:
        """继续监控。"""
        if not self.is_monitoring:
            return {"status": "not_running", "message": "监控服务未在运行"}

        if not self.is_paused:
            return {"status": "not_paused", "message": "监控当前未暂停"}

        self.is_paused = False
        self._loop = asyncio.get_running_loop()
        self._create_and_start_asr()
        return {"status": "resumed", "message": "监控已继续"}

    async def stop(self) -> dict:
        """停止监控服务"""
        if not self.is_monitoring:
            return {"status": "not_running", "message": "监控服务未在运行"}

        self.is_monitoring = False
        self.is_paused = False
        session_state_service.set_llm_ready(False)

        # 停止 ASR
        if self._asr:
            self._asr.stop()
            self._asr = None

        with self._state_lock:
            stop_time = datetime.now()
            if self._partial_line and self._partial_line[1].strip():
                timestamp, text = self._partial_line
                self._append_entry_locked(timestamp, text)
                self._partial_line = None

            self._queue_current_window_locked(flush_reason="stop", ended_at=stop_time)
            self._session_end_marker = (
                f"=== 课堂记录 结束于 {stop_time.strftime('%Y-%m-%d %H:%M:%S')} ==="
            )
            self._flush_transcript_file()

        await self._wait_for_summary_drain()
        session_storage_service.finalize_current_session(status="stopped")

        return {
            "status": "stopped",
            "message": "监控已停止",
            "course_name": self._course_name,
            "session_id": self._session_id,
        }

    def _reset_session_state(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self._state_lock:
            self._cancel_window_timer_locked()
            self._session_id = session_storage_service.get_active_session_id()
            self._session_start_marker = f"=== 课堂记录 开始于 {now} ==="
            self._session_end_marker = ""
            self._partial_line = None
            self._recent_entries = []
            self._recent_normalized_entries = []
            self._rolling_summary = ""
            self._summary_cards = []
            self._summary_source_entries = []
            self._summary_task_running = False
            self._window_queue = []
            self._window_started_at = None
            self._window_started_timestamp = ""
            self._window_counter = 0
            self._last_asr_text = ""
            self._final_summary_state = self._empty_final_summary_state()

    def reset_context_for_recovery(self) -> dict:
        with self._state_lock:
            self._cancel_window_timer_locked()
            self._partial_line = None
            self._recent_entries = []
            self._recent_normalized_entries = []
            self._summary_source_entries = []
            self._summary_task_running = False
            self._window_queue = []
            self._window_started_at = None
            self._window_started_timestamp = ""
            self._last_asr_text = ""
            self._last_question_time = 0
            self._flush_transcript_file()

        context = session_state_service.reset_context_preserving_summary(llm_ready=False)
        return {
            "summary_kept": bool(self._rolling_summary.strip() or self._summary_cards),
            "context": context,
        }

    def _upsert_summary_card_locked(self, payload: dict):
        section_title = (payload.get("section_title") or "").strip()
        points = [
            item.strip()
            for item in payload.get("points", [])
            if isinstance(item, str) and item.strip()
        ][:4]
        flow_title = (payload.get("flow_title") or "").strip()
        flow_steps = [
            item.strip()
            for item in payload.get("flow_steps", [])
            if isinstance(item, str) and item.strip()
        ][:5]

        if not section_title and not points and not flow_steps:
            return

        card = {
            "section_title": section_title or "当前课堂要点",
            "points": points,
            "flow_title": flow_title,
            "flow_steps": flow_steps,
        }

        if self._summary_cards and self._summary_cards[-1].get("section_title") == card["section_title"]:
            self._summary_cards[-1] = card
        else:
            self._summary_cards.append(card)
            self._summary_cards = self._summary_cards[-6:]

    def _build_summary_card_from_window_payload(self, payload: dict) -> dict:
        points: list[str] = []
        for collection in (
            payload.get("extracted_subtopics", []),
            payload.get("extracted_concepts", []),
            payload.get("facts", []),
        ):
            for item in collection:
                cleaned = str(item).strip()
                if not cleaned or cleaned in points:
                    continue
                points.append(cleaned)
                if len(points) >= 4:
                    break
            if len(points) >= 4:
                break

        return {
            "section_title": (payload.get("main_topic") or "").strip(),
            "points": points,
            "flow_title": "",
            "flow_steps": [],
        }

    def _normalize_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text or "")
        return text.strip()

    def _collapse_repeated_phrase(self, text: str) -> str:
        compact = text
        previous = ""
        while compact != previous:
            previous = compact
            compact = re.sub(r"([A-Za-z0-9\u4e00-\u9fff]{1,4})(?:\1){1,}", r"\1", compact)
            compact = re.sub(r"\b([A-Za-z0-9]{1,4})(?:\s+\1){1,}\b", r"\1", compact)
        return compact

    def _clean_asr_text(self, text: str) -> str:
        cleaned = self._normalize_text(text)
        if not cleaned:
            return ""

        cleaned = cleaned.replace("…", ".").replace("···", ".")
        cleaned = re.sub(
            r"[\[(（【<〈].{0,8}(?:noise|静音|噪音|杂音|掌声|咳嗽|笑声|听不清).{0,4}[\])）】>〉]",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"[~～·•]+", " ", cleaned)
        cleaned = re.sub(r"([，,。！？!?；;、])\1+", r"\1", cleaned)
        cleaned = self._collapse_repeated_phrase(cleaned)
        cleaned = re.sub(r"(?:^|[，,。！？!?；;、\s])(嗯+|呃+|额+|啊+|哦+|唉+|诶+)(?=$|[，,。！？!?；;、\s])", " ", cleaned)
        cleaned = re.sub(
            r"^(?:(?:那个|这个|就是|然后|所以|那么|然后呢|就是说|老师啊|老师呀|老师欸)[，,。！？!?；;、\s]*)+",
            "",
            cleaned,
        )
        cleaned = re.sub(r"(?:[，,。！？!?；;、\s]+)(?:嗯+|呃+|额+|啊+|哦+|唉+|诶+)$", "", cleaned)
        cleaned = re.sub(r"\s*([，,。！？!?；;、])\s*", r"\1", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip(" ，,。！？!?；;、")

    def _normalize_for_dedupe(self, text: str) -> str:
        normalized = self._normalize_text(text)
        return normalized.rstrip("。？！；!?;，,、 ")

    def _extract_question_candidate(self, text: str) -> str:
        candidate = self._clean_asr_text(text)
        if not candidate:
            return ""

        candidate = re.sub(
            r"^(?:老师[啊呀呢吗吧]*[，,、 ]*)?(?:我想问(?:一下)?|想问(?:一下)?|请问(?:一下)?|我有个问题|我想请教(?:一下)?|那个我想问(?:一下)?)[，,、 ]*",
            "",
            candidate,
        )
        candidate = re.sub(r"^(?:老师[啊呀呢吗吧]*[，,、 ]*)+", "", candidate)
        candidate = re.sub(r"(?:啊|呀|呃|嗯)+$", "", candidate).strip(" ，,。！？!?；;、")
        return candidate or self._clean_asr_text(text)

    def _is_meaningful_text(self, text: str) -> bool:
        normalized = self._normalize_for_dedupe(self._clean_asr_text(text))
        if len(normalized) < 2:
            return False

        if normalized in self.ASR_FILLER_ONLY_TEXTS:
            return False

        compact = re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)
        if len(compact) < 2:
            return False

        return bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", compact))

    def _is_near_duplicate_locked(self, text: str) -> bool:
        dedupe_text = self._normalize_for_dedupe(text)
        if not dedupe_text:
            return True

        for recent in self._recent_normalized_entries[-8:]:
            if dedupe_text == recent:
                return True

            shorter_len = min(len(dedupe_text), len(recent))
            longer_len = max(len(dedupe_text), len(recent))

            if shorter_len >= 4 and (dedupe_text in recent or recent in dedupe_text):
                if shorter_len / longer_len >= 0.8:
                    return True

            if shorter_len >= 6:
                similarity = SequenceMatcher(None, dedupe_text, recent).ratio()
                if similarity >= 0.88:
                    return True

        return False

    def _append_entry_locked(self, timestamp: str, text: str) -> bool:
        cleaned = self._clean_asr_text(text)
        if not cleaned or not self._is_meaningful_text(cleaned):
            return False

        dedupe_text = self._normalize_for_dedupe(cleaned)
        if self._is_near_duplicate_locked(cleaned):
            return False

        self._recent_entries.append((timestamp, cleaned))
        self._summary_source_entries.append((timestamp, cleaned))
        if self._window_started_at is None:
            self._open_summary_window_locked(timestamp)
        session_state_service.add_transcript_entry(timestamp, cleaned)
        if dedupe_text:
            self._recent_normalized_entries.append(dedupe_text)
            self._recent_normalized_entries = self._recent_normalized_entries[-12:]
        return True

    def _open_summary_window_locked(self, timestamp: str):
        self._window_started_at = datetime.now()
        self._window_started_timestamp = timestamp
        self._schedule_window_timeout_locked()

    def _schedule_window_timeout_locked(self):
        if self._window_timer is not None:
            return

        timer = threading.Timer(self.SUMMARY_WINDOW_SECONDS, self._handle_window_timeout)
        timer.daemon = True
        self._window_timer = timer
        timer.start()

    def _cancel_window_timer_locked(self):
        if self._window_timer is not None:
            self._window_timer.cancel()
            self._window_timer = None

    def _handle_window_timeout(self):
        with self._state_lock:
            self._window_timer = None
            self._queue_current_window_locked(flush_reason="timer")
            self._flush_transcript_file()

    def _queue_current_window_locked(
        self,
        *,
        flush_reason: str,
        ended_at: Optional[datetime] = None,
    ) -> bool:
        self._cancel_window_timer_locked()
        if not self._summary_source_entries:
            self._window_started_at = None
            self._window_started_timestamp = ""
            return False

        self._window_counter += 1
        end_time = (ended_at or datetime.now()).strftime("%H:%M:%S")
        window_payload = {
            "window_id": f"w_{self._window_counter:04d}",
            "session_id": self._session_id,
            "start_time": self._window_started_timestamp or self._summary_source_entries[0][0],
            "end_time": end_time,
            "entries": list(self._summary_source_entries),
            "flush_reason": flush_reason,
        }
        self._window_queue.append(window_payload)
        self._summary_source_entries = []
        self._window_started_at = None
        self._window_started_timestamp = ""
        self._schedule_summary_locked()
        return True

    def _pending_window_entries_locked(self) -> List[Tuple[str, str]]:
        pending_entries: List[Tuple[str, str]] = []
        for window_payload in self._window_queue:
            pending_entries.extend(window_payload.get("entries", []))
        pending_entries.extend(self._summary_source_entries)
        return pending_entries

    def _build_session_transcript_lines_locked(self) -> List[str]:
        lines: List[str] = [self._session_start_marker, ""]

        if self._session_id:
            lines.append(f"Session ID：{self._session_id}")
        if self._course_name:
            lines.append(f"课程：{self._course_name}")
        if self._subject:
            lines.append(f"科目：{self._subject}")
        if self._active_material_name:
            lines.append(f"参考资料：{self._active_material_name}")
        if self._session_id or self._course_name or self._subject or self._active_material_name:
            lines.append("")

        for timestamp, text in self._recent_entries:
            lines.append(f"[{timestamp}] {text}")

        if self._session_end_marker:
            lines.extend(["", self._session_end_marker])

        return lines

    def _build_legacy_transcript_lines_locked(self) -> List[str]:
        lines: List[str] = [self._session_start_marker, ""]

        if self._course_name:
            lines.append(f"课程：{self._course_name}")
        if self._subject:
            lines.append(f"科目：{self._subject}")
        if self._active_material_name:
            lines.append(f"参考资料：{self._active_material_name}")
        if self._course_name or self._subject or self._active_material_name:
            lines.append("")

        if self._rolling_summary:
            lines.extend([
                TranscriptService.SUMMARY_START_MARKER,
                self._rolling_summary.strip(),
                TranscriptService.SUMMARY_END_MARKER,
                "",
            ])

        for timestamp, text in self._pending_window_entries_locked():
            lines.append(f"[{timestamp}] {text}")

        if self._session_end_marker:
            lines.extend(["", self._session_end_marker])

        return lines

    def _write_text_file(self, path: str, lines: List[str]):
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file_obj:
            file_obj.write("\n".join(lines).rstrip() + "\n")

    def _flush_transcript_file(self):
        try:
            session_transcript_path = self._transcript_service.get_session_transcript_path()
            self._write_text_file(session_transcript_path, self._build_session_transcript_lines_locked())
            self._write_text_file(self.transcript_path, self._build_legacy_transcript_lines_locked())
        except Exception:
            logger.exception("写入转录文件失败")

    def _schedule_summary_locked(self):
        if self._summary_task_running or not self._loop or not self._window_queue:
            return
        chunk = dict(self._window_queue[0])
        previous_summary = self._rolling_summary
        self._summary_task_running = True
        asyncio.run_coroutine_threadsafe(
            self._run_summary_task(previous_summary, chunk),
            self._loop,
        )

    async def _run_summary_task(
        self,
        previous_summary: str,
        chunk: dict,
    ):
        chunk_entries = list(chunk.get("entries", []))
        cleaner_payload = self._transcript_cleaner.clean_window_entries(chunk_entries)
        structured_payload: dict = {}
        window_record: dict = {}
        tree_result: dict = {}
        error_message = ""

        self._transcript_cleaner.persist_window_debug(
            window_id=str(chunk.get("window_id") or ""),
            raw_text=cleaner_payload.get("raw_text", ""),
            rule_cleaned_text=cleaner_payload.get("rule_cleaned_text", ""),
        )

        try:
            structured_payload = await asyncio.wait_for(
                self._llm_service.generate_window_structured_summary(
                    window_id=str(chunk.get("window_id") or ""),
                    raw_window_text=cleaner_payload.get("raw_text", ""),
                    rule_cleaned_text=cleaner_payload.get("rule_cleaned_text", ""),
                    subject=self._subject,
                    course_name=self._course_name,
                    start_time=str(chunk.get("start_time") or ""),
                    end_time=str(chunk.get("end_time") or ""),
                    previous_main_topic=knowledge_tree_service.get_current_main_topic(),
                    knowledge_tree_outline=knowledge_tree_service.get_outline_text(),
                    recent_valid_questions=question_event_service.get_recent_valid_questions(limit=4),
                ),
                timeout=self.SUMMARY_TASK_TIMEOUT_SECONDS,
            )
            self._transcript_cleaner.persist_window_debug(
                window_id=str(chunk.get("window_id") or ""),
                raw_text=cleaner_payload.get("raw_text", ""),
                rule_cleaned_text=cleaner_payload.get("rule_cleaned_text", ""),
                model_payload=structured_payload,
            )
        except Exception as exc:
            error_message = str(exc)
            with self._state_lock:
                self._summary_task_running = False
                if self._window_queue and self._window_queue[0].get("window_id") == chunk.get("window_id"):
                    self._persist_window_record_locked(
                        chunk,
                        structured_payload,
                        cleaner_payload=cleaner_payload,
                        error_message=error_message,
                    )
                    self._window_queue.pop(0)
                self._flush_transcript_file()
                self._schedule_summary_locked()
            return

        with self._state_lock:
            if self._window_queue and self._window_queue[0].get("window_id") == chunk.get("window_id"):
                self._rolling_summary = (structured_payload.get("stage_summary") or previous_summary or "").strip()
                self._upsert_summary_card_locked(self._build_summary_card_from_window_payload({
                    "main_topic": structured_payload.get("main_topic", ""),
                    "extracted_subtopics": structured_payload.get("subtopics", []),
                    "extracted_concepts": structured_payload.get("concepts", []),
                    "facts": structured_payload.get("facts", []),
                }))
                window_record = self._persist_window_record_locked(
                    chunk,
                    structured_payload,
                    cleaner_payload=cleaner_payload,
                )
                self._window_queue.pop(0)
            self._summary_task_running = False
            session_state_service.update_summary(
                summary_text=self._rolling_summary,
                cards=[dict(card) for card in self._summary_cards],
            )
            self._flush_transcript_file()
            self._schedule_summary_locked()
            current_payload = {
                "summary_text": self._rolling_summary,
                "cards": [dict(card) for card in self._summary_cards],
            }

        if window_record:
            tree_result = knowledge_tree_service.merge_window_record(window_record)

        if (current_payload["summary_text"] or current_payload["cards"]) and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_alert({"type": "summary_update", **current_payload}),
                self._loop,
            )
        if tree_result and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_alert(
                    {
                        "type": "knowledge_tree_update",
                        "current_main_topic": tree_result.get("main_topic_title", ""),
                        "knowledge_tree": tree_result.get("tree", {}),
                    }
                ),
                self._loop,
            )

    def _persist_window_record_locked(
        self,
        chunk: dict,
        structured_payload: dict,
        *,
        cleaner_payload: Optional[dict] = None,
        error_message: str = "",
    ) -> dict:
        window_id = str(chunk.get("window_id") or "").strip()
        if not window_id:
            return {}

        entries = list(chunk.get("entries", []))
        cleaner_payload = cleaner_payload or {}
        raw_text = cleaner_payload.get("raw_text") or "\n".join(f"[{timestamp}] {text}" for timestamp, text in entries)
        cleaned_text = str(structured_payload.get("cleaned_text") or cleaner_payload.get("rule_cleaned_text") or "").strip()
        main_topic = str(structured_payload.get("main_topic") or "").strip()
        extracted_subtopics = [
            item.strip()
            for item in structured_payload.get("subtopics", [])
            if isinstance(item, str) and item.strip()
        ]
        extracted_concepts = [
            item.strip()
            for item in structured_payload.get("concepts", [])
            if isinstance(item, str) and item.strip()
        ]
        extracted_topics = [main_topic] if main_topic else []
        extracted_relations = [
            {
                "source": str(item.get("source") or "").strip(),
                "target": str(item.get("target") or "").strip(),
                "type": str(item.get("type") or "").strip(),
            }
            for item in structured_payload.get("relations", [])
            if isinstance(item, dict)
            and str(item.get("source") or "").strip()
            and str(item.get("target") or "").strip()
        ]
        record = {
            "window_id": window_id,
            "session_id": self._session_id,
            "start_time": chunk.get("start_time", ""),
            "end_time": chunk.get("end_time", ""),
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "entries": [
                {"timestamp": timestamp, "text": text}
                for timestamp, text in entries
            ],
            "stage_summary": (structured_payload.get("stage_summary") or "").strip(),
            "main_topic": main_topic,
            "extracted_topics": extracted_topics,
            "extracted_subtopics": extracted_subtopics,
            "extracted_concepts": extracted_concepts,
            "extracted_relations": extracted_relations,
            "facts": [
                item.strip()
                for item in structured_payload.get("facts", [])
                if isinstance(item, str) and item.strip()
            ],
            "examples": [
                item.strip()
                for item in structured_payload.get("examples", [])
                if isinstance(item, str) and item.strip()
            ],
            "candidate_question_links": [
                item.strip()
                for item in structured_payload.get("candidate_question_links", [])
                if isinstance(item, str) and item.strip()
            ],
            "linked_question_ids": [],
            "rolling_summary_after_window": self._rolling_summary.strip(),
            "flush_reason": chunk.get("flush_reason", ""),
            "summary_status": "failed" if error_message else "completed",
            "summary_reason": error_message,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        session_storage_service.write_session_json(os.path.join("windows", f"{window_id}.json"), record)
        return record

    async def _wait_for_summary_drain(self):
        for _ in range(80):
            with self._state_lock:
                if not self._summary_task_running and not self._window_queue:
                    return
            await asyncio.sleep(0.1)

    def _on_local_asr_text(self, text: str, is_final: bool):
        """
        本地 ASR 识别回调 - 每识别一句话就追加一行到转录文件。
        同时检测是否为学生提问句，若是则广播 question_detected 事件。
        """
        if not self.is_monitoring or self.is_paused or not text.strip():
            return

        timestamp = datetime.now().strftime("%H:%M:%S")

        with self._state_lock:
            appended, alert_text = self._append_or_merge_local_entry_locked(timestamp, text)
            if appended:
                self._flush_transcript_file()
                self._schedule_summary_locked()

        if not appended:
            return

        # 广播实时转录文本
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_alert({"type": "transcript_update", "text": alert_text, "timestamp": timestamp}),
                self._loop,
            )

        # 学生提问检测（快速预检，LLM 精确识别在 question_router 中）
        if self._is_question_sentence(alert_text) and self._loop:
            import time
            now = time.time()
            if now - self._last_question_time > self._question_cooldown:
                self._last_question_time = now
                question_candidate = self._extract_question_candidate(alert_text)
                detected_record = question_event_service.record_detected_question(
                    raw_text=question_candidate or alert_text,
                    trigger_time=timestamp,
                    confidence="low",
                )
                event = {
                    "type": "question_detected",
                    "question_id": detected_record.get("question_id", ""),
                    "text": question_candidate or alert_text,
                    "timestamp": timestamp,
                    "confidence": "low",  # 预检置信度低，需 LLM 确认
                }
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_alert(event), self._loop
                )

    def _on_asr_text(self, text: str, is_final: bool):
        """
        ASR 识别回调 (可能从非主线程调用) —— 用于线上流式 ASR。

        仅把最终稳定的句子写入转录文件。
        流式修正中的 partial 文本只暂存在内存中，停止监控时再兜底写入一次。
        检测到学生提问时广播 question_detected 事件。
        """
        if not self.is_monitoring or self.is_paused or not text.strip():
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        logger.info("[ASR] on_text (len=%d): %s", len(text), text[:60])

        alert_text = ""
        question_candidate = ""
        do_question_check = False

        with self._state_lock:
            cleaned = self._clean_asr_text(text)
            self._last_asr_text = cleaned

            appended_any = False
            partial_text = None
            if is_final:
                self._partial_line = None
                appended_any = self._append_entry_locked(timestamp, cleaned)
            elif self._is_meaningful_text(cleaned) and not self._is_near_duplicate_locked(cleaned):
                self._partial_line = (timestamp, cleaned)
                partial_text = cleaned

            if appended_any:
                self._flush_transcript_file()
                alert_text = cleaned
                question_candidate = self._extract_question_candidate(cleaned)
                do_question_check = True
                self._schedule_summary_locked()

        if do_question_check and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_alert({"type": "transcript_update", "text": alert_text, "is_final": True, "timestamp": timestamp}),
                self._loop,
            )
        elif partial_text and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_alert({"type": "transcript_update", "text": partial_text, "is_final": False, "timestamp": timestamp}),
                self._loop,
            )

        if do_question_check and self._is_question_sentence(question_candidate or alert_text) and self._loop:
            import time
            now = time.time()
            if now - self._last_question_time > self._question_cooldown:
                self._last_question_time = now
                detected_record = question_event_service.record_detected_question(
                    raw_text=question_candidate or alert_text,
                    trigger_time=timestamp,
                    confidence="low",
                )
                event = {
                    "type": "question_detected",
                    "question_id": detected_record.get("question_id", ""),
                    "text": question_candidate or alert_text,
                    "timestamp": timestamp,
                    "confidence": "low",
                }
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_alert(event), self._loop
                )
