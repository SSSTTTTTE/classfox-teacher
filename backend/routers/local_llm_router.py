"""
本地模型状态路由
================
暴露 Ollama 的健康检查、状态快照、评估指标与模型预热接口。
"""

from fastapi import APIRouter, HTTPException

from services.llm_service import LLMService
from services.local_llm_runtime import local_llm_runtime


router = APIRouter()
llm_service = LLMService()


@router.get("/local_llm/health")
async def local_llm_health():
    try:
        status = await local_llm_runtime.check_health()
        return {"status": "success", **status}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"本地模型健康检查失败: {exc}")


@router.get("/local_llm/status")
async def local_llm_status():
    return {"status": "success", **local_llm_runtime.get_status()}


@router.get("/local_llm/evaluation")
async def local_llm_evaluation():
    return {"status": "success", **llm_service.get_evaluation_snapshot()}


@router.post("/local_llm/warmup")
async def local_llm_warmup():
    try:
        status = await local_llm_runtime.warmup_chat_model()
        return {"status": "success", **status}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"本地模型预热失败: {exc}")


@router.post("/local_llm/realtime_summary_probe")
async def local_llm_realtime_summary_probe():
    try:
        payload = await llm_service.generate_realtime_summary_if_enabled(
            previous_summary="老师刚讲完上一段内容。",
            recent_lines=[
                "[09:00:01] 老师：我们先看一次函数图像。",
                "[09:00:08] 学生：这里为什么会先下降？",
                "[09:00:14] 老师：因为导数在这一段是负值。",
            ],
        )
        return {"status": "success", **payload}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"实时总结探针执行失败: {exc}")
