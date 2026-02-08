import json
import pytest

from app.agents.tools.ai_services.script_generation_tool import ScriptGenerationTool
from app.agents.tools.base_tool import ToolInput


class _FakeLLM:
    def __init__(self, *, fail_after=None):
        self.calls = 0
        self.fail_after = fail_after

    async def chat_completion(self, *args, **kwargs):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("mock failure")
        payload = {
            "duration": 10,
            "script_text": f"script-{self.calls}",
            "narrative_description": "mock narrative",
            "background_music_style": "mock",
            "sound_effects": [],
            "voice_over_text": "mock voice",
            "motion_beats": [],
        }
        return {
            "content": json.dumps(payload, ensure_ascii=False),
            "finish_reason": "stop",
            "model": "mock",
        }


@pytest.mark.asyncio
async def test_script_generation_batch_success(monkeypatch):
    fake_llm = _FakeLLM()

    def _fake_service():
        return fake_llm

    monkeypatch.setattr(
        "app.agents.tools.ai_services.service_interfaces.get_llm_service",
        _fake_service,
    )

    tool = ScriptGenerationTool()
    tool_input = ToolInput(
        action="generate_scene_scripts_batch",
        parameters={
            "scenes": [
                {
                    "scene_number": 1,
                    "scene_data": {
                        "scene_number": 1,
                        "visual_description": "scene one",
                        "narrative_description": "scene one",
                        "duration": 10,
                    },
                },
                {
                    "scene_number": 2,
                    "scene_data": {
                        "scene_number": 2,
                        "visual_description": "scene two",
                        "narrative_description": "scene two",
                        "duration": 10,
                    },
                },
            ]
        },
    )

    result = await tool.execute(tool_input)

    assert result.success is True
    payload = result.result
    assert payload.get("batch_success") is True
    scripts = payload.get("scripts") or {}
    assert len(scripts) == 2
    assert payload.get("failures") == []
    assert payload.get("failure_count") == 0


@pytest.mark.asyncio
async def test_script_generation_batch_partial_failure(monkeypatch):
    fake_llm = _FakeLLM(fail_after=1)

    def _fake_service():
        return fake_llm

    monkeypatch.setattr(
        "app.agents.tools.ai_services.service_interfaces.get_llm_service",
        _fake_service,
    )

    tool = ScriptGenerationTool()
    tool_input = ToolInput(
        action="generate_scene_scripts_batch",
        parameters={
            "scenes": [
                {
                    "scene_number": 1,
                    "scene_data": {
                        "scene_number": 1,
                        "visual_description": "scene one",
                        "narrative_description": "scene one",
                        "duration": 10,
                    },
                },
                {
                    "scene_number": 2,
                    "scene_data": {
                        "scene_number": 2,
                        "visual_description": "scene two",
                        "narrative_description": "scene two",
                        "duration": 10,
                    },
                },
            ]
        },
    )

    result = await tool.execute(tool_input)

    assert result.success is True
    payload = result.result
    scripts = payload.get("scripts") or {}
    failures = payload.get("failures") or []
    assert payload.get("batch_success") is False
    assert len(scripts) == 1
    assert len(failures) == 1
    assert payload.get("failure_count") == 1
