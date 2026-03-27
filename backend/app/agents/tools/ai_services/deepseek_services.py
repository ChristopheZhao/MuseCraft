"""
DeepSeek LLM service implementation.

DeepSeek exposes an OpenAI-compatible `/chat/completions` API.
"""

from __future__ import annotations

import httpx
import logging
from typing import Any, Dict, List, Optional, Union

from .service_interfaces import LLMServiceInterface, ServiceProvider
from ....core.config import settings


class DeepSeekLLMService(LLMServiceInterface):
    """DeepSeek OpenAI-compatible LLM service."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self.api_key = self._get_api_key()
        self.base_url = self.config.get("base_url") or getattr(
            settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.timeout = int(self.config.get("timeout") or 120)
        self.default_model = self.config.get("default_model") or getattr(
            settings, "DEEPSEEK_DEFAULT_MODEL", "deepseek-chat"
        )
        self.supported_models = ["deepseek-chat", "deepseek-reasoner"]

    def _get_api_key(self) -> Optional[str]:
        api_key = self.config.get("api_key")
        if api_key:
            return api_key
        return getattr(settings, "DEEPSEEK_API_KEY", None)

    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def get_provider_name(self) -> str:
        return ServiceProvider.DEEPSEEK.value

    def get_supported_models(self) -> List[str]:
        return list(self.supported_models)

    def _resolve_effective_timeout(
        self,
        *,
        model: Optional[str],
        request_timeout: Optional[Union[int, float]],
    ) -> float:
        effective_timeout: Optional[float] = None
        try:
            if request_timeout is not None:
                effective_timeout = float(request_timeout)
            elif model:
                try:
                    from ....core.ai_config import get_ai_config  # type: ignore

                    mc = get_ai_config().get_model_config(model)
                    if mc and getattr(mc, "timeout", None):
                        effective_timeout = float(mc.timeout)
                except Exception:
                    pass
            if effective_timeout is None:
                effective_timeout = float(self.timeout)
            else:
                effective_timeout = max(5.0, min(float(self.timeout), effective_timeout))
        except Exception:
            effective_timeout = float(self.timeout)
        return effective_timeout

    async def _post_json(
        self,
        *,
        payload: Dict[str, Any],
        timeout: float,
        log_prefix: str,
    ) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout, trust_env=True) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        if response.status_code != 200:
            raise RuntimeError(f"{log_prefix} API error: {response.status_code} - {response.text}")
        return response.json()

    def _normalize_chat_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        choice = result["choices"][0]
        message = choice.get("message", {}) or {}
        return {
            "content": message.get("content"),
            "reasoning_content": message.get("reasoning_content"),
            "model": result.get("model"),
            "usage": result.get("usage", {}),
            "finish_reason": choice.get("finish_reason"),
            "provider": self.get_provider_name(),
        }

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("DeepSeekLLMService not available - API key required")

        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": kwargs.get("top_p", 0.7),
            "stream": kwargs.get("stream", False),
        }
        if "response_format" in kwargs and kwargs["response_format"]:
            payload["response_format"] = kwargs["response_format"]

        effective_timeout = self._resolve_effective_timeout(
            model=payload["model"],
            request_timeout=kwargs.get("request_timeout"),
        )
        try:
            result = await self._post_json(
                payload=payload,
                timeout=effective_timeout,
                log_prefix="DeepSeek LLM API",
            )
            return self._normalize_chat_response(result)
        except Exception as exc:
            raise RuntimeError(f"DeepSeek LLM chat completion failed: {exc}") from exc

    async def function_call(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
        model: str = None,
        temperature: float = 0.3,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("DeepSeekLLMService not available - API key required")

        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature,
            "max_tokens": kwargs.get("max_tokens", 2000),
        }
        rf = kwargs.get("response_format")
        if rf and not tools:
            payload["response_format"] = rf

        effective_timeout = self._resolve_effective_timeout(
            model=payload["model"],
            request_timeout=kwargs.get("request_timeout"),
        )
        try:
            result = await self._post_json(
                payload=payload,
                timeout=effective_timeout,
                log_prefix="DeepSeek Function Call API",
            )
            response = self._normalize_chat_response(result)
            response["has_function_call"] = False
            choice = result["choices"][0]
            message = choice.get("message", {}) or {}
            tool_calls = message.get("tool_calls")
            if tool_calls:
                response["tool_calls"] = tool_calls
                response["has_function_call"] = True
            return response
        except Exception as exc:
            raise RuntimeError(f"DeepSeek Function Call failed: {exc}") from exc
