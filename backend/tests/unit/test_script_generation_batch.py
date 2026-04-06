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


class _CapturingTemplateManager:
    def __init__(self):
        self.calls = []

    def render_template(self, template_name, payload):
        self.calls.append((template_name, payload))
        return "captured prompt"


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


@pytest.mark.asyncio
async def test_generate_scene_script_renders_scene_thesis_and_story_context(monkeypatch):
    fake_llm = _FakeLLM()
    template_manager = _CapturingTemplateManager()

    def _fake_service():
        return fake_llm

    monkeypatch.setattr(
        "app.agents.tools.ai_services.service_interfaces.get_llm_service",
        _fake_service,
    )
    monkeypatch.setattr(
        "app.agents.prompts.template_manager.get_template_manager",
        lambda *_args, **_kwargs: template_manager,
    )

    tool = ScriptGenerationTool()
    tool_input = ToolInput(
        action="generate_scene_script",
        parameters={
            "scene_data": {
                "scene_number": 3,
                "scene_thesis": "黑袍修士先手压制，韩立正面迎击，局势升级为爆炸失控",
                "title": "修仙激战",
                "visual_description": "黑袍修士悬空压制，韩立在破碎山石间迎战",
                "narrative_description": "这一幕负责把冲突推到最高点",
                "duration": 10,
            },
            "context": {
                "narrative_arc": "凡人逆袭，踏入修仙世界后不断面对更强敌手",
                "episode_context": {
                    "title": "Episode 1",
                    "summary": "韩立从凡人修炼到直面强敌",
                    "narrative_purpose": "把局势推向第一次真正失控",
                },
                "project_context": {
                    "project_brief": "修仙成长预告片",
                    "global_theme": "逆袭与代价",
                },
                "approved_script": "00:20-00:30 韩立迎战黑袍修士，冲突升级。",
            },
        },
    )

    result = await tool.execute(tool_input)

    assert result.success is True
    assert template_manager.calls
    template_name, payload = template_manager.calls[-1]
    assert template_name == "scene_script_generation"
    assert payload["scene_thesis"].startswith("黑袍修士先手压制")
    assert "10s" in payload["duration_guidance"]
    assert "全片主线" in payload["story_context_block"]
    assert "修仙成长预告片" in payload["story_context_block"]
    assert "00:20-00:30" in payload["story_context_block"]
