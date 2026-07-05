import asyncio
import json

import pytest

from app.agents.tools import image_prompt_composer_tool as composer_module
from app.agents.tools.ai_services import image_generation_tool as image_tool_module
from app.agents.tools.ai_services.doubao_services import DoubaoVLMService
from app.agents.tools.ai_services.service_interfaces import (
    EnumCapability,
    ImageGenerationCapabilities,
    ReferenceImageCapability,
)
from app.agents.tools.ai_services.zhipu_services import ZhipuVLMService
from app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool
from app.agents.tools.base_tool import ToolError, ToolInput
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
    assert caps.reference_image is None


def test_image_generation_schema_hides_reference_image_when_capability_missing(monkeypatch):
    monkeypatch.setattr(
        image_tool_module,
        "get_vlm_capabilities",
        lambda: ImageGenerationCapabilities(size=EnumCapability(options=["1024x1024"])),
    )
    tool = ImageGenerationTool()

    schema = tool.get_action_schema("generate_image")

    assert "reference_image_url" not in schema["properties"]


def test_image_generation_schema_exposes_reference_image_when_capability_supported(monkeypatch):
    monkeypatch.setattr(
        image_tool_module,
        "get_vlm_capabilities",
        lambda: ImageGenerationCapabilities(
            size=EnumCapability(options=["1024x1024"]),
            reference_image=ReferenceImageCapability(
                supported=True,
                max_images=1,
                input_modes=["url"],
                note="provider accepts one reference image",
            ),
        ),
    )
    tool = ImageGenerationTool()

    schema = tool.get_action_schema("generate_image")

    assert "reference_image_url" in schema["properties"]
    assert "provider accepts one reference image" in schema["properties"]["reference_image_url"]["description"]


def test_image_generation_rejects_reference_image_without_provider_capability():
    class FakeVLMService:
        def get_provider_name(self):
            return "fake"

        def get_capabilities(self):
            return ImageGenerationCapabilities(size=EnumCapability(options=["1024x1024"]))

        async def image_generation(self, **_kwargs):
            raise AssertionError("provider must not be called without reference capability")

    tool = ImageGenerationTool()
    tool._vlm_service = FakeVLMService()

    with pytest.raises(ToolError) as exc:
        asyncio.run(
            tool._generate_image(
                {
                    "prompt": "温馨动漫叙事风，母亲站在家门口，夕阳照亮围裙与柔和微笑。",
                    "size": "1024x1024",
                    "reference_image_url": "https://example.com/mother-ref.jpg",
                }
            )
        )

    assert exc.value.error_code == "image_reference_capability_missing"
    assert exc.value.details["provider"] == "fake"


def test_image_prompt_composer_does_not_invent_size_default(monkeypatch):
    tool = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    captured = {}

    monkeypatch.setattr(tool, "_load_scene_info", lambda ref: {"scenes": [{"scene_number": 1}]})
    monkeypatch.setattr(tool, "_extract_scene_entry", lambda scene_info, scene_number: {"scene_number": scene_number})
    monkeypatch.setattr(
        tool,
        "_build_scene_data",
        lambda scene_entry, scene_number, **_kwargs: {"title": f"scene-{scene_number}", "image_purpose": "scene_opening_anchor"},
    )
    monkeypatch.setattr(tool, "_build_style_guidance", lambda scene_info: {})
    monkeypatch.setattr(tool, "_resolve_style_name", lambda style_guidance: "")
    monkeypatch.setattr(tool, "_build_consistency_block", lambda assets, **_kwargs: ("", [], []))
    monkeypatch.setattr(
        tool,
        "_compose_prompt_text",
        lambda scene_data, **_kwargs: "东方玄幻史诗动画风格，韩立立于山村晨雾之间，细节清晰，构图稳定。",
    )

    class FakeImageTool:
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


def test_image_prompt_composer_marks_reference_assets_unavailable_without_schema(monkeypatch):
    tool = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    captured = {}

    monkeypatch.setattr(tool, "_load_scene_info", lambda ref: {"scenes": [{"scene_number": 1}]})
    monkeypatch.setattr(tool, "_extract_scene_entry", lambda scene_info, scene_number: {"scene_number": scene_number})
    monkeypatch.setattr(
        tool,
        "_build_scene_data",
        lambda scene_entry, scene_number, **_kwargs: {"title": f"scene-{scene_number}"},
    )
    monkeypatch.setattr(tool, "_build_style_guidance", lambda scene_info: {})
    monkeypatch.setattr(tool, "_resolve_style_name", lambda style_guidance: "")
    monkeypatch.setattr(tool, "_build_consistency_block", lambda assets, **_kwargs: ("", [], []))
    monkeypatch.setattr(
        tool,
        "_compose_prompt_text",
        lambda scene_data, **_kwargs: "温馨动漫叙事风，母亲在家门口等待孩子归来。",
    )

    class FakeImageTool:
        def get_action_schema(self, action):
            assert action == "generate_image"
            return {"type": "object", "properties": {"prompt": {"type": "string"}}}

        async def execute(self, tool_input):
            captured["image_params"] = dict(tool_input.parameters or {})
            return {"success": True, "result": {"image_url": "https://img.example.com/scene.jpg"}}

    class FakeConsistencyTool:
        async def execute(self, tool_input):
            return {
                "success": True,
                "result": {
                    "assets": {
                        "characters": {
                            "characters": [
                                {
                                    "canonical_id": "mother",
                                    "display_name": "妈妈",
                                    "reference_assets": [
                                        {
                                            "asset_type": "character_reference",
                                            "uri": "https://img.example.com/mother-ref.jpg",
                                            "capability_required": "reference_image",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                },
            }

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

    diagnostics = result["metadata"]["reference_asset_diagnostics"]
    assert "reference_image_url" not in captured["image_params"]
    assert diagnostics["status"] == "unavailable"
    assert diagnostics["reference_asset_count"] == 1
    assert diagnostics["fallback_reason"] == "image_reference_capability_missing"


def test_image_prompt_composer_passes_reference_asset_when_schema_supports_it(monkeypatch):
    tool = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    captured = {}

    monkeypatch.setattr(tool, "_load_scene_info", lambda ref: {"scenes": [{"scene_number": 1}]})
    monkeypatch.setattr(tool, "_extract_scene_entry", lambda scene_info, scene_number: {"scene_number": scene_number})
    monkeypatch.setattr(
        tool,
        "_build_scene_data",
        lambda scene_entry, scene_number, **_kwargs: {"title": f"scene-{scene_number}"},
    )
    monkeypatch.setattr(tool, "_build_style_guidance", lambda scene_info: {})
    monkeypatch.setattr(tool, "_resolve_style_name", lambda style_guidance: "")
    monkeypatch.setattr(tool, "_build_consistency_block", lambda assets, **_kwargs: ("", [], []))
    monkeypatch.setattr(
        tool,
        "_compose_prompt_text",
        lambda scene_data, **_kwargs: "温馨动漫叙事风，母亲在家门口等待孩子归来。",
    )

    class FakeImageTool:
        def get_action_schema(self, action):
            assert action == "generate_image"
            return {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "reference_image_url": {"type": "string"},
                },
            }

        async def execute(self, tool_input):
            captured["image_params"] = dict(tool_input.parameters or {})
            return {"success": True, "result": {"image_url": "https://img.example.com/scene.jpg"}}

    class FakeConsistencyTool:
        async def execute(self, tool_input):
            return {
                "success": True,
                "result": {
                    "assets": {
                        "characters": {
                            "characters": [
                                {
                                    "canonical_id": "mother",
                                    "display_name": "妈妈",
                                    "reference_assets": [
                                        {
                                            "asset_type": "character_reference",
                                            "uri": "https://img.example.com/mother-ref.jpg",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                },
            }

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

    diagnostics = result["metadata"]["reference_asset_diagnostics"]
    assert captured["image_params"]["reference_image_url"] == "https://img.example.com/mother-ref.jpg"
    assert diagnostics["status"] == "enabled"
    assert diagnostics["selected_reference_asset"]["canonical_id"] == "mother"


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
