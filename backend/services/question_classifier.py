"""
课堂问题类型识别
================
在正式生成答案前，对学生问题做轻量分类。
"""

from __future__ import annotations

import re


class QuestionClassifier:
    QUESTION_SIGNALS = (
        r"[？?]$",
        r"(什么|为什么|怎么|如何|是不是|对不对|能不能|可以吗|吗$|呢$)",
        r"(不懂|不明白|不理解|没听懂|能解释|能说明)",
    )

    def classify(self, detected_question: str = "", transcript: str = "") -> dict[str, str]:
        candidate = self._extract_candidate_question(detected_question, transcript)
        question_type = self._infer_question_type(candidate)
        return {
            "candidate_question": candidate,
            "question_type": question_type,
        }

    def _extract_candidate_question(self, detected_question: str, transcript: str) -> str:
        direct = self._clean_text(detected_question)
        if direct:
            return direct

        for raw_line in reversed((transcript or "").splitlines()):
            cleaned = self._clean_line(raw_line)
            if not cleaned:
                continue
            if any(re.search(pattern, cleaned) for pattern in self.QUESTION_SIGNALS):
                return cleaned

        return ""

    def _infer_question_type(self, text: str) -> str:
        cleaned = self._clean_text(text)
        compact = re.sub(r"[\s\W_]+", "", cleaned, flags=re.UNICODE)

        if not cleaned or len(compact) < 4:
            return "信息不足型"

        if re.search(r"(区别|不同|联系|比较|对比|怎么区分|分别|有何不同)", cleaned):
            return "区分型"

        if re.search(r"(为什么|为何|原因|怎么会|为何会|凭什么|为什么会)", cleaned):
            return "原因型"

        if re.search(r"(怎么算|怎么做|如何做|求|解|证明|列式|计算|过程|步骤|方法|代入)", cleaned):
            return "解题型"

        if re.search(r"(什么是|是什么意思|是什么|指什么|含义|概念|定义|怎么理解|解释一下)", cleaned):
            return "概念型"

        if re.search(r"(这个|那个|这里|这一步|上一题|这一题|它为什么|它怎么)", cleaned) and len(compact) <= 10:
            return "信息不足型"

        return "概念型"

    def _clean_line(self, raw_line: str) -> str:
        cleaned = re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s*", "", raw_line or "")
        return self._clean_text(cleaned)

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip())
