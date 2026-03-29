import asyncio
import json

import pytest

from app.agents.tools import image_prompt_composer_tool as composer_module
from app.agents.tools.ai_services.doubao_services import DoubaoVLMService
from app.agents.tools.ai_services.service_interfaces import EnumCapability, ImageGenerationCapabilities
from app.agents.tools.ai_services.zhipu_services import ZhipuVLMService
from app.agents.tools.base_tool import ToolInput
from app.agents.tools.image_prompt_composer_tool import ImagePromptComposerTool
from app.agents.utils import fc_param_guard as guard_module
from app.agents.utils.fc_param_guard import FCParamGuard, FCParamPolicyViolation


class _DummyImageAgent:
    agent_name = "image_generator"


def test_doubao_vlm_capabilities_publish_canonical_2k_size():
    caps = DoubaoVLMService(config={"api_key": "k", "image_model": "seedream-test"}).get_capabilities()

    assert caps.size is not None
    assert caps.size.options == ["2K"]
    assert caps.size.aliases["1024x1024"] == "2K"


def test_zhipu_vlm_capabilities_preserve_existing_size_set():
    caps = ZhipuVLMService(config={"api_key": "k"}).get_capabilities()

    assert caps.size is not None
    assert caps.size.options == ["1024x1024", "1024x1792", "1792x1024"]


def test_image_prompt_composer_does_not_invent_size_default(monkeypatch):
    tool = ImagePromptComposerTool()
    captured = {}

    monkeypatch.setattr(tool, "_load_scene_info", lambda ref: {"scenes": [{"scene_number": 1}]})
    monkeypatch.setattr(tool, "_extract_scene_entry", lambda scene_info, scene_number: {"scene_number": scene_number})
    monkeypatch.setattr(tool, "_build_scene_data", lambda scene_entry, scene_number: {"title": f"scene-{scene_number}"})
    monkeypatch.setattr(tool, "_build_style_guidance", lambda scene_info: {})
    monkeypatch.setattr(tool, "_resolve_style_name", lambda style_guidance: "")
    monkeypatch.setattr(tool, "_build_consistency_block", lambda assets: ("", []))

    class FakeImageTool:
        async def _create_image_prompt_from_scene(self, scene_data, style_name, style_guidance):
            return "东方玄幻史诗动画风格，韩立立于山村晨雾之间，细节清晰，构图稳定。"

        async def execute(self, tool_input):
            captured["image_params"] = dict(tool_input.parameters or {})
            return {"success": True, "result": {"image_url": "https://img.example.com/composer.jpg", "size": "2K"}}

    class FakeConsistencyTool:
        async def execute(self, tool_input):
            return {"success": True, "result": {"assets": {}}}

    class FakeRegistry:
        def get_tool(self, name):
            if name == "image_generation":
                return FakeImageTool()
            if name == "consistency_tool":
                return FakeConsistencyTool()
            raise AssertionError(f"unexpected tool {name}")

    monkeypatch.setattr("app.agents.tools.tool_registry.get_tool_registry", lambda: FakeRegistry())

    result = asyncio.run(
        tool._execute_impl(
            ToolInput(
                action="generate",
                parameters={"scene_number": 1, "scene_info_ref": "unused.json"},
                context={},
            )
        )
    )

    assert "size" not in captured["image_params"]
    assert result["size"] == "2K"


def test_fc_param_guard_rejects_size_outside_shared_capability_snapshot(monkeypatch):
    monkeypatch.setattr(
        guard_module,
        "get_vlm_capabilities",
        lambda: ImageGenerationCapabilities(
            size=EnumCapability(options=["2K"], aliases={"1024x1024": "2K"})
        ),
    )
    guard = FCParamGuard()
    tool_calls = [
        {
            "function": {
                "name": "image_prompt_composer.generate",
                "arguments": json.dumps({"scene_number": 1, "scene_info_ref": "ctx.json", "size": "1920x1924"}),
            }
        }
    ]

    with pytest.raises(FCParamPolicyViolation):
        guard.validate(_DummyImageAgent(), tool_calls)


def test_fc_param_guard_accepts_alias_from_shared_capability_snapshot(monkeypatch):
    monkeypatch.setattr(
        guard_module,
        "get_vlm_capabilities",
        lambda: ImageGenerationCapabilities(
            size=EnumCapability(options=["2K"], aliases={"1024x1024": "2K"})
        ),
    )
    guard = FCParamGuard()
    tool_calls = [
        {
            "function": {
                "name": "image_prompt_composer.generate",
                "arguments": json.dumps({"scene_number": 1, "scene_info_ref": "ctx.json", "size": "1024x1024"}),
            }
        }
    ]

    assert guard.validate(_DummyImageAgent(), tool_calls) == tool_calls
