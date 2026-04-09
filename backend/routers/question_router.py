"""
学生提问路由（教师版）
======================
检测到学生提问后，调用 LLM 生成兜底答案和课堂状态摘要
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.llm_service import LLMService
from services.prompt_builder import resolve_subject_name
from services.question_classifier import QuestionClassifier
from services.question_event_service import question_event_service
from services.session_state_service import session_state_service
from services.transcript_service import TranscriptService

router = APIRouter()

llm_service = LLMService()
question_classifier = QuestionClassifier()
transcript_service = TranscriptService()


class HistoryItem(BaseModel):
    role: str
    content: str


class AnswerRequest(BaseModel):
    detected_question: Optional[str] = None
    detected_timestamp: Optional[str] = None


class FollowupRequest(BaseModel):
    student_question: str
    teacher_speakable_answer: str = ""
    one_sentence_answer: str = ""
    followup: str
    history: list[HistoryItem] = []


class StatusChatRequest(BaseModel):
    summary: str
    question: str
    history: list[HistoryItem] = []


class ConfirmValidRequest(BaseModel):
    question_id: str
    answer_id: str
    confirmed_by_teacher_action: bool = True


def _get_classroom_context() -> tuple[dict, str, str, str, str]:
    classroom_state = session_state_service.get_state()
    transcript_meta = transcript_service.get_transcript_metadata()
    subject = resolve_subject_name(
        classroom_state.get("subject", "") or transcript_meta.get("subject", ""),
        classroom_state.get("course_name", "") or transcript_meta.get("course_name", ""),
    )
    course_name = (
        classroom_state.get("course_name", "")
        or transcript_meta.get("course_name", "")
        or ""
    ).strip()
    recent_transcript = session_state_service.get_recent_transcript_text(max_lines=8)
    if not recent_transcript:
        recent_transcript = transcript_service.get_recent_transcript(minutes=2)
    class_material = (classroom_state.get("current_material") or "").strip()
    if not class_material:
        class_material = transcript_service.get_class_material_excerpt()
    return classroom_state, subject, course_name, recent_transcript, class_material


@router.post("/question/answer")
async def get_fallback_answer(request: Optional[AnswerRequest] = None):
    """
    学生提问兜底答案接口
    - 如果前端传入 detected_question，直接以该文本为上下文提示 LLM
    - 否则读取结构化课堂状态里的最近转录短窗口
    - 调用 LLM 提取学生问题并生成一句话兜底答案
    - 返回：student_question, one_line_answer, teacher_speakable_answer, short_explanation, confidence
    """
    try:
        detected_q = (request.detected_question or "").strip() if request else ""
        detected_timestamp = (request.detected_timestamp or "").strip() if request else ""
        classroom_state, subject, course_name, recent_transcript, class_material = _get_classroom_context()
        if detected_q:
            recent_transcript = ""

        classification = question_classifier.classify(
            detected_question=detected_q,
            transcript=recent_transcript,
        )

        if not recent_transcript and not detected_q:
            return {
                "status": "warning",
                "student_question": "暂无课堂记录",
                "one_line_answer": "请先开启监听",
                "teacher_speakable_answer": "请先开启课堂监听。",
                "short_explanation": "",
                "confidence": "low",
                "question_type": classification["question_type"],
                "used_subject": subject,
                "one_sentence_answer": "请先开启课堂监听。",
                "detail": "",
            }

        result = await llm_service.generate_fallback_answer(
            transcript=recent_transcript,
            material=class_material,
            detected_question=detected_q or None,
            subject=subject,
            course_name=course_name,
            question_type=classification["question_type"],
            classroom_state=classroom_state,
        )

        answered_record = question_event_service.record_answered_question(
            raw_text=detected_q or result.get("student_question", ""),
            question_text=result.get("student_question", "") or detected_q,
            one_sentence_answer=result.get("one_line_answer", "") or result.get("one_sentence_answer", ""),
            teacher_speakable_answer=result.get("teacher_speakable_answer", ""),
            trigger_time=detected_timestamp,
            question_type=result.get("question_type", classification["question_type"]),
            used_subject=result.get("used_subject", subject),
            confidence=result.get("confidence", ""),
            answer_mode=result.get("answer_mode", ""),
        )

        session_state_service.record_interaction(
            student_question=result.get("student_question", ""),
            teacher_answer=result.get("teacher_speakable_answer", "") or result.get("one_sentence_answer", ""),
            question_type=result.get("question_type", classification["question_type"]),
            used_subject=result.get("used_subject", subject),
            confidence=result.get("confidence", ""),
            answer_mode=result.get("answer_mode", ""),
        )

        return {
            "status": "success",
            **result,
            "question_id": answered_record.get("question_id", ""),
            "answer_id": answered_record.get("linked_answer_id", ""),
            "trigger_time": answered_record.get("trigger_time", detected_timestamp),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成兜底答案失败: {str(e)}")


@router.post("/question/followup")
async def question_followup(request: FollowupRequest):
    """围绕兜底答案继续追问。"""
    try:
        classroom_state, subject, course_name, recent_transcript, class_material = _get_classroom_context()
        result = await llm_service.answer_followup_question(
            student_question=request.student_question,
            fallback_answer=request.teacher_speakable_answer or request.one_sentence_answer,
            transcript=recent_transcript,
            material=class_material,
            followup=request.followup,
            history=[item.model_dump() for item in request.history],
            subject=subject,
            course_name=course_name,
            classroom_state=classroom_state,
        )
        session_state_service.record_interaction(
            student_question="",
            teacher_answer=result.get("answer", ""),
            question_type=classroom_state.get("question_type", ""),
            used_subject=subject,
        )
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"追问失败: {str(e)}")


@router.post("/status/summary")
async def class_status_summary():
    """
    课堂状态摘要接口
    - 帮助老师快速了解当前教学进展
    - 返回：summary
    """
    try:
        classroom_state, subject, course_name, recent_transcript, class_material = _get_classroom_context()

        if not recent_transcript:
            return {
                "status": "warning",
                "summary": "暂无课堂记录，请先开始课堂监听。"
            }

        result = await llm_service.summarize_class_status(
            transcript=recent_transcript,
            material=class_material,
            subject=subject,
            course_name=course_name,
            classroom_state=classroom_state,
        )

        return {"status": "success", **result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取课堂状态失败: {str(e)}")


@router.post("/status/chat")
async def status_chat(request: StatusChatRequest):
    """围绕课堂状态继续追问。"""
    try:
        classroom_state, subject, course_name, recent_transcript, class_material = _get_classroom_context()
        result = await llm_service.answer_status_question(
            summary=request.summary,
            transcript=recent_transcript,
            material=class_material,
            question=request.question,
            history=[item.model_dump() for item in request.history],
            subject=subject,
            course_name=course_name,
            classroom_state=classroom_state,
        )
        session_state_service.record_interaction(
            student_question="",
            teacher_answer=result.get("answer", ""),
            question_type=classroom_state.get("question_type", ""),
            used_subject=subject,
        )
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"追问失败: {str(e)}")


@router.post("/question/confirm_valid")
async def confirm_valid_question(request: ConfirmValidRequest):
    """将“查看兜底答案”升级为有效问题确认动作，并尝试挂到知识树。"""
    try:
        record = question_event_service.confirm_valid_question(
            question_id=request.question_id,
            answer_id=request.answer_id,
            confirmed_by_teacher_action=request.confirmed_by_teacher_action,
        )
        return {
            "status": "success",
            "question_id": record.get("question_id", ""),
            "answer_id": record.get("linked_answer_id", ""),
            "question_status": record.get("status", ""),
            "linked_topic_id": record.get("linked_topic_id", ""),
            "linked_topic_title": record.get("linked_topic_title", ""),
            "confirmed_at": record.get("confirmed_at", ""),
            "knowledge_tree_snapshot": record.get("knowledge_tree_snapshot", {}),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"确认有效问题失败: {str(exc)}")
