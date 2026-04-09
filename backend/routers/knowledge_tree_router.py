"""
知识树查询路由
==============
为前端知识树面板和调试工具提供当前树状态与快照摘要。
"""

from fastapi import APIRouter

from services.knowledge_tree_service import knowledge_tree_service

router = APIRouter()


@router.get("/knowledge_tree/current")
async def get_current_knowledge_tree():
    tree = knowledge_tree_service.get_current_tree()
    return {
        "status": "success",
        "knowledge_tree": tree,
        "summary": knowledge_tree_service.get_tree_summary(),
    }


@router.get("/knowledge_tree/snapshots")
async def get_knowledge_tree_snapshots(limit: int = 12):
    return {
        "status": "success",
        "snapshots": knowledge_tree_service.list_snapshots(limit=max(1, min(limit, 50))),
    }
