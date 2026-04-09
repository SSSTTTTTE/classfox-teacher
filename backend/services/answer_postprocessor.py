"""
答案后处理模块
==============
统一清洗课堂短答，减少小模型输出里的 AI 腔、客套、重复句和跑题尾巴。
"""

from __future__ import annotations

import re


class AnswerPostProcessor:
    """对课堂回答做最小但稳定的规则化处理。"""

    _AI_PATTERNS = (
        r"作为(?:一个)?AI(?:助手)?[，,:： ]*",
        r"我是(?:一个)?AI(?:助手)?[，,:： ]*",
        r"根据(?:你|题目|题干|上述)描述[，,:： ]*",
        r"我认为[，,:： ]*",
    )

    _LEADING_FILLERS = (
        r"^(好的|好|嗯|那|这里|这个问题|我们先看一下|下面我来|我来)[，,:： ]*",
    )

    _TRAILING_FILLERS = (
        r"(希望这样能帮助你理解|希望对你有帮助|如果你还有问题.*|如果还想继续问.*)$",
    )

    _SPEAKABLE_REPLACEMENTS = (
        ("首先", "先"),
        ("其次", "再"),
        ("因此", "所以"),
        ("由于", "因为"),
        ("综上所述", "所以"),
        ("由此可见", "所以"),
        ("换言之", "换句话说"),
        ("简而言之", ""),
        ("总的来说", ""),
        ("总体来说", ""),
    )

    def clean(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        cleaned = cleaned.replace("\u3000", " ")

        for pattern in self._AI_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        for pattern in self._LEADING_FILLERS:
            cleaned = re.sub(pattern, "", cleaned)

        for pattern in self._TRAILING_FILLERS:
            cleaned = re.sub(pattern, "", cleaned)

        cleaned = cleaned.strip(" \n\t-:：")
        return cleaned

    def make_speakable(self, text: str) -> str:
        cleaned = self.clean(text)
        for source, target in self._SPEAKABLE_REPLACEMENTS:
            cleaned = cleaned.replace(source, target)
        cleaned = re.sub(r"^(所以|那|这里)[，,:：]\s*", "", cleaned)
        return cleaned.strip()

    def split_sentences(self, text: str) -> list[str]:
        cleaned = self.make_speakable(text)
        if not cleaned:
            return []

        parts = re.split(r"(?<=[。！？!?；;])\s*", cleaned)
        sentences = [part.strip(" \n\t") for part in parts if part and part.strip()]
        return self.dedupe_sentences(sentences) or [cleaned]

    def dedupe_sentences(self, sentences: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for sentence in sentences:
            normalized = re.sub(r"[\s，,。！？!?；;、:：]", "", sentence)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(sentence)
        return deduped

    def trim_chars(self, text: str, limit: int) -> str:
        cleaned = self.clean(text)
        if len(cleaned) <= limit:
            return cleaned
        trimmed = cleaned[:limit].rstrip("，,、；;：: ")
        return f"{trimmed}…"

    def finalize(
        self,
        text: str,
        *,
        max_sentences: int,
        char_limit: int,
        prefer_single: bool = False,
        default: str = "",
    ) -> str:
        sentences = self.split_sentences(text)
        if not sentences:
            return default
        kept = sentences[:1] if prefer_single else sentences[:max_sentences]
        merged = "".join(kept)
        finalized = self.trim_chars(merged, char_limit)
        return finalized or default


answer_postprocessor = AnswerPostProcessor()
