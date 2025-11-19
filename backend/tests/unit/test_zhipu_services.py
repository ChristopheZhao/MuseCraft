import httpx
import pytest

from backend.app.agents.tools.ai_services.zhipu_services import ZhipuLLMService
from backend.app.core.config import settings


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


@pytest.mark.asyncio
async def test_chat_completion_fallback_on_connect_error(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)
    DummyAsyncClient.call_log.clear()
    monkeypatch.setattr(settings, "NETWORK_DIRECT_FALLBACK_ON_TIMEOUT", True, raising=False)

    service = ZhipuLLMService({"api_key": "test", "base_url": "https://fake", "timeout": 5})
    result = await service.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert DummyAsyncClient.call_log == [True, False]
    assert result["content"] == "{}"
    assert result["model"] == "glm-test"


@pytest.mark.asyncio
async def test_function_call_fallback_on_connect_error(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)
    DummyAsyncClient.call_log.clear()
    monkeypatch.setattr(settings, "NETWORK_DIRECT_FALLBACK_ON_TIMEOUT", True, raising=False)

    service = ZhipuLLMService({"api_key": "test", "base_url": "https://fake", "timeout": 5})
    result = await service.function_call(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
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


@pytest.mark.asyncio
async def test_chat_completion_raises_without_fallback(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", AlwaysFailAsyncClient)
    monkeypatch.setattr(settings, "NETWORK_DIRECT_FALLBACK_ON_TIMEOUT", False, raising=False)

    service = ZhipuLLMService({"api_key": "test", "base_url": "https://fake", "timeout": 5})

    with pytest.raises(RuntimeError) as exc:
        await service.chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert "connection failed" in str(exc.value)
