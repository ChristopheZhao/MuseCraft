import asyncio
from types import SimpleNamespace

from app.agents.tools.ai_services import suno_client as suno_module
from app.agents.tools.ai_services.suno_client import SunoClientTool
from app.core.consistency_policy import ConsistencyPolicy, PromptSafetyPolicy


class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


class FakeClient:
    def __init__(self, responses):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        return self._responses.pop(0)


def test_audio_sensitive_error_triggers_one_shot_rewrite(monkeypatch):
    # Enable rewrite-on-sensitive policy
    policy = ConsistencyPolicy(
        prompt_safety=PromptSafetyPolicy(
            enabled=True,
            level="moderate",
            preserve_locked_sections=True,
            rewrite_model="glm-4.5-air",
            enable_rewrite_on_sensitive_error=True,
        )
    )
    monkeypatch.setattr(suno_module, "get_consistency_policy", lambda: policy)

    # Sensitive detection True & rewrite returns a new prompt
    monkeypatch.setattr(suno_module, "ps_is_sensitive_error", lambda err: True)

    async def fake_rewrite(prompt, locks, **kw):
        return "REWRITTEN_AUDIO_PROMPT", {"tokens": 7}

    monkeypatch.setattr(suno_module, "ps_rewrite_preserving_locks", fake_rewrite)

    # Prepare fake httpx client: first call returns 400 (SensitiveContent), second returns 200 with taskId
    responses_first = [
        FakeResponse(status_code=400, text="SensitiveContent"),
    ]
    responses_second = [
        FakeResponse(status_code=200, json_data={"code": 200, "data": {"taskId": "abc"}}),
    ]

    # Patch AsyncClient to yield prepared responses sequentially
    class ClientFactory:
        def __init__(self):
            self.calls = 0

        def __call__(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return FakeClient(list(responses_first))
            return FakeClient(list(responses_second))

    cf = ClientFactory()
    monkeypatch.setattr(suno_module.httpx, "AsyncClient", cf)

    # Stub poll to finish immediately
    async def fake_poll(self, task_id: str):
        return {"audio_url": "https://audio.example.com/ok.mp3"}

    # Initialize tool with api key
    tool = SunoClientTool(config={"api_key": "stub", "base_url": "https://api.suno.test"})
    tool._initialize()
    monkeypatch.setattr(SunoClientTool, "_poll_generation_status", fake_poll)

    async def _run():
        return await tool._generate_background_music({
            "description": "calm ambient background",
            "style": "ambient",
            "duration": 30,
            "instrumental": True,
            "title": "Test",
            "model": "V3_5",
        })

    result = asyncio.run(_run())

    assert result["audio_url"].endswith(".mp3")
    assert result.get("prompt_safety_rewrite", {}).get("applied") is True
    # ensure two client contexts created (first fail, second retry)
    assert cf.calls == 2
