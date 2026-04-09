"""
设置路由
========
管理后端 .env 配置，供前端设置面板读写。
"""

import os
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter()


if getattr(sys, 'frozen', False):
    ENV_PATH = os.path.join(os.path.dirname(sys.executable), '.env')
else:
    ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')


class SettingsUpdateRequest(BaseModel):
    content: str


class SeedAsrValidateRequest(BaseModel):
    app_key: str
    access_key: str
    resource_id: str
    ws_url: str


@router.get("/settings")
async def get_settings():
    if not os.path.exists(ENV_PATH):
        return {"status": "success", "content": "", "path": ENV_PATH}

    with open(ENV_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    return {"status": "success", "content": content, "path": ENV_PATH}


@router.post("/settings")
async def update_settings(request: SettingsUpdateRequest):
    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(request.content.rstrip() + "\n")
        return {"status": "success", "message": "设置已保存，重启后端后生效。"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存设置失败: {exc}")


@router.post("/settings/validate_seed_asr")
async def validate_seed_asr(request: SeedAsrValidateRequest):
    """尝试与 Seed-ASR 建立 WebSocket 握手，验证凭证是否有效"""
    import uuid
    try:
        import websocket
    except ImportError:
        raise HTTPException(status_code=500, detail="websocket-client 未安装")

    connect_id = str(uuid.uuid4())
    headers = [
        f"X-Api-App-Key: {request.app_key}",
        f"X-Api-Access-Key: {request.access_key}",
        f"X-Api-Resource-Id: {request.resource_id}",
        f"X-Api-Connect-Id: {connect_id}",
    ]

    try:
        ws = websocket.create_connection(request.ws_url, header=headers, timeout=8)
        ws.close()
        return {"status": "success", "message": "验证通过，凭证有效"}
    except websocket.WebSocketBadStatusException as e:
        status_code_val = getattr(e, 'status_code', 0)
        body = getattr(e, 'resp_body', b"")
        try:
            import json
            err_detail = json.loads(body).get("error", str(e))
        except Exception:
            err_detail = str(e)
        raise HTTPException(status_code=400, detail=f"HTTP {status_code_val}: {err_detail}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"连接失败: {exc}")


@router.post("/settings/restart_backend")
async def restart_backend():
    """touch main.py 触发 uvicorn --reload 热重载，使新 .env 生效"""
    try:
        main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py')
        os.utime(main_path, None)
        return {"status": "success", "message": "已触发后端重载"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"重载失败: {exc}")
