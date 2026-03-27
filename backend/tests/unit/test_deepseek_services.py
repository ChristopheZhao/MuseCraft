import asyncio

import httpx

from app.agents.tools.ai_services.deepseek_services import DeepSeekLLMService


class _DummyResponse:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _RecordingAsyncClient:
    init_log = []
    request_log = []
    response_payload = {}

    def __init__(self, *_, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        _RecordingAsyncClient.init_log.append(dict(self.kwargs))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        _RecordingAsyncClient.request_log.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
            }
        )
        return _DummyResponse(_RecordingAsyncClient.response_payload)


def test_chat_completion_passes_json_response_format(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.init_log.clear()
    _RecordingAsyncClient.request_log.clear()
    _RecordingAsyncClient.response_payload = {
        "choices": [
            {
                "message": {
                    "content": "{\"ok\":true}",
                    "reasoning_content": "trace",
                },
                "finish_reason": "stop",
            }
        ],
        "model": "deepseek-chat",
        "usage": {"total_tokens": 11},
    }

    service = DeepSeekLLMService(
        {
            "api_key": "deepseek-test-key",
            "base_url": "https://deepseek.example",
            "timeout": 45,
            "default_model": "deepseek-chat",
        }
    )
    result = asyncio.run(
        service.chat_completion(
            messages=[{"role": "user", "content": "return valid json"}],
            response_format={"type": "json_object"},
            request_timeout=30,
            max_tokens=512,
        )
    )

    assert _RecordingAsyncClient.init_log == [{"timeout": 30.0, "trust_env": True}]
    assert _RecordingAsyncClient.request_log[0]["url"] == "https://deepseek.example/chat/completions"
    assert _RecordingAsyncClient.request_log[0]["json"]["response_format"] == {"type": "json_object"}
    assert _RecordingAsyncClient.request_log[0]["json"]["model"] == "deepseek-chat"
    assert result["content"] == "{\"ok\":true}"
    assert result["reasoning_content"] == "trace"
    assert result["provider"] == "deepseek"


def test_function_call_returns_tool_calls(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)
    _RecordingAsyncClient.init_log.clear()
    _RecordingAsyncClient.request_log.clear()
    _RecordingAsyncClient.response_payload = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "select_plan",
                                "arguments": "{\"choice\":\"A\"}",
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "model": "deepseek-chat",
        "usage": {"total_tokens": 7},
    }

    service = DeepSeekLLMService(
        {
            "api_key": "deepseek-test-key",
            "base_url": "https://deepseek.example",
            "timeout": 60,
        }
    )
    result = asyncio.run(
        service.function_call(
            messages=[{"role": "user", "content": "choose"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "select_plan",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            response_format={"type": "json_object"},
        )
    )

    assert _RecordingAsyncClient.request_log[0]["json"]["tools"][0]["function"]["name"] == "select_plan"
    assert "response_format" not in _RecordingAsyncClient.request_log[0]["json"]
    assert result["has_function_call"] is True
    assert result["tool_calls"][0]["function"]["name"] == "select_plan"
