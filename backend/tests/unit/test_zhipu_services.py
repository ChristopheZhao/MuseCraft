import asyncio
import httpx
import pytest

from app.agents.tools.ai_services.zhipu_services import ZhipuLLMService
from app.core.config import settings


class DummyResponse:
    status_code = 200

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": "{}",
                        "reasoning_content": "",
                    },
                    "finish_reason": "stop",
                }
            ],
            "model": "glm-test",
            "usage": {"total_tokens": 10},
        }


class DummyAsyncClient:
    call_log = []

    def __init__(self, *_, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        DummyAsyncClient.call_log.append(self.kwargs.get("trust_env"))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        if self.kwargs.get("trust_env", True):
            raise httpx.ConnectError("proxy connect failed", request=httpx.Request("POST", url))
        return DummyResponse()


def test_chat_completion_fallback_on_connect_error(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)
    DummyAsyncClient.call_log.clear()
    monkeypatch.setattr(settings, "NETWORK_DIRECT_FALLBACK_ON_TIMEOUT", True, raising=False)
    monkeypatch.setattr(settings, "LLM_FALLBACK_TIMEOUT_MIN", 1, raising=False)
    monkeypatch.setattr(settings, "LLM_REQUEST_SAFETY_MARGIN", 0, raising=False)

    service = ZhipuLLMService({"api_key": "test", "base_url": "https://fake", "timeout": 5})
    result = asyncio.run(service.chat_completion(messages=[{"role": "user", "content": "hi"}]))

    assert DummyAsyncClient.call_log == [True, False]
    assert result["content"] == "{}"
    assert result["model"] == "glm-test"


def test_function_call_fallback_on_connect_error(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)
    DummyAsyncClient.call_log.clear()
    monkeypatch.setattr(settings, "NETWORK_DIRECT_FALLBACK_ON_TIMEOUT", True, raising=False)
    monkeypatch.setattr(settings, "LLM_FALLBACK_TIMEOUT_MIN", 1, raising=False)
    monkeypatch.setattr(settings, "LLM_REQUEST_SAFETY_MARGIN", 0, raising=False)

    service = ZhipuLLMService({"api_key": "test", "base_url": "https://fake", "timeout": 5})
    result = asyncio.run(
        service.function_call(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
    )

    assert DummyAsyncClient.call_log == [True, False]
    assert result["content"] == "{}"
    assert result["model"] == "glm-test"


class AlwaysFailAsyncClient:
    def __init__(self, *_, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        raise httpx.ConnectError("proxy connect failed", request=httpx.Request("POST", url))


def test_chat_completion_raises_without_fallback(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", AlwaysFailAsyncClient)
    monkeypatch.setattr(settings, "NETWORK_DIRECT_FALLBACK_ON_TIMEOUT", False, raising=False)

    service = ZhipuLLMService({"api_key": "test", "base_url": "https://fake", "timeout": 5})

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(service.chat_completion(messages=[{"role": "user", "content": "hi"}]))
    assert "proxy connect failed" in str(exc.value)


class TimeoutThenSuccessAsyncClient:
    call_log = []

    def __init__(self, *_, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        TimeoutThenSuccessAsyncClient.call_log.append(
            {
                "trust_env": self.kwargs.get("trust_env"),
                "timeout": self.kwargs.get("timeout"),
            }
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        if self.kwargs.get("trust_env", True):
            raise httpx.ReadTimeout("proxy timeout", request=httpx.Request("POST", url))
        return DummyResponse()


def test_chat_completion_uses_remaining_budget_for_direct_fallback(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", TimeoutThenSuccessAsyncClient)
    TimeoutThenSuccessAsyncClient.call_log.clear()
    monkeypatch.setattr(settings, "NETWORK_DIRECT_FALLBACK_ON_TIMEOUT", True, raising=False)
    monkeypatch.setattr(settings, "LLM_PRIMARY_TIMEOUT_RATIO", 0.5, raising=False)
    monkeypatch.setattr(settings, "LLM_FALLBACK_TIMEOUT_MIN", 2, raising=False)
    monkeypatch.setattr(settings, "LLM_REQUEST_SAFETY_MARGIN", 0, raising=False)
    monkeypatch.setattr(
        ZhipuLLMService,
        "_remaining_fallback_budget",
        lambda self, total_timeout, started_at: 4.0,
    )

    service = ZhipuLLMService({"api_key": "test", "base_url": "https://fake", "timeout": 10})
    result = asyncio.run(
        service.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            request_timeout=10,
        )
    )

    assert result["content"] == "{}"
    assert TimeoutThenSuccessAsyncClient.call_log == [
        {"trust_env": True, "timeout": 5.0},
        {"trust_env": False, "timeout": 4.0},
    ]


def test_chat_completion_fails_when_no_remaining_budget_for_direct_fallback(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", TimeoutThenSuccessAsyncClient)
    TimeoutThenSuccessAsyncClient.call_log.clear()
    monkeypatch.setattr(settings, "NETWORK_DIRECT_FALLBACK_ON_TIMEOUT", True, raising=False)
    monkeypatch.setattr(settings, "LLM_PRIMARY_TIMEOUT_RATIO", 0.5, raising=False)
    monkeypatch.setattr(settings, "LLM_FALLBACK_TIMEOUT_MIN", 6, raising=False)
    monkeypatch.setattr(settings, "LLM_REQUEST_SAFETY_MARGIN", 0, raising=False)
    monkeypatch.setattr(
        ZhipuLLMService,
        "_remaining_fallback_budget",
        lambda self, total_timeout, started_at: 4.0,
    )

    service = ZhipuLLMService({"api_key": "test", "base_url": "https://fake", "timeout": 10})

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            service.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                request_timeout=10,
            )
        )

    assert "budget exhausted before direct fallback" in str(exc.value)
    assert TimeoutThenSuccessAsyncClient.call_log == [
        {"trust_env": True, "timeout": 5.0},
    ]
