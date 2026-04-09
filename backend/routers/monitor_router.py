"""
监控服务路由（教师版）
======================
处理录音启停、学生提问检测、WebSocket 事件推送
"""

import json
import os
import shutil
from datetime import datetime
from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from services.local_llm_runtime import local_llm_runtime
from services.monitor_service import MonitorService
from services.prompt_builder import resolve_subject_name
from services.session_state_service import session_state_service
from services.summary_service import SummaryService
from services.transcript_service import TranscriptService
from services.ppt_service import parse_material
from config import MATERIALS_DIR

router = APIRouter()

monitor_service = MonitorService()
transcript_service = TranscriptService()
summary_service = SummaryService()


class StartMonitorRequest(BaseModel):
    subject: str = ""
    course_name: str = ""
    material_filename: Optional[str] = None
    dry_run: bool = False


@router.post("/start_monitor")
async def start_monitor(request: StartMonitorRequest):
    """
    开始课堂监听
    - 初始化课堂会话
    - 检查本地 Ollama 状态
    - 预热课堂短答模型
    - 启动麦克风录音
    - 启动 ASR 语音转文字
    - 启动学生提问检测
    """
    material_name = request.material_filename or ""

    try:
        transcript_service.activate_cite_file(material_name or None)
        llm_init = await local_llm_runtime.prepare_for_class_start()
        if request.dry_run:
            resolved_subject = resolve_subject_name(request.subject, request.course_name)
            session_state_service.reset_for_class(
                subject=resolved_subject,
                course_name=request.course_name.strip(),
                material_name=material_name,
                material_excerpt=transcript_service.get_class_material_excerpt(),
                llm_ready=True,
            )
            result = {
                "status": "dry_run_ready",
                "message": "课堂初始化已完成（未启动麦克风）",
                "subject": resolved_subject,
            }
        else:
            result = await monitor_service.start(
                course_name=request.course_name,
                material_name=material_name,
                subject=request.subject,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"课堂初始化失败: {exc}")

    return {
        **result,
        "local_llm": llm_init["status"],
        "init_steps": [
            {"step": "session_initialized", "ok": True, "course_name": request.course_name.strip()},
            {"step": "subject_ready", "ok": True, "subject": result.get("subject", "")},
            {
                "step": "ollama_checked",
                "ok": True,
                "chat_model": llm_init["health"]["chat_model"],
                "online": llm_init["health"]["online"],
            },
            {
                "step": "chat_model_warmed",
                "ok": True,
                "models": [item.get("model", "") for item in llm_init["warmup"].get("models", [])],
            },
            {"step": "monitor_started", "ok": not request.dry_run},
            {"step": "audio_capture_skipped", "ok": request.dry_run},
        ],
    }


@router.get("/materials")
async def get_materials():
    """获取可用参考资料列表"""
    return {
        "status": "success",
        "items": transcript_service.list_cite_files(),
    }


@router.post("/materials/upload")
async def upload_material(file: UploadFile = File(...)):
    """上传参考资料文件，自动解析为文本"""
    os.makedirs(MATERIALS_DIR, exist_ok=True)
    original_name = file.filename
    dest = os.path.join(MATERIALS_DIR, original_name)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    ext = os.path.splitext(original_name)[1].lower()
    if ext in (".pptx", ".ppt", ".pdf", ".docx", ".doc"):
        try:
            text_content = parse_material(dest, original_name)
            txt_name = os.path.splitext(original_name)[0] + ".txt"
            txt_dest = os.path.join(MATERIALS_DIR, txt_name)
            with open(txt_dest, "w", encoding="utf-8") as f:
                f.write(text_content)
            return {"status": "success", "filename": txt_name, "original": original_name}
        except Exception as exc:
            return {"status": "success", "filename": original_name, "warning": f"解析失败，保留原文件: {exc}"}

    return {"status": "success", "filename": original_name}


@router.post("/stop_monitor")
async def stop_monitor():
    """停止监听并自动生成课堂总结"""
    result = await monitor_service.stop()
    if result.get("status") != "stopped":
        return result

    try:
        await monitor_service.update_final_summary_state(
            active=True,
            phase="preparing",
            message="课堂监听已结束，正在切换到 Gemma4 课后总结。",
            model=monitor_service.get_final_summary_payload().get("model", ""),
            course_name=result.get("course_name") or "",
            thinking_text="",
            content_text="",
            filename="",
            error="",
            started_at=datetime.now().isoformat(timespec="seconds"),
            finished_at="",
        )

        async def handle_summary_progress(payload: dict):
            phase = str(payload.get("phase") or "thinking").strip() or "thinking"
            is_completed = phase == "completed"
            is_failed = phase == "failed"
            await monitor_service.update_final_summary_state(
                active=not (is_completed or is_failed),
                phase=phase,
                message=str(payload.get("message") or "").strip(),
                model=str(payload.get("model") or monitor_service.get_final_summary_payload().get("model", "")).strip(),
                course_name=str(payload.get("course_name") or result.get("course_name") or "").strip(),
                thinking_text=str(payload.get("thinking_text") or monitor_service.get_final_summary_payload().get("thinking_text", "")),
                content_text=str(payload.get("content_text") or monitor_service.get_final_summary_payload().get("content_text", "")),
                filename=str(payload.get("filename") or ""),
                error=str(payload.get("error") or ""),
                finished_at=datetime.now().isoformat(timespec="seconds") if (is_completed or is_failed) else "",
            )

        summary_result = await summary_service.generate_summary_with_progress(
            course_name=result.get("course_name") or "",
            progress_callback=handle_summary_progress,
        )
        result["summary"] = {
            "filename": summary_result["filename"],
            "course_name": summary_result["course_name"],
        }
    except ValueError as exc:
        result["summary_error"] = str(exc)
        await monitor_service.update_final_summary_state(
            active=False,
            phase="failed",
            message=f"课堂总结生成失败：{str(exc)}",
            course_name=result.get("course_name") or "",
            error=str(exc),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    except Exception as exc:
        result["summary_error"] = f"自动总结失败: {exc}"
        await monitor_service.update_final_summary_state(
            active=False,
            phase="failed",
            message=f"课堂总结生成失败：{str(exc)}",
            course_name=result.get("course_name") or "",
            error=str(exc),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )

    return result


@router.post("/pause_monitor")
async def pause_monitor():
    return await monitor_service.pause()


@router.post("/resume_monitor")
async def resume_monitor():
    return await monitor_service.resume()


@router.get("/monitor_status")
async def monitor_status():
    return {
        "status": "success",
        "is_monitoring": monitor_service.is_monitoring,
        "is_paused": monitor_service.is_paused,
        "context": monitor_service.get_context_status(),
    }


@router.get("/monitor/context_status")
async def monitor_context_status():
    return {
        "status": "success",
        "is_monitoring": monitor_service.is_monitoring,
        "is_paused": monitor_service.is_paused,
        "context": monitor_service.get_context_status(),
    }


@router.get("/monitor/final_summary_status")
async def monitor_final_summary_status():
    return {
        "status": "success",
        "summary": monitor_service.get_final_summary_payload(),
    }


@router.post("/monitor/reset_context")
async def reset_monitor_context():
    reset_payload = monitor_service.reset_context_for_recovery()
    warmup_status = None
    warmup_error = ""

    try:
        health = await local_llm_runtime.check_health()
        if health.get("online") and health.get("chat_model_available"):
            warmup_status = await local_llm_runtime.warmup_chat_model()
            session_state_service.set_llm_ready(True)
        else:
            session_state_service.set_llm_ready(False)
            warmup_error = health.get("last_error") or "课堂短答模型暂不可用"
    except Exception as exc:
        session_state_service.set_llm_ready(False)
        warmup_error = str(exc)

    return {
        "status": "success",
        "message": "课堂上下文已重置",
        "summary_kept": reset_payload["summary_kept"],
        "context": monitor_service.get_context_status(),
        "warmup": warmup_status,
        "warmup_error": warmup_error,
    }


@router.get("/check_mic")
async def check_mic():
    """检查麦克风是否可用"""
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        info = p.get_default_input_device_info()
        device_name = info.get("name", "Unknown")
        sample_rate = int(info.get("defaultSampleRate", 0))
        channels = int(info.get("maxInputChannels", 0))
        p.terminate()
        return {
            "status": "ok",
            "device": device_name,
            "sample_rate": sample_rate,
            "channels": channels,
            "message": f"麦克风可用: {device_name}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"麦克风不可用: {str(e)}"
        }


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket 端点 - 实时推送学生提问检测事件
    前端连接此 WebSocket 后，当检测到学生提问时会收到 question_detected 消息
    """
    await websocket.accept()
    monitor_service.register_websocket(websocket)
    current_summary = monitor_service.get_realtime_summary_payload()
    if current_summary.get("summary_text") or current_summary.get("cards"):
        await websocket.send_text(
            json.dumps({"type": "summary_update", **current_summary}, ensure_ascii=False)
        )
    current_final_summary = monitor_service.get_final_summary_payload()
    if (
        current_final_summary.get("active")
        or current_final_summary.get("phase") not in {"", "idle"}
        or current_final_summary.get("thinking_text")
        or current_final_summary.get("content_text")
        or current_final_summary.get("error")
    ):
        await websocket.send_text(
            json.dumps({"type": "final_summary_update", **current_final_summary}, ensure_ascii=False)
        )
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        monitor_service.unregister_websocket(websocket)
