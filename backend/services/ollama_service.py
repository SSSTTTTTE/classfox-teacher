"""
Ollama 本地客户端
=================
封装本地 Ollama HTTP API，提供统一的生成、JSON 输出、健康检查和预热能力。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Iterable, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class OllamaServiceError(RuntimeError):
    """Ollama 调用失败时抛出的统一异常。"""


class OllamaService:
    """Ollama 本地模型客户端。"""

    def __init__(self):
        self.base_url = (os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434") or "http://127.0.0.1:11434").rstrip("/")
        self.timeout = self._read_float_env("OLLAMA_TIMEOUT", 45.0)
        self.default_max_tokens = self._read_int_env("OLLAMA_MAX_TOKENS", 1024)
        self.default_temperature = self._read_float_env("OLLAMA_TEMPERATURE", 0.3)
        self.retry_count = max(0, self._read_int_env("OLLAMA_RETRY_COUNT", 2))
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "15m").strip() or "15m"
        self._last_error: str = ""

    @staticmethod
    def _read_float_env(key: str, default: float) -> float:
        raw = os.getenv(key, "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    @staticmethod
    def _read_int_env(key: str, default: int) -> int:
        raw = os.getenv(key, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    @property
    def last_error(self) -> str:
        return self._last_error

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        last_exception: Optional[Exception] = None

        for attempt in range(self.retry_count + 1):
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                    response = await client.request(method, path, json=payload)
                    response.raise_for_status()
                    self._last_error = ""
                    return response.json()
            except httpx.HTTPStatusError as exc:
                body = (exc.response.text or "").strip()
                self._last_error = f"Ollama HTTP {exc.response.status_code}: {body[:240]}"
                last_exception = exc
                # 4xx 通常是参数错误或模型不存在，直接抛出
                if 400 <= exc.response.status_code < 500:
                    raise OllamaServiceError(self._last_error) from exc
            except httpx.RequestError as exc:
                self._last_error = f"Ollama 请求失败: {exc}"
                last_exception = exc

            if attempt < self.retry_count:
                await asyncio.sleep(min(0.8 * (attempt + 1), 2.0))

        raise OllamaServiceError(self._last_error or f"Ollama 请求失败: {last_exception}")

    def _build_chat_payload(
        self,
        *,
        prompt: str,
        model_name: str,
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        request_options = dict(options or {})
        system_prompt = (request_options.pop("system_prompt", "") or "").strip()
        temperature = request_options.pop("temperature", self.default_temperature)
        max_tokens = request_options.pop("max_tokens", self.default_max_tokens)
        keep_alive = request_options.pop("keep_alive", self.keep_alive)
        response_format = request_options.pop("response_format", None)
        think = request_options.pop("think", False)
        ollama_options = dict(request_options.pop("ollama_options", {}) or {})

        ollama_options.setdefault("temperature", float(temperature))
        ollama_options.setdefault("num_predict", int(max_tokens))

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": ollama_options,
            "keep_alive": keep_alive,
            "think": bool(think),
        }
        if response_format is not None:
            payload["format"] = response_format
        return payload

    async def generate_answer(
        self,
        prompt: str,
        model_name: str,
        options: Optional[dict[str, Any]] = None,
    ) -> str:
        payload = self._build_chat_payload(prompt=prompt, model_name=model_name, options=options)
        data = await self._request_json("POST", "/api/chat", payload)
        message = data.get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            thinking = (message.get("thinking") or "").strip()
            if thinking:
                raise OllamaServiceError(
                    "Ollama 未返回最终回答内容；当前模型可能启用了 thinking，"
                    "请关闭 thinking 后重试。"
                )
            raise OllamaServiceError("Ollama 未返回可用文本内容。")
        return content

    async def generate_answer_stream(
        self,
        prompt: str,
        model_name: str,
        options: Optional[dict[str, Any]] = None,
        on_chunk: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    ) -> str:
        payload = self._build_chat_payload(prompt=prompt, model_name=model_name, options=options)
        payload["stream"] = True

        thinking_parts: list[str] = []
        content_parts: list[str] = []
        last_exception: Optional[Exception] = None

        for attempt in range(self.retry_count + 1):
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                    async with client.stream("POST", "/api/chat", json=payload) as response:
                        response.raise_for_status()
                        self._last_error = ""

                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                            except json.JSONDecodeError as exc:
                                raise OllamaServiceError(f"Ollama 流式响应不是合法 JSON: {line[:160]}") from exc

                            message = chunk.get("message") or {}
                            thinking_delta = message.get("thinking") or ""
                            content_delta = message.get("content") or ""

                            if thinking_delta:
                                thinking_parts.append(thinking_delta)
                            if content_delta:
                                content_parts.append(content_delta)

                            if on_chunk is not None:
                                await on_chunk(
                                    {
                                        "thinking_delta": thinking_delta,
                                        "content_delta": content_delta,
                                        "done": bool(chunk.get("done")),
                                        "done_reason": chunk.get("done_reason", ""),
                                    }
                                )

                        content = "".join(content_parts).strip()
                        if content:
                            return content

                        thinking = "".join(thinking_parts).strip()
                        if thinking:
                            raise OllamaServiceError(
                                "Ollama 未返回最终回答内容；当前模型可能启用了 thinking，"
                                "请关闭 thinking 后重试。"
                            )
                        raise OllamaServiceError("Ollama 未返回可用文本内容。")
            except httpx.HTTPStatusError as exc:
                body = (exc.response.text or "").strip()
                self._last_error = f"Ollama HTTP {exc.response.status_code}: {body[:240]}"
                last_exception = exc
                if 400 <= exc.response.status_code < 500:
                    raise OllamaServiceError(self._last_error) from exc
            except httpx.RequestError as exc:
                self._last_error = f"Ollama 请求失败: {exc}"
                last_exception = exc
            except OllamaServiceError as exc:
                self._last_error = str(exc)
                last_exception = exc
                raise

            if attempt < self.retry_count:
                await asyncio.sleep(min(0.8 * (attempt + 1), 2.0))

        raise OllamaServiceError(self._last_error or f"Ollama 请求失败: {last_exception}")

    async def generate_json(
        self,
        prompt: str,
        model_name: str,
        schema_hint: Optional[Any] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        request_options = dict(options or {})
        request_options.setdefault("response_format", schema_hint if schema_hint is not None else "json")
        json_prompt = prompt.strip()
        if "JSON" not in json_prompt.upper():
            json_prompt = f"{json_prompt}\n\n请严格输出 JSON，不要添加 markdown 代码块或额外解释。"
        content = await self.generate_answer(
            prompt=json_prompt,
            model_name=model_name,
            options=request_options,
        )
        parsed = self._extract_json_payload(content)
        if not isinstance(parsed, dict):
            raise OllamaServiceError("Ollama JSON 输出不是对象结构。")
        return parsed

    def _extract_json_payload(self, content: str) -> Any:
        text = (content or "").strip()
        if not text:
            raise OllamaServiceError("Ollama 返回了空 JSON 内容。")

        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = min([index for index in (text.find("{"), text.find("[")) if index != -1], default=-1)
            if start == -1:
                raise OllamaServiceError(f"无法解析 JSON 输出: {content[:200]}")

            closing_char = "}" if text[start] == "{" else "]"
            end = text.rfind(closing_char)
            if end == -1 or end <= start:
                raise OllamaServiceError(f"无法解析 JSON 输出: {content[:200]}")

            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError as exc:
                raise OllamaServiceError(f"无法解析 JSON 输出: {content[:200]}") from exc

    async def check_ollama_health(
        self,
        required_models: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        required = [model.strip() for model in (required_models or []) if model and model.strip()]
        try:
            version_payload = await self._request_json("GET", "/api/version")
            tags_payload = await self._request_json("GET", "/api/tags")
        except OllamaServiceError:
            return {
                "ok": False,
                "base_url": self.base_url,
                "version": "",
                "models": [],
                "missing_models": required,
                "error": self._last_error or "Ollama 不可用",
            }

        model_names = []
        for model_item in tags_payload.get("models", []):
            name = (model_item.get("model") or model_item.get("name") or "").strip()
            if name:
                model_names.append(name)

        missing_models = [model for model in required if model not in model_names]
        return {
            "ok": True,
            "base_url": self.base_url,
            "version": (version_payload.get("version") or "").strip(),
            "models": model_names,
            "missing_models": missing_models,
            "error": "",
        }

    async def warmup_model(
        self,
        model_name: str,
        prompt: str = "请只回复：已就绪",
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        request_options = dict(options or {})
        temperature = request_options.pop("temperature", 0)
        max_tokens = request_options.pop("max_tokens", 12)
        keep_alive = request_options.pop("keep_alive", self.keep_alive)
        ollama_options = dict(request_options.pop("ollama_options", {}) or {})
        ollama_options.setdefault("temperature", float(temperature))
        ollama_options.setdefault("num_predict", int(max_tokens))

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": ollama_options,
            "keep_alive": keep_alive,
        }
        data = await self._request_json("POST", "/api/generate", payload)
        return {
            "ok": True,
            "model": model_name,
            "response": (data.get("response") or "").strip(),
        }
