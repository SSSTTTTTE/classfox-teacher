"""
本地模型运行态
==============
统一维护 Ollama 健康检查、预热状态和最近错误，供多个路由共享。
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from services.llm_service import LLMService


class LocalLLMRuntime:
    """持有本地模型运行状态的轻量单例。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._warmed_models: set[str] = set()
        self._last_error: str = ""
        self._last_health_payload: dict[str, Any] = {}
        self._last_checked_at: str = ""
        self._last_warmed_at: str = ""
        self._warmup_state: str = "idle"

    def _service(self) -> LLMService:
        return LLMService()

    def _snapshot(self, service: LLMService) -> dict[str, Any]:
        config = service.runtime_config()
        with self._lock:
            available_models = list(self._last_health_payload.get("models", []))
            chat_model = config["chat_model"]
            final_summary_model = config["final_summary_model"]
            realtime_summary_model = config["realtime_summary_model"]
            online = bool(self._last_health_payload.get("ok", False))

            return {
                "online": online,
                "base_url": config["base_url"],
                "chat_model": chat_model,
                "final_summary_model": final_summary_model,
                "realtime_summary_enabled": config["realtime_summary_enabled"],
                "realtime_summary_model": realtime_summary_model,
                "available_models": available_models,
                "missing_models": list(self._last_health_payload.get("missing_models", [])),
                "chat_model_available": chat_model in available_models if available_models else False,
                "final_summary_model_available": (
                    final_summary_model in available_models if available_models else False
                ),
                "realtime_summary_model_available": (
                    realtime_summary_model in available_models
                    if config["realtime_summary_enabled"] and available_models
                    else False
                ),
                "is_warmed": chat_model in self._warmed_models,
                "warmed_models": sorted(self._warmed_models),
                "warmup_state": self._warmup_state,
                "last_error": self._last_error,
                "last_checked_at": self._last_checked_at,
                "last_warmed_at": self._last_warmed_at,
            }

    def get_status(self) -> dict[str, Any]:
        return self._snapshot(self._service())

    async def check_health(self) -> dict[str, Any]:
        service = self._service()
        payload = await service.check_local_health()
        config = service.runtime_config()
        timestamp = datetime.now().isoformat(timespec="seconds")

        with self._lock:
            self._last_health_payload = dict(payload)
            self._last_checked_at = timestamp
            if payload.get("ok"):
                self._last_error = ""
                available_models = set(payload.get("models", []))
                self._warmed_models.intersection_update(available_models)
                self._warmup_state = "ready" if config["chat_model"] in self._warmed_models else "idle"
            else:
                self._last_error = payload.get("error", "") or "Ollama 不可用"
                self._warmed_models.clear()
                self._warmup_state = "error"

        status = self._snapshot(service)
        status["version"] = payload.get("version", "")
        return status

    async def warmup_chat_model(self) -> dict[str, Any]:
        service = self._service()
        with self._lock:
            self._warmup_state = "warming"
            self._last_error = ""

        try:
            result = await service.warmup_chat_model()
        except Exception as exc:
            with self._lock:
                self._warmup_state = "error"
                self._last_error = str(exc)
            raise

        timestamp = datetime.now().isoformat(timespec="seconds")

        with self._lock:
            for item in result.get("models", []):
                model_name = (item.get("model") or "").strip()
                if item.get("ok") and model_name:
                    self._warmed_models.add(model_name)
            self._last_warmed_at = timestamp
            self._last_error = ""
            self._warmup_state = "ready"

        status = self._snapshot(service)
        status["warmup"] = result
        return status

    async def prepare_for_class_start(self) -> dict[str, Any]:
        health = await self.check_health()
        if not health.get("online"):
            raise RuntimeError(health.get("last_error") or "Ollama 未在线")
        if not health.get("chat_model_available"):
            raise RuntimeError(f"未找到课堂短答模型：{health['chat_model']}")

        warmup = await self.warmup_chat_model()
        return {
            "health": health,
            "warmup": warmup.get("warmup", {}),
            "status": warmup,
        }


local_llm_runtime = LocalLLMRuntime()
