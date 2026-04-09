"""
课后总结路由
============
课后生成 Markdown 笔记
"""

from fastapi import APIRouter, HTTPException
from services.summary_service import SummaryService

router = APIRouter()

summary_service = SummaryService()


@router.post("/generate_summary")
async def generate_summary():
    """
    课后总结接口
    - 读取完整的课堂转录文本
    - 读取课程资料
    - 调用 LLM 生成结构化 Markdown 笔记
    - 保存到 /data/summaries/ 目录
    """
    try:
        return await summary_service.generate_summary()

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"总结生成失败: {str(e)}")
