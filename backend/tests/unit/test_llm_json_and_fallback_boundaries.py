import asyncio
from types import SimpleNamespace

import pytest

from app.agents.tools.ai_services import service_interfaces
from app.agents.tools.ai_services.kimi_client import KimiClientTool
from app.agents.tools.ai_services.openai_client import OpenAIClientTool
from app.agents.tools.ai_services.scene_continuity_analysis_tool import (
    SceneContinuityAnalysisTool,
)
from app.agents.tools.ai_services.script_generation_tool import ScriptGenerationTool
from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolError


def _client_instance(client_type):
    client = object.__new__(client_type)
    client.metadata = client_type.get_metadata()
    client.default_model = "test-model"
    client.default_max_tokens = 256
    return client


@pytest.mark.parametrize("client_type", [KimiClientTool, ZhipuClientTool])
def test_http_provider_json_completion_requests_json_object_and_parses_once(client_type):
    client = _client_instance(client_type)
    captured = {}

    async def _chat_completion(params):
        captured.update(params)
        return {"content": '{"decision":"ok"}', "model": "test-model"}

    client._chat_completion = _chat_completion

    result = asyncio.run(client._json_completion({"prompt": "decide"}))

    assert captured["response_format"] == {"type": "json_object"}
    assert result["json_result"] == {"decision": "ok"}
    assert result["valid_json"] is True


@pytest.mark.parametrize("client_type", [KimiClientTool, ZhipuClientTool])
def test_http_provider_json_completion_rejects_wrapped_json(client_type):
    client = _client_instance(client_type)

    async def _chat_completion(_params):
        return {"content": 'prefix {"decision":"ok"} suffix', "model": "test-model"}

    client._chat_completion = _chat_completion

    with pytest.raises(ToolError, match="JSON completion failed"):
        asyncio.run(client._json_completion({"prompt": "decide"}))


def test_openai_json_completion_rejects_wrapped_json():
    client = _client_instance(OpenAIClientTool)
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content='prefix {"decision":"ok"} suffix'))
        ],
        model="test-model",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )

    async def _create(**kwargs):
        assert kwargs["response_format"] == {"type": "json_object"}
        return response

    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    with pytest.raises(ToolError, match="JSON completion failed"):
        asyncio.run(client._json_completion({"prompt": "decide"}))


def test_scene_continuity_failure_does_not_fabricate_independent_strategy(monkeypatch):
    tool = object.__new__(SceneContinuityAnalysisTool)
    tool.metadata = SceneContinuityAnalysisTool.get_metadata()
    tool.logger = SimpleNamespace(error=lambda *args, **kwargs: None)
    provider = SimpleNamespace(
        execute=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider down"))
    )
    monkeypatch.setattr(
        "app.agents.tools.tool_registry.get_tool_registry",
        lambda: SimpleNamespace(get_tool=lambda _name: provider),
    )

    with pytest.raises(ToolError, match="Scene continuity analysis failed"):
        asyncio.run(
            tool._analyze_all_scenes_continuity(
                {
                    "scenes": [
                        {"scene_number": 1, "description": "opening"},
                        {"scene_number": 2, "description": "continuation"},
                    ],
                    "overall_narrative": "one continuous action",
                }
            )
        )


def test_scene_continuity_contract_rejects_missing_scene_decision():
    tool = object.__new__(SceneContinuityAnalysisTool)
    tool.metadata = SceneContinuityAnalysisTool.get_metadata()

    with pytest.raises(ToolError, match="missing decision for scene 3"):
        tool._standardize_continuity_analysis(
            {
                "continuity_decisions": {
                    "2": {
                        "strategy": "continue_from_previous",
                        "reason": "same action",
                        "confidence": 0.9,
                    }
                },
                "analysis_summary": "partial result",
            },
            [{"scene_number": 2}, {"scene_number": 3}],
        )


def test_script_narrative_json_failure_does_not_fabricate_structure(monkeypatch):
    tool = object.__new__(ScriptGenerationTool)
    llm = SimpleNamespace(
        chat_completion=lambda **_kwargs: asyncio.sleep(
            0,
            result={"content": "not-json"},
        )
    )
    monkeypatch.setattr(service_interfaces, "get_llm_service", lambda: llm)

    with pytest.raises(ToolError, match="叙事结构生成失败"):
        asyncio.run(
            tool._generate_narrative_structure(
                {"scenes_data": [{"scene_number": 1}], "video_style": "documentary"}
            )
        )


def test_script_continuity_json_failure_does_not_fabricate_score(monkeypatch):
    tool = object.__new__(ScriptGenerationTool)
    llm = SimpleNamespace(
        chat_completion=lambda **_kwargs: asyncio.sleep(
            0,
            result={"content": "not-json"},
        )
    )
    monkeypatch.setattr(service_interfaces, "get_llm_service", lambda: llm)

    with pytest.raises(ToolError, match="连续性分析失败"):
        asyncio.run(
            tool._analyze_script_continuity(
                {"scripts": [{"text": "one"}, {"text": "two"}]}
            )
        )
