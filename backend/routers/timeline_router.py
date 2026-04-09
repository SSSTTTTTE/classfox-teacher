"""
问题轨迹路由（兼容旧时间轴接口）
==============================
主存储改为 questions/，timeline/current_session.json 仅作为兼容镜像。
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services.question_event_service import question_event_service

router = APIRouter()


class TimelineNode(BaseModel):
    """兼容旧前端的时间轴节点定义。"""

    timestamp: str
    text: str
    student_question: str
    one_sentence_answer: str
    bookmarked: bool = False
    expanded: bool = False
    repeat_count: int = 1


class AddNodeRequest(BaseModel):
    timestamp: str
    text: str
    student_question: str
    one_sentence_answer: str


class BookmarkRequest(BaseModel):
    node_id: str
    bookmarked: bool


class MarkExpandedRequest(BaseModel):
    node_id: str


@router.post("/timeline/add")
async def add_timeline_node(request: AddNodeRequest):
    """
    兼容旧前端的时间轴写入接口。
    现在统一落到问题状态机，至少会生成 answered 轨迹记录。
    """
    record = question_event_service.record_answered_question(
        raw_text=request.text,
        question_text=request.student_question,
        one_sentence_answer=request.one_sentence_answer,
        teacher_speakable_answer=request.one_sentence_answer,
        trigger_time=request.timestamp,
    )
    return {
        "status": "added",
        "node_id": record.get("question_id", ""),
        "question_status": record.get("status", ""),
    }


@router.post("/timeline/bookmark")
async def set_bookmark(request: BookmarkRequest):
    """
    兼容接口。
    v1.1.2 后 bookmarked 主要由问题状态驱动，这里保留成功响应避免旧前端报错。
    """
    return {
        "status": "ignored",
        "node_id": request.node_id,
        "bookmarked": request.bookmarked,
        "message": "v1.1.2 起书签状态由有效问题/挂树状态自动维护",
    }


@router.post("/timeline/expanded")
async def mark_expanded(request: MarkExpandedRequest):
    """兼容接口，前端仍可调用但不再单独持久化 expanded 状态。"""
    return {
        "status": "ignored",
        "node_id": request.node_id,
        "message": "v1.1.2 起展开状态不再单独持久化",
    }


@router.get("/timeline")
async def get_timeline(
    bookmarked_only: bool = False,
    status: Optional[str] = None,
):
    """获取当前会话的问题轨迹，同时兼容旧时间轴字段。"""
    nodes = question_event_service.get_question_trajectory(
        status=(status or "").strip(),
        bookmarked_only=bookmarked_only,
    )
    summary = question_event_service.get_trajectory_summary()
    return {
        "status": "success",
        "total": len(nodes),
        "nodes": nodes,
        "status_counts": summary.get("status_counts", {}),
    }


@router.get("/timeline/questions")
async def get_question_records(
    status: Optional[str] = None,
    bookmarked_only: bool = False,
):
    """提供完整的问题轨迹记录，给新前端或调试使用。"""
    records = question_event_service.list_question_records(
        status=(status or "").strip(),
        bookmarked_only=bookmarked_only,
    )
    return {
        "status": "success",
        "total": len(records),
        "records": records,
    }


@router.post("/timeline/clear")
async def clear_timeline():
    """清空当前 session 的问题轨迹。"""
    return question_event_service.clear_current_session()


@router.get("/timeline/summary")
async def timeline_summary():
    """生成问题轨迹摘要（课后复盘用）。"""
    summary = question_event_service.get_trajectory_summary()
    valid_nodes = question_event_service.get_question_trajectory(bookmarked_only=True)
    return {
        "status": "success",
        **summary,
        "bookmarked_count": summary.get("valid_questions", 0),
        "repeated_questions": 0,
        "nodes": valid_nodes,
    }
