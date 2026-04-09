"""
窗口转录清洗服务
================
对 30 秒窗口文本做规则清洗，并保存可回放的前后对比日志。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Iterable

from services.session_storage_service import session_storage_service


class TranscriptCleaner:
    """对窗口原文做轻量规则清洗。"""

    MANAGEMENT_PATTERNS = [
        r"翻到第.{0,8}页",
        r"看(?:一下)?黑板",
        r"先看(?:这里|这道题|这个图)?",
        r"抄(?:一下|下来)?",
        r"先停一下",
        r"稍等一下",
        r"听我说",
        r"先记一下",
        r"注意(?:一下)?",
        r"这一题先(?:不看|放一下)",
    ]

    FILLER_PATTERNS = [
        r"(?:^|[\s，,。！？!?；;、])(?:嗯+|呃+|额+|啊+|哦+|诶+)(?=$|[\s，,。！？!?；;、])",
        r"^(?:(?:那个|这个|就是|然后|所以|那么|然后呢|就是说|对吧|是吧)[，,。！？!?；;、\s]*)+",
    ]

    def _normalize_text(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", (text or "").strip())
        normalized = normalized.replace("…", ".").replace("···", ".")
        normalized = re.sub(r"[~～·•]+", " ", normalized)
        normalized = re.sub(r"([，,。！？!?；;、])\1+", r"\1", normalized)
        normalized = re.sub(r"\s*([，,。！？!?；;、])\s*", r"\1", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _collapse_repetition(self, text: str) -> str:
        compact = text
        previous = ""
        while compact != previous:
            previous = compact
            compact = re.sub(r"([A-Za-z0-9\u4e00-\u9fff]{1,4})(?:\1){1,}", r"\1", compact)
            compact = re.sub(r"\b([A-Za-z0-9]{1,4})(?:\s+\1){1,}\b", r"\1", compact)
        return compact

    def _strip_management_phrases(self, text: str) -> str:
        cleaned = text
        for pattern in self.MANAGEMENT_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        return cleaned

    def _strip_fillers(self, text: str) -> str:
        cleaned = text
        for pattern in self.FILLER_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"(?:[，,。！？!?；;、\s]+)(?:嗯+|呃+|额+|啊+|哦+|诶+)$",
            "",
            cleaned,
        )
        return cleaned

    def _is_meaningful(self, text: str) -> bool:
        compact = re.sub(r"[\s\W_]+", "", text or "", flags=re.UNICODE)
        return len(compact) >= 4 and bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", compact))

    def clean_text(self, text: str) -> str:
        cleaned = self._normalize_text(text)
        if not cleaned:
            return ""

        cleaned = re.sub(
            r"[\[(（【<〈].{0,8}(?:noise|静音|噪音|杂音|掌声|咳嗽|笑声|听不清).{0,4}[\])）】>〉]",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = self._strip_management_phrases(cleaned)
        cleaned = self._strip_fillers(cleaned)
        cleaned = self._collapse_repetition(cleaned)
        cleaned = self._normalize_text(cleaned)
        return cleaned.strip(" ，,。！？!?；;、")

    def clean_window_entries(self, entries: Iterable[tuple[str, str]]) -> dict:
        raw_lines: list[str] = []
        kept_lines: list[str] = []
        dropped_lines: list[dict[str, str]] = []

        for timestamp, text in entries:
            raw_line = f"[{timestamp}] {text}".strip()
            raw_lines.append(raw_line)
            cleaned = self.clean_text(text)
            if not cleaned or not self._is_meaningful(cleaned):
                dropped_lines.append(
                    {
                        "timestamp": timestamp,
                        "raw_text": text,
                        "reason": "empty_after_rules",
                    }
                )
                continue
            kept_lines.append(f"[{timestamp}] {cleaned}")

        raw_text = "\n".join(raw_lines).strip()
        rule_cleaned_text = "\n".join(kept_lines).strip()
        return {
            "raw_text": raw_text,
            "rule_cleaned_text": rule_cleaned_text,
            "kept_line_count": len(kept_lines),
            "dropped_line_count": len(dropped_lines),
            "dropped_lines": dropped_lines,
        }

    def persist_window_debug(
        self,
        *,
        window_id: str,
        raw_text: str,
        rule_cleaned_text: str,
        model_payload: dict | None = None,
        extra: dict | None = None,
    ) -> None:
        debug_dir = session_storage_service.ensure_session_subdir("windows", "debug")
        if not debug_dir or not window_id:
            return

        raw_path = os.path.join(debug_dir, f"{window_id}.raw.txt")
        rule_path = os.path.join(debug_dir, f"{window_id}.rule_cleaned.txt")
        model_path = os.path.join(debug_dir, f"{window_id}.model_cleaned.json")

        with open(raw_path, "w", encoding="utf-8") as file_obj:
            file_obj.write((raw_text or "").strip())
        with open(rule_path, "w", encoding="utf-8") as file_obj:
            file_obj.write((rule_cleaned_text or "").strip())
        if model_payload is not None:
            with open(model_path, "w", encoding="utf-8") as file_obj:
                json.dump(model_payload, file_obj, ensure_ascii=False, indent=2)

        log_dir = session_storage_service.ensure_session_subdir("debug")
        if not log_dir:
            return

        log_path = os.path.join(log_dir, "cleaner.log")
        payload = {
            "window_id": window_id,
            "raw_chars": len(raw_text or ""),
            "rule_cleaned_chars": len(rule_cleaned_text or ""),
            "model_cleaned_chars": len((model_payload or {}).get("cleaned_text", "")),
            "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        if extra:
            payload.update(extra)
        with open(log_path, "a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(payload, ensure_ascii=False) + "\n")


transcript_cleaner = TranscriptCleaner()
