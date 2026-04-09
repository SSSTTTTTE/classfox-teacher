"""
LLM 服务（教师版）
==================
v1.1.1 起，这里不再直接承载模型 SDK，而是作为课堂推理编排层：
- 保留业务语义和返回结构
- 将实际本地模型调用下沉到 OllamaService
- 默认保障短答与课后总结链路，实时总结保留接口但默认关闭
"""

from __future__ import annotations

import json
import logging
import os
import re
from time import perf_counter
from typing import Any, Awaitable, Callable, Optional

from dotenv import load_dotenv

from services.answer_postprocessor import answer_postprocessor
from services.local_llm_observability import local_llm_observability
from services.ollama_service import OllamaService
from services.prompt_builder import (
    SPEAKABLE_CONSTRAINTS,
    WINDOW_RELATION_TYPES,
    build_final_summary_prompts,
    build_window_structuring_prompts,
    build_question_type_prompt,
    build_question_type_template,
    build_subject_prompt,
)
from services.session_storage_service import session_storage_service

load_dotenv()

logger = logging.getLogger(__name__)

MAX_PROMPT_HISTORY_ITEMS = 4
MAX_PROMPT_HISTORY_CHARS = 280
MAX_PROMPT_TRANSCRIPT_LINES = 8
MAX_PROMPT_TRANSCRIPT_CHARS = 520
MAX_PROMPT_MATERIAL_CHARS = 420
MAX_PROMPT_SUMMARY_CHARS = 260


def _read_bool_env(key: str, default: bool) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class LLMService:
    """课堂推理编排层。"""

    FALLBACK_SCHEMA = {
        "type": "object",
        "properties": {
            "student_question": {"type": "string"},
            "one_line_answer": {"type": "string"},
            "teacher_speakable_answer": {"type": "string"},
            "short_explanation": {"type": "string"},
            "confidence": {"type": "string"},
            "answer_mode": {"type": "string"},
        },
        "required": [
            "student_question",
            "one_line_answer",
            "teacher_speakable_answer",
            "short_explanation",
            "confidence",
            "answer_mode",
        ],
    }

    SUMMARY_CARD_SCHEMA = {
        "type": "object",
        "properties": {
            "summary_text": {"type": "string"},
            "section_title": {"type": "string"},
            "points": {"type": "array", "items": {"type": "string"}},
            "flow_title": {"type": "string"},
            "flow_steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary_text", "section_title", "points", "flow_title", "flow_steps"],
    }

    WINDOW_STRUCTURED_SCHEMA = {
        "type": "object",
        "properties": {
            "cleaned_text": {"type": "string"},
            "stage_summary": {"type": "string"},
            "main_topic": {"type": "string"},
            "subtopics": {"type": "array", "items": {"type": "string"}},
            "concepts": {"type": "array", "items": {"type": "string"}},
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "type": {"type": "string"},
                    },
                    "required": ["source", "target", "type"],
                },
            },
            "facts": {"type": "array", "items": {"type": "string"}},
            "examples": {"type": "array", "items": {"type": "string"}},
            "candidate_question_links": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "cleaned_text",
            "stage_summary",
            "main_topic",
            "subtopics",
            "concepts",
            "relations",
            "facts",
            "examples",
            "candidate_question_links",
        ],
    }

    def __init__(self):
        self._ollama = OllamaService()
        self.chat_model = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:1.5b").strip() or "qwen2.5:1.5b"
        self.final_summary_model = (
            os.getenv("OLLAMA_FINAL_SUMMARY_MODEL", "gemma4:e4b").strip() or "gemma4:e4b"
        )
        self.realtime_summary_enabled = _read_bool_env("OLLAMA_REALTIME_SUMMARY_ENABLED", False)
        self.realtime_summary_model = (
            os.getenv("OLLAMA_REALTIME_SUMMARY_MODEL", "").strip() or self.chat_model
        )
        self.timeout = self._ollama.timeout
        self.max_tokens = self._ollama.default_max_tokens
        self.temperature = self._ollama.default_temperature

    def runtime_config(self) -> dict[str, Any]:
        return {
            "base_url": self._ollama.base_url,
            "chat_model": self.chat_model,
            "final_summary_model": self.final_summary_model,
            "realtime_summary_enabled": self.realtime_summary_enabled,
            "realtime_summary_model": self.realtime_summary_model,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

    def get_evaluation_snapshot(self, *, recent_limit: int = 20) -> dict[str, Any]:
        return local_llm_observability.get_snapshot(recent_limit=recent_limit)

    def _record_generation_event(
        self,
        *,
        task: str,
        model_name: str,
        started_at: float,
        input_chars: int,
        primary_output: str = "",
        question_preview: str = "",
        subject: str = "",
        question_type: str = "",
        success: bool = True,
        skipped: bool = False,
        error: str = "",
        clipped: bool = False,
        confidence: str = "",
        answer_mode: str = "",
        first_answer_ms: Optional[float] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        payload: dict[str, Any] = {
            "task": task,
            "model": model_name,
            "success": success,
            "skipped": skipped,
            "input_chars": int(input_chars),
            "output_chars": len(primary_output or ""),
            "primary_output": primary_output,
            "question_preview": question_preview,
            "subject": subject,
            "question_type": question_type,
            "confidence": confidence,
            "answer_mode": answer_mode,
            "clipped": bool(clipped),
            "total_duration_ms": duration_ms,
            "first_answer_ms": round(first_answer_ms, 2) if first_answer_ms is not None else duration_ms,
            "realtime_summary_enabled": self.realtime_summary_enabled,
            "error": error,
        }
        if extra:
            payload.update(extra)
        local_llm_observability.record_event(payload)

    def _history_to_text(self, history: Optional[list[dict[str, Any]]]) -> str:
        safe_history = history or []
        history_lines: list[str] = []
        total_chars = 0

        for item in safe_history[-MAX_PROMPT_HISTORY_ITEMS:]:
            content = self._clean_text(item.get("content", ""))
            if not content:
                continue
            role = item.get("role", "user")
            clipped = self._trim_chars(content, 70)
            total_chars += len(clipped)
            if total_chars > MAX_PROMPT_HISTORY_CHARS:
                break
            history_lines.append(f"{role}: {clipped}")

        return "\n".join(history_lines) or "暂无历史追问"

    def _normalize_confidence(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized if normalized in {"high", "low"} else "low"

    def _normalize_answer_mode(self, value: str, confidence: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized in {"direct", "cautious"}:
            return normalized
        return "cautious" if confidence == "low" else "direct"

    def _clean_text(self, text: str) -> str:
        return answer_postprocessor.clean(text)

    def _make_speakable(self, text: str) -> str:
        return answer_postprocessor.make_speakable(text)

    def _split_sentences(self, text: str) -> list[str]:
        return answer_postprocessor.split_sentences(text)

    def _trim_chars(self, text: str, limit: int) -> str:
        return answer_postprocessor.trim_chars(text, limit)

    def _clip_block(self, text: str, *, char_limit: int) -> str:
        cleaned = self._clean_text(text)
        if not cleaned:
            return ""
        return self._trim_chars(cleaned, char_limit)

    def _render_state_items(self, values: list[Any], key: str, *, limit: int) -> str:
        rendered: list[str] = []
        for item in values[-limit:]:
            if isinstance(item, dict):
                text = self._clean_text(str(item.get(key, "")))
            else:
                text = self._clean_text(str(item))
            if text:
                rendered.append(f"- {self._trim_chars(text, 72)}")
        return "\n".join(rendered) or "- 暂无"

    def _render_transcript_window(self, classroom_state: Optional[dict[str, Any]], fallback_text: str = "") -> str:
        state_window = (classroom_state or {}).get("recent_transcript_window", [])
        lines: list[str] = []

        for item in state_window[-MAX_PROMPT_TRANSCRIPT_LINES:]:
            if not isinstance(item, dict):
                continue
            text = self._clean_text(str(item.get("text", "")))
            if not text:
                continue
            timestamp = self._clean_text(str(item.get("timestamp", "")))
            prefix = f"[{timestamp}] " if timestamp else ""
            lines.append(f"{prefix}{self._trim_chars(text, 72)}")

        if lines:
            return "\n".join(lines)

        clipped = self._clip_block(
            fallback_text,
            char_limit=MAX_PROMPT_TRANSCRIPT_CHARS,
        )
        return clipped or "暂无最近课堂记录"

    def _render_classroom_state(self, classroom_state: Optional[dict[str, Any]]) -> str:
        state = classroom_state or {}
        if not state:
            return "暂无结构化课堂状态"

        summary_cards: list[str] = []
        for card in state.get("summary_cards", []) or []:
            if not isinstance(card, dict):
                continue
            title = self._clean_text(str(card.get("section_title") or ""))
            points = [
                self._clean_text(str(item))
                for item in (card.get("points", []) or [])
                if str(item).strip()
            ]
            if not title and not points:
                continue
            points_text = " / ".join(points[:3]) if points else ""
            if title and points_text:
                summary_cards.append(f"- {title}：{points_text}")
            elif title:
                summary_cards.append(f"- {title}")
            elif points_text:
                summary_cards.append(f"- {points_text}")

        blocks = [
            f"当前主题：{self._clip_block(str(state.get('current_topic', '')), char_limit=60) or '未提炼'}",
            f"主题摘要：{self._clip_block(str(state.get('topic_summary', '')), char_limit=MAX_PROMPT_SUMMARY_CHARS) or '暂无'}",
            f"实时总结要点：\n{chr(10).join(summary_cards) if summary_cards else '- 暂无'}",
            f"最近学生问题：\n{self._render_state_items(state.get('recent_questions', []), 'question', limit=3)}",
            f"最近老师回答：\n{self._render_state_items(state.get('recent_answers', []), 'answer', limit=3)}",
            f"学生卡点：\n{self._render_state_items(state.get('student_confusion_points', []), '', limit=3)}",
            f"最近问题类型：{self._clean_text(str(state.get('question_type', ''))) or '未记录'}",
            f"本地模型状态：{'ready' if state.get('llm_ready') else 'not_ready'}",
        ]
        return "\n".join(blocks)

    def _limit_sentences(
        self,
        text: str,
        *,
        max_sentences: int,
        char_limit: int,
        prefer_single: bool = False,
    ) -> str:
        sentences = self._split_sentences(text)
        if not sentences:
            return ""
        kept = sentences[:1] if prefer_single else sentences[:max_sentences]
        merged = "".join(kept)
        return self._trim_chars(merged, char_limit)

    def _has_caution_marker(self, text: str) -> bool:
        return any(
            marker in (text or "")
            for marker in ("信息不足", "还不够完整", "暂时只能", "先按现有信息", "大概率", "可能是", "先这样讲")
        )

    def _ensure_cautious_trace(self, text: str, *, short: bool) -> str:
        cleaned = self._clean_text(text)
        if not cleaned:
            return "信息不足，先按现有内容讲。"
        if self._has_caution_marker(cleaned):
            return cleaned
        prefix = "先按现有信息看，" if short else "信息还不够完整，先按现有内容判断："
        return f"{prefix}{cleaned}"

    def _finalize_fallback_payload(self, payload: dict[str, Any]) -> dict[str, str]:
        confidence = self._normalize_confidence(payload.get("confidence", "low"))
        answer_mode = self._normalize_answer_mode(payload.get("answer_mode", ""), confidence)
        student_question = self._clean_text(payload.get("student_question") or "无法识别问题") or "无法识别问题"
        one_line_answer = self._limit_sentences(
            payload.get("one_line_answer")
            or payload.get("teacher_speakable_answer")
            or payload.get("one_sentence_answer")
            or "先按现有信息讲。",
            max_sentences=1,
            char_limit=36,
            prefer_single=True,
        )
        teacher_speakable_answer = self._limit_sentences(
            payload.get("teacher_speakable_answer")
            or payload.get("one_line_answer")
            or payload.get("one_sentence_answer")
            or "我先按现有信息讲这一步。",
            max_sentences=2,
            char_limit=54,
        )
        short_explanation = self._limit_sentences(
            payload.get("short_explanation") or payload.get("detail") or "",
            max_sentences=3,
            char_limit=96,
        )

        if confidence == "low" or answer_mode == "cautious":
            answer_mode = "cautious"
            one_line_answer = self._limit_sentences(
                self._ensure_cautious_trace(one_line_answer, short=True),
                max_sentences=1,
                char_limit=36,
                prefer_single=True,
            )
            teacher_speakable_answer = self._limit_sentences(
                self._ensure_cautious_trace(
                    teacher_speakable_answer or "先按现有信息讲这一层。",
                    short=False,
                ),
                max_sentences=2,
                char_limit=54,
            )
            short_explanation = self._limit_sentences(
                self._ensure_cautious_trace(
                    short_explanation or "请老师先确认学生具体在问哪一部分。",
                    short=False,
                ),
                max_sentences=3,
                char_limit=96,
            )
        else:
            answer_mode = "direct"

        return {
            "student_question": student_question,
            "one_line_answer": one_line_answer or "先按现有信息讲。",
            "teacher_speakable_answer": teacher_speakable_answer or "我先按现有信息讲这一步。",
            "short_explanation": short_explanation,
            "confidence": confidence,
            "answer_mode": answer_mode,
            # 兼容旧前端字段，待后续清理。
            "one_sentence_answer": teacher_speakable_answer or "我先按现有信息讲这一步。",
            "detail": short_explanation,
        }

    def _finalize_brief_answer(self, text: str, *, char_limit: int = 120) -> str:
        cleaned = answer_postprocessor.finalize(
            text,
            max_sentences=3,
            char_limit=char_limit,
            default="当前信息还不够，我先按现有内容回答。",
        )
        return cleaned or "当前信息还不够，我先按现有内容回答。"

    def _normalize_string_list(self, values: Any, *, limit: int) -> list[str]:
        normalized: list[str] = []
        for item in values or []:
            cleaned = self._clean_text(str(item))
            if not cleaned or cleaned in normalized:
                continue
            normalized.append(cleaned)
            if len(normalized) >= limit:
                break
        return normalized

    def _normalize_relations(self, values: Any) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in values or []:
            if not isinstance(item, dict):
                continue
            source = self._clean_text(str(item.get("source") or ""))
            target = self._clean_text(str(item.get("target") or ""))
            relation_type = self._clean_text(str(item.get("type") or ""))
            if not source or not target:
                continue
            if relation_type not in WINDOW_RELATION_TYPES:
                relation_type = "includes"
            relation = {"source": source, "target": target, "type": relation_type}
            if relation not in normalized:
                normalized.append(relation)
        return normalized[:8]

    def _fallback_window_payload(self, *, raw_window_text: str, rule_cleaned_text: str) -> dict[str, Any]:
        cleaned_text = rule_cleaned_text.strip() or self._clip_block(raw_window_text, char_limit=220)
        summary_source = cleaned_text or raw_window_text
        stage_summary = self._trim_chars(summary_source, 120) if summary_source else ""
        main_topic = ""
        if cleaned_text:
            first_line = cleaned_text.splitlines()[0]
            main_topic = self._trim_chars(first_line, 32)
        return {
            "cleaned_text": cleaned_text,
            "stage_summary": stage_summary,
            "main_topic": main_topic,
            "subtopics": [],
            "concepts": [],
            "relations": [],
            "facts": [],
            "examples": [],
            "candidate_question_links": [],
        }

    def _finalize_window_payload(
        self,
        payload: dict[str, Any],
        *,
        raw_window_text: str,
        rule_cleaned_text: str,
    ) -> dict[str, Any]:
        fallback = self._fallback_window_payload(
            raw_window_text=raw_window_text,
            rule_cleaned_text=rule_cleaned_text,
        )
        cleaned_text = self._clean_text(str(payload.get("cleaned_text") or "")) or fallback["cleaned_text"]
        stage_summary = self._clean_text(str(payload.get("stage_summary") or "")) or fallback["stage_summary"]
        main_topic = self._clean_text(str(payload.get("main_topic") or "")) or fallback["main_topic"]
        subtopics = self._normalize_string_list(payload.get("subtopics"), limit=6)
        concepts = self._normalize_string_list(payload.get("concepts"), limit=8)
        facts = self._normalize_string_list(payload.get("facts"), limit=6)
        examples = self._normalize_string_list(payload.get("examples"), limit=4)
        candidate_question_links = self._normalize_string_list(payload.get("candidate_question_links"), limit=6)
        relations = self._normalize_relations(payload.get("relations"))

        if not stage_summary and cleaned_text:
            stage_summary = self._trim_chars(cleaned_text, 120)
        if not main_topic:
            main_topic = (subtopics[:1] or concepts[:1] or [stage_summary[:24]])[0].strip() if stage_summary else ""

        return {
            "cleaned_text": cleaned_text,
            "stage_summary": stage_summary,
            "main_topic": main_topic,
            "subtopics": subtopics,
            "concepts": concepts,
            "relations": relations,
            "facts": facts,
            "examples": examples,
            "candidate_question_links": candidate_question_links,
        }

    async def _generate_text(
        self,
        *,
        prompt: str,
        model_name: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        return await self._ollama.generate_answer(
            prompt=prompt,
            model_name=model_name,
            options={
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

    async def _generate_json(
        self,
        *,
        prompt: str,
        model_name: str,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._ollama.generate_json(
            prompt=prompt,
            model_name=model_name,
            schema_hint=schema,
            options={
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

    async def check_local_health(self) -> dict[str, Any]:
        payload = await self._ollama.check_ollama_health(
            required_models=[self.chat_model, self.final_summary_model]
        )
        available_models = set(payload.get("models", []))
        return {
            **payload,
            "chat_model": self.chat_model,
            "final_summary_model": self.final_summary_model,
            "realtime_summary_enabled": self.realtime_summary_enabled,
            "realtime_summary_model": self.realtime_summary_model,
            "chat_model_available": self.chat_model in available_models,
            "final_summary_model_available": self.final_summary_model in available_models,
            "realtime_summary_model_available": (
                self.realtime_summary_model in available_models
                if self.realtime_summary_enabled
                else False
            ),
        }

    async def warmup_local_models(
        self,
        model_names: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        warmed_models: set[str] = set()
        targets = model_names or [self.chat_model, self.final_summary_model]
        for model_name in targets:
            if model_name in warmed_models:
                continue
            warmed_models.add(model_name)
            results.append(await self._ollama.warmup_model(model_name))
        return {"status": "success", "models": results}

    async def warmup_chat_model(self) -> dict[str, Any]:
        return await self.warmup_local_models([self.chat_model])

    async def generate_fallback_answer(
        self,
        transcript: str,
        material: str,
        detected_question: Optional[str] = None,
        subject: str = "",
        course_name: str = "",
        question_type: str = "",
        classroom_state: Optional[dict[str, Any]] = None,
    ) -> dict:
        """
        学生提问 → 教师兜底答案

        根据最近课堂转录提取学生提问，生成一句话兜底答案 + 可展开的详细说明。
        如果提供 detected_question，优先将其作为学生问题提示 LLM。

        Returns:
            dict with keys:
            student_question, one_line_answer, teacher_speakable_answer,
            short_explanation, confidence
        """
        use_fast_path = bool((detected_question or "").strip())
        used_subject, subject_prompt = build_subject_prompt(subject, course_name)
        question_type_prompt = build_question_type_prompt(question_type)
        question_type_template = build_question_type_template(question_type)
        subject_block = used_subject or "未指定"
        course_block = (course_name or "").strip() or "未指定"
        question_preview = (detected_question or "").strip()
        transcript_block = self._render_transcript_window(classroom_state, transcript)
        material_block = self._clip_block(material, char_limit=MAX_PROMPT_MATERIAL_CHARS) or "暂无参考资料"
        classroom_state_block = self._render_classroom_state(classroom_state)

        if use_fast_path:
            system_prompt = f"""你是老师的课堂实时兜底助手，只服务“学生刚提问，老师马上要接话”这一瞬间。

角色：
- 站在老师身后，帮老师立刻组织能说出口的话

目标：
- 先把已识别到的学生问题整理成更清楚、更完整、但不改变原意的提问
- 再围绕这个优化后的问题直接作答
- 先给一句老师可直接转述的课堂短答
- 再给 1 到 3 句补充说明
- 判断当前信息是否足够可靠

风格：
- 口语化、短句、像老师当场接话
- 优先先回答核心结论，再补一句点拨
- 只说课堂上现在能用的话
{SPEAKABLE_CONSTRAINTS}
{subject_prompt}
- 当前问题类型提示：{question_type_prompt}
{question_type_template}

禁止项：
- 不要长篇分析
- 不要说“作为 AI”“我认为”“根据题目描述”
- 不要编造题干、数据、公式条件
- 信息不够时不要硬猜，不要给绝对结论
- 如果问题已经足够明确，不要说“先按现有信息看”“大概率”“可能是”这类回避话
- teacher_speakable_answer 必须紧扣优化后的 student_question，不能答非所问

信息不足策略：
- 若问题本身不完整、缺少题目条件、或无法确定学生具体所问，confidence 必须设为 low
- answer_mode 设为 cautious
- one_line_answer 用“先按现有信息看 / 大概率 / 先这样讲”这一类谨慎说法
- teacher_speakable_answer 给老师一到两句可直接接上的课堂表达
- short_explanation 明确指出缺的关键信息，并给老师一个临时可讲的保守回答

明确问题时的处理：
- 如果已检测问题本身就是明确问题，例如在问时间、定义、原因、作用、区别、人物、事件结果，student_question 只做语言整理，不要改成别的问题
- 这类明确问题默认应直接回答，confidence 设为 high，answer_mode 设为 direct
- teacher_speakable_answer 第一分句就要正面回答问题，例如时间题先说具体时间，定义题先说核心定义

输出格式：
- 只输出 JSON，不要 markdown
- student_question: 保持学生原意，整理成更清楚的提问
- one_line_answer: 只允许 1 句，优先 10 到 28 个字，能完整看出结论
- teacher_speakable_answer: 1 到 2 句，老师可直接照着说
- short_explanation: 1 到 3 句，供老师展开说
- confidence: 只能是 high 或 low
- answer_mode: 只能是 direct 或 cautious"""

            user_prompt = f"""【当前科目】
{subject_block}

【当前课程】
{course_block}

【问题类型】
{question_type or "未分类"}

【结构化课堂状态】
{classroom_state_block}

【最近课堂短窗口】
{transcript_block}

【参考资料摘要】
{material_block}

【已检测到的学生提问】
{detected_question}

请先把已检测问题整理成老师现在要回答的标准问题，再直接生成兜底答案。"""
            max_tokens = 220
        else:
            system_prompt = f"""你是老师的课堂实时兜底助手，要根据最近课堂转录帮老师接住学生提问。

角色：
- 课堂短答助手，不是百科讲解员

目标：
1. 从转录里提取学生刚才真正的问题
2. 生成一句老师可直接说出口的短答
3. 再补 1 到 3 句解释，方便老师展开
4. 判断信息是否足够

风格：
- 像老师上课时说话，短、稳、直接
- 优先先回答，再补一句点拨
- 适合初中、高中、培训课堂现场转述
{SPEAKABLE_CONSTRAINTS}
{subject_prompt}
- 当前问题类型提示：{question_type_prompt}
{question_type_template}

禁止项：
- 不要输出推理过程
- 不要用书面腔套话
- 不要自称 AI
- 不要在信息不全时乱猜

信息不足策略：
- 转录里如果听不清、上下文断裂、题目条件不全、或无法确定学生具体问题，confidence 必须设为 low
- answer_mode 设为 cautious
- one_line_answer 用保守表达，不要绝对化
- teacher_speakable_answer 保持老师上课能直接说出口
- short_explanation 说明缺少什么信息，并给出临时可讲的稳妥回答

输出格式：
- 只输出 JSON，不要 markdown
- one_line_answer 只允许 1 句
- teacher_speakable_answer 只允许 1 到 2 句
- short_explanation 只允许 1 到 3 句
- confidence 只能是 high 或 low
- answer_mode 只能是 direct 或 cautious"""

            hint = f"\n\n【已检测到的学生提问】\n{detected_question}" if detected_question else ""
            user_prompt = f"""【当前科目】
{subject_block}

【当前课程】
{course_block}

【问题类型】
{question_type or "未分类"}

【结构化课堂状态】
{classroom_state_block}

【课堂转录短窗口】
{transcript_block}

【参考资料摘要】
{material_block}{hint}

请提取学生的问题并生成兜底答案。"""
            max_tokens = 320

        started_at = perf_counter()
        input_chars = len(system_prompt) + len(user_prompt)

        try:
            raw_result = await self._generate_json(
                prompt=user_prompt,
                model_name=self.chat_model,
                system_prompt=system_prompt,
                temperature=0.2 if use_fast_path else 0.3,
                max_tokens=max_tokens,
                schema=self.FALLBACK_SCHEMA,
            )
            finalized = self._finalize_fallback_payload(raw_result)
            clipped = (
                finalized.get("teacher_speakable_answer", "")
                != self._clean_text(raw_result.get("teacher_speakable_answer", ""))
                or finalized.get("short_explanation", "")
                != self._clean_text(raw_result.get("short_explanation", ""))
                or finalized.get("one_line_answer", "")
                != self._clean_text(raw_result.get("one_line_answer", ""))
            )
            self._record_generation_event(
                task="fallback_answer",
                model_name=self.chat_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=finalized.get("teacher_speakable_answer", ""),
                question_preview=question_preview or finalized.get("student_question", ""),
                subject=used_subject,
                question_type=question_type,
                clipped=clipped,
                confidence=finalized.get("confidence", ""),
                answer_mode=finalized.get("answer_mode", ""),
            )
            return {
                **finalized,
                "question_type": question_type,
                "used_subject": used_subject,
            }
        except Exception as e:
            logger.exception("生成课堂短答失败")
            fallback_payload = {
                "student_question": "本地模型调用失败",
                "one_line_answer": "请检查模型状态",
                "teacher_speakable_answer": "请先检查 Ollama 状态。",
                "short_explanation": self._limit_sentences(str(e), max_sentences=2, char_limit=96),
                "confidence": "low",
                "answer_mode": "cautious",
                "question_type": question_type,
                "used_subject": used_subject,
                "one_sentence_answer": "请先检查 Ollama 状态。",
                "detail": self._limit_sentences(str(e), max_sentences=2, char_limit=96),
            }
            self._record_generation_event(
                task="fallback_answer",
                model_name=self.chat_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=fallback_payload["teacher_speakable_answer"],
                question_preview=question_preview,
                subject=used_subject,
                question_type=question_type,
                success=False,
                error=str(e),
                confidence="low",
                answer_mode="cautious",
            )
            return fallback_payload

    async def answer_followup_question(
        self,
        student_question: str,
        fallback_answer: str,
        transcript: str,
        material: str,
        followup: str,
        history: Optional[list] = None,
        subject: str = "",
        course_name: str = "",
        classroom_state: Optional[dict[str, Any]] = None,
    ) -> dict:
        """围绕兜底答案继续追问（教师视角）。"""
        history_text = self._history_to_text(history)
        used_subject, subject_prompt = build_subject_prompt(subject, course_name)
        classroom_state_block = self._render_classroom_state(classroom_state)
        transcript_block = self._render_transcript_window(classroom_state, transcript)
        material_block = self._clip_block(material, char_limit=MAX_PROMPT_MATERIAL_CHARS) or "暂无参考资料"

        system_prompt = f"""你是老师的课堂追问助手，负责把回答压缩成老师现场能说的短答。

要求：
1. 只回答学生当前追问，优先一句直答，最多 3 句
2. 口语化、直接、适合老师当场讲
3. 如果信息不足，要明确说“还缺什么”，再给保守回答
4. 不要编造课堂中未提到的内容
5. 不要输出条目、标题、推理过程或 AI 自述
{SPEAKABLE_CONSTRAINTS}
{subject_prompt}"""

        user_prompt = f"""【当前科目】
{used_subject or "未指定"}

【当前课程】
{(course_name or "").strip() or "未指定"}

【学生原始问题】
{student_question}

【已给出的兜底答案】
{fallback_answer}

【结构化课堂状态】
{classroom_state_block}

【最近课堂短窗口】
{transcript_block}

【参考资料摘要】
{material_block}

【追问历史】
{history_text}

【学生的新追问】
{followup}

请帮助老师回答。"""
        started_at = perf_counter()
        input_chars = len(system_prompt) + len(user_prompt)
        resolved_question_type = self._clean_text(str((classroom_state or {}).get("question_type", "")))

        try:
            content = await self._generate_text(
                prompt=user_prompt,
                model_name=self.chat_model,
                system_prompt=system_prompt,
                temperature=0.4,
                max_tokens=220,
            )
            answer = self._finalize_brief_answer(content, char_limit=120)
            self._record_generation_event(
                task="followup_answer",
                model_name=self.chat_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=answer,
                question_preview=followup or student_question,
                subject=used_subject,
                question_type=resolved_question_type,
            )
            return {"answer": answer}
        except Exception as exc:
            logger.exception("课堂追问失败")
            self._record_generation_event(
                task="followup_answer",
                model_name=self.chat_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output="",
                question_preview=followup or student_question,
                subject=used_subject,
                question_type=resolved_question_type,
                success=False,
                error=str(exc),
            )
            return {"answer": f"本地模型调用失败: {exc}"}

    async def generate_window_structured_summary(
        self,
        *,
        window_id: str = "",
        raw_window_text: str,
        rule_cleaned_text: str,
        subject: str = "",
        course_name: str = "",
        start_time: str = "",
        end_time: str = "",
        previous_main_topic: str = "",
        knowledge_tree_outline: str = "",
        recent_valid_questions: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        model_name = self.realtime_summary_model if self.realtime_summary_enabled else self.chat_model
        system_prompt, user_prompt = build_window_structuring_prompts(
            subject=subject,
            course_name=course_name,
            start_time=start_time,
            end_time=end_time,
            previous_main_topic=previous_main_topic,
            knowledge_tree_outline=knowledge_tree_outline,
            recent_valid_questions=recent_valid_questions or [],
            raw_window_text=raw_window_text,
            rule_cleaned_text=rule_cleaned_text,
        )
        started_at = perf_counter()
        input_chars = len(system_prompt) + len(user_prompt)

        try:
            result = await self._generate_json(
                prompt=user_prompt,
                model_name=model_name,
                system_prompt=system_prompt,
                temperature=0.2,
                max_tokens=520,
                schema=self.WINDOW_STRUCTURED_SCHEMA,
            )
            finalized = self._finalize_window_payload(
                result,
                raw_window_text=raw_window_text,
                rule_cleaned_text=rule_cleaned_text,
            )
            self._record_generation_event(
                task="window_structuring",
                model_name=model_name,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=finalized.get("stage_summary", ""),
                subject=subject,
                extra={
                    "session_id": session_storage_service.get_active_session_id(),
                    "window_id": window_id,
                    "prompt_preview": self._trim_chars(f"{system_prompt}\n{user_prompt}", 320),
                    "main_topic": finalized.get("main_topic", ""),
                    "relation_count": len(finalized.get("relations", [])),
                },
            )
            return finalized
        except Exception as exc:
            fallback = self._fallback_window_payload(
                raw_window_text=raw_window_text,
                rule_cleaned_text=rule_cleaned_text,
            )
            self._record_generation_event(
                task="window_structuring",
                model_name=model_name,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=fallback.get("stage_summary", ""),
                subject=subject,
                success=False,
                error=str(exc),
                extra={
                    "session_id": session_storage_service.get_active_session_id(),
                    "window_id": window_id,
                    "prompt_preview": self._trim_chars(f"{system_prompt}\n{user_prompt}", 320),
                },
            )
            logger.exception("窗口结构化抽取失败")
            return fallback

    async def summarize_class_status(
        self,
        transcript: str,
        material: str,
        subject: str = "",
        course_name: str = "",
        classroom_state: Optional[dict[str, Any]] = None,
    ) -> dict:
        """
        课堂状态摘要 - 帮助老师掌握当前教学进展

        Returns:
            dict with key: summary
        """
        used_subject, subject_prompt = build_subject_prompt(subject, course_name)
        classroom_state_block = self._render_classroom_state(classroom_state)
        transcript_block = self._render_transcript_window(classroom_state, transcript)
        material_block = self._clip_block(material, char_limit=MAX_PROMPT_MATERIAL_CHARS) or "暂无参考资料"

        system_prompt = f"""你是一位老师的课堂助手。请根据课堂转录和参考资料，帮助老师了解当前教学状态。

请简洁总结：
1. 当前已讲到的内容进度
2. 学生理解情况（从提问和互动判断）
3. 需要重点关注的知识点或未解答的问题
4. 课堂节奏评估（是否按计划推进）

控制在200字以内，用简洁条目式中文。
{subject_prompt}"""

        user_prompt = f"""【当前科目】
{used_subject or "未指定"}

【当前课程】
{(course_name or "").strip() or "未指定"}

【结构化课堂状态】
{classroom_state_block}

【课堂转录短窗口】
{transcript_block}

【参考资料摘要】
{material_block}

请总结当前课堂状态。"""
        started_at = perf_counter()
        input_chars = len(system_prompt) + len(user_prompt)
        resolved_question_type = self._clean_text(str((classroom_state or {}).get("question_type", "")))

        try:
            content = await self._generate_text(
                prompt=user_prompt,
                model_name=self.chat_model,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=500,
            )
            self._record_generation_event(
                task="class_status_summary",
                model_name=self.chat_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=content,
                question_preview="",
                subject=used_subject,
                question_type=resolved_question_type,
            )
            return {"summary": content}
        except Exception as e:
            logger.exception("课堂状态摘要生成失败")
            self._record_generation_event(
                task="class_status_summary",
                model_name=self.chat_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output="",
                question_preview="",
                subject=used_subject,
                question_type=resolved_question_type,
                success=False,
                error=str(e),
            )
            return {"summary": f"本地模型调用失败: {str(e)}"}

    async def answer_status_question(
        self,
        summary: str,
        transcript: str,
        material: str,
        question: str,
        history: Optional[list] = None,
        subject: str = "",
        course_name: str = "",
        classroom_state: Optional[dict[str, Any]] = None,
    ) -> dict:
        """围绕课堂状态继续追问。"""
        history_text = self._history_to_text(history)
        used_subject, subject_prompt = build_subject_prompt(subject, course_name)
        classroom_state_block = self._render_classroom_state(classroom_state)
        transcript_block = self._render_transcript_window(classroom_state, transcript)
        material_block = self._clip_block(material, char_limit=MAX_PROMPT_MATERIAL_CHARS) or "暂无参考资料"

        system_prompt = f"""你是老师的课堂状态助手，回答时只保留老师现在最需要知道的内容。

要求：
1. 优先依据课堂上下文回答
2. 默认 1 到 3 句，先给结论，再补一句建议
3. 信息不足时要明确说不够，再给下一步判断建议
4. 不要长篇分析，不要 AI 自述，不要编造不存在的课堂信息
{SPEAKABLE_CONSTRAINTS}
{subject_prompt}"""

        user_prompt = f"""【当前科目】
{used_subject or "未指定"}

【当前课程】
{(course_name or "").strip() or "未指定"}

【当前课堂状态摘要】
{self._clip_block(summary, char_limit=MAX_PROMPT_SUMMARY_CHARS) or "暂无摘要"}

【结构化课堂状态】
{classroom_state_block}

【最近课堂短窗口】
{transcript_block}

【参考资料摘要】
{material_block}

【已有追问历史】
{history_text}

【老师的问题】
{question}

请直接回答。"""
        started_at = perf_counter()
        input_chars = len(system_prompt) + len(user_prompt)
        resolved_question_type = self._clean_text(str((classroom_state or {}).get("question_type", "")))

        try:
            content = await self._generate_text(
                prompt=user_prompt,
                model_name=self.chat_model,
                system_prompt=system_prompt,
                temperature=0.4,
                max_tokens=220,
            )
            answer = self._finalize_brief_answer(content, char_limit=120)
            self._record_generation_event(
                task="status_answer",
                model_name=self.chat_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=answer,
                question_preview=question,
                subject=used_subject,
                question_type=resolved_question_type,
            )
            return {"answer": answer}
        except Exception as exc:
            logger.exception("课堂状态追问失败")
            self._record_generation_event(
                task="status_answer",
                model_name=self.chat_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output="",
                question_preview=question,
                subject=used_subject,
                question_type=resolved_question_type,
                success=False,
                error=str(exc),
            )
            return {"answer": f"本地模型调用失败: {exc}"}

    async def generate_class_summary(
        self,
        summary_package: dict[str, Any],
        subject: str = "",
        course_name: str = "",
        classroom_state: Optional[dict[str, Any]] = None,
        progress_callback: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    ) -> str:
        """
        生成课后总结 Markdown 笔记（教师版）

        Returns:
            Markdown 格式的课堂总结
        """
        used_subject, _ = build_subject_prompt(subject, course_name)
        resolved_subject = used_subject or str(summary_package.get("subject") or "").strip()
        resolved_course_name = (course_name or "").strip() or str(summary_package.get("course_name") or "").strip() or "课堂笔记"
        system_prompt, user_prompt = build_final_summary_prompts(
            subject=resolved_subject,
            course_name=resolved_course_name,
            summary_package=summary_package,
        )
        started_at = perf_counter()
        input_chars = len(system_prompt) + len(user_prompt)
        resolved_question_type = self._clean_text(str((classroom_state or {}).get("question_type", "")))
        thinking_text = ""
        content_text = ""

        if progress_callback is not None:
            await progress_callback(
                {
                    "phase": "preparing",
                    "message": "Gemma4 已接管课后总结，正在读取结构化课堂输入包。",
                    "model": self.final_summary_model,
                    "thinking_text": "",
                    "content_text": "",
                }
            )

        try:
            async def handle_stream_chunk(chunk: dict[str, Any]) -> None:
                nonlocal thinking_text, content_text

                thinking_delta = (chunk.get("thinking_delta") or "")
                content_delta = (chunk.get("content_delta") or "")
                if not thinking_delta and not content_delta:
                    return

                if thinking_delta:
                    thinking_text += thinking_delta
                if content_delta:
                    content_text += content_delta

                if progress_callback is not None:
                    await progress_callback(
                        {
                            "phase": "writing" if content_text.strip() else "thinking",
                            "message": (
                                "Gemma4 正在输出课堂总结正文。"
                                if content_text.strip()
                                else "Gemma4 正在思考课堂总结结构。"
                            ),
                            "model": self.final_summary_model,
                            "thinking_text": thinking_text,
                            "content_text": content_text,
                        }
                    )

            summary_text = await self._ollama.generate_answer_stream(
                prompt=user_prompt,
                model_name=self.final_summary_model,
                options={
                    "system_prompt": system_prompt,
                    "temperature": 0.4,
                    "max_tokens": 4000,
                    "think": True,
                },
                on_chunk=handle_stream_chunk,
            )
            self._record_generation_event(
                task="final_class_summary",
                model_name=self.final_summary_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=summary_text,
                question_preview=resolved_course_name,
                subject=resolved_subject,
                question_type=resolved_question_type,
                extra={
                    "session_id": str(summary_package.get("session_id") or session_storage_service.get_active_session_id()),
                    "summary_package_bytes": len(json.dumps(summary_package, ensure_ascii=False)),
                    "prompt_preview": self._trim_chars(f"{system_prompt}\n{user_prompt}", 360),
                    "summary_package_windows": len(summary_package.get("window_summaries", []) or []),
                    "summary_package_valid_questions": len(summary_package.get("valid_questions", []) or []),
                },
            )
            return summary_text
        except Exception as e:
            logger.exception("课后总结生成失败")
            if progress_callback is not None:
                await progress_callback(
                    {
                        "phase": "failed",
                        "message": f"Gemma4 总结生成失败：{str(e)}",
                        "model": self.final_summary_model,
                        "thinking_text": thinking_text,
                        "content_text": content_text,
                        "error": str(e),
                    }
                )
            self._record_generation_event(
                task="final_class_summary",
                model_name=self.final_summary_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output="",
                question_preview=resolved_course_name,
                subject=resolved_subject,
                question_type=resolved_question_type,
                success=False,
                error=str(e),
                extra={
                    "session_id": str(summary_package.get("session_id") or session_storage_service.get_active_session_id()),
                    "summary_package_bytes": len(json.dumps(summary_package, ensure_ascii=False)),
                    "prompt_preview": self._trim_chars(f"{system_prompt}\n{user_prompt}", 360),
                    "summary_package_windows": len(summary_package.get("window_summaries", []) or []),
                    "summary_package_valid_questions": len(summary_package.get("valid_questions", []) or []),
                },
            )
            raise

    async def generate_realtime_summary_if_enabled(
        self,
        previous_summary: str,
        recent_lines: list[str],
        *,
        subject: str = "",
        question_type: str = "",
    ) -> dict[str, Any]:
        started_at = perf_counter()
        input_chars = len(previous_summary or "") + sum(len(line) for line in recent_lines or [])

        if not recent_lines:
            payload = {
                "summary_text": previous_summary.strip(),
                "section_title": "",
                "points": [],
                "flow_title": "",
                "flow_steps": [],
                "skipped": True,
                "reason": "empty_recent_lines",
            }
            self._record_generation_event(
                task="realtime_summary",
                model_name=self.realtime_summary_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=payload["summary_text"],
                subject=subject,
                question_type=question_type,
                skipped=True,
                extra={"reason": payload["reason"]},
            )
            return payload

        if not self.realtime_summary_enabled:
            payload = {
                "summary_text": previous_summary.strip(),
                "section_title": "",
                "points": [],
                "flow_title": "",
                "flow_steps": [],
                "skipped": True,
                "reason": "disabled_by_config",
            }
            self._record_generation_event(
                task="realtime_summary",
                model_name=self.realtime_summary_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=payload["summary_text"],
                subject=subject,
                question_type=question_type,
                skipped=True,
                extra={"reason": payload["reason"]},
            )
            return payload

        try:
            payload = await self.compress_monitoring_progress(previous_summary, recent_lines)
            self._record_generation_event(
                task="realtime_summary",
                model_name=self.realtime_summary_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output=str(payload.get("summary_text", "")),
                subject=subject,
                question_type=question_type,
            )
            return payload
        except Exception as exc:
            self._record_generation_event(
                task="realtime_summary",
                model_name=self.realtime_summary_model,
                started_at=started_at,
                input_chars=input_chars,
                primary_output="",
                subject=subject,
                question_type=question_type,
                success=False,
                error=str(exc),
            )
            raise

    async def compress_monitoring_progress(self, previous_summary: str, recent_lines: list[str]) -> dict:
        """
        将历史摘要和新近课堂记录压缩为新的滚动摘要。

        Args:
            previous_summary: 上一次滚动摘要，首次为空字符串
            recent_lines: 本轮待压缩的课堂记录（建议 50 行）

        Returns:
            dict with keys: summary_text, section_title, points, flow_title, flow_steps
        """
        if not recent_lines:
            return {
                "summary_text": previous_summary.strip(),
                "section_title": "",
                "points": [],
                "flow_title": "",
                "flow_steps": [],
            }

        system_prompt = """你是一个课堂实时总结助手。把"历史摘要"和"最新课堂记录"合并成一份更短但信息完整的滚动摘要卡片。

要求：
1. 保留课程主题、当前讲到的章节、关键知识点、学生提问、老师解答、课堂节奏信息
2. 删除口头重复、语气词、无信息量的重复表述
3. 输出精简中文，不要编造内容
4. summary_text 控制在120到180字以内，适合放在紧凑的实时摘要卡片中
5. section_title 是当前章节或当前知识块标题，尽量短
6. points 输出 2 到 4 条分点，每条 10 到 30 字
7. 如果当前内容明显包含步骤、流程、形成过程，可输出 flow_title 和 flow_steps；否则留空数组
8. 输出 JSON，不要加 markdown 代码块

JSON 格式：
{
  "summary_text": "整体实时总结",
  "section_title": "当前章节标题",
  "points": ["分点1", "分点2"],
  "flow_title": "某某形成流程",
  "flow_steps": ["步骤1", "步骤2", "步骤3"]
}"""

        previous_summary = previous_summary.strip() or "暂无历史摘要"
        new_content = "\n".join(recent_lines)
        user_prompt = f"""【历史摘要】
{previous_summary}

【最新课堂记录】
{new_content}

请输出新的滚动摘要。"""

        try:
            result = await self._generate_json(
                prompt=user_prompt,
                model_name=self.realtime_summary_model,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=320,
                schema=self.SUMMARY_CARD_SCHEMA,
            )
            points = [
                item.strip()
                for item in result.get("points", [])
                if isinstance(item, str) and item.strip()
            ][:4]
            flow_steps = [
                item.strip()
                for item in result.get("flow_steps", [])
                if isinstance(item, str) and item.strip()
            ][:5]
            summary_text = (result.get("summary_text") or "").strip()
            section_title = (result.get("section_title") or "").strip()
            flow_title = (result.get("flow_title") or "").strip()

            if not summary_text:
                summary_text = "；".join(points) if points else previous_summary.strip()

            return {
                "summary_text": summary_text,
                "section_title": section_title,
                "points": points,
                "flow_title": flow_title,
                "flow_steps": flow_steps,
            }
        except Exception:
            logger.exception("滚动摘要生成失败")
            raise
