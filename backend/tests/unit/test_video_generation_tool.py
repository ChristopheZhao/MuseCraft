import asyncio
import types

import pytest

from app.agents.tools.ai_services import video_generation_tool_v2 as vgt_module
from app.agents.tools.ai_services.video_generation_tool_v2 import VideoGenerationTool
from app.core.consistency_policy import ConsistencyPolicy, PromptSafetyPolicy
from app.agents.tools.base_tool import ToolError


def test_prompt_safety_preserves_locked_segments(monkeypatch):
    """Locked segments should survive strict sanitization when preservation is enabled."""

    policy = ConsistencyPolicy(
        prompt_safety=PromptSafetyPolicy(
            enabled=True,
            level="strict",
            preserve_locked_sections=True,
            rewrite_model=None,
            enable_rewrite_on_sensitive_error=False,
        )
    )
    monkeypatch.setattr(vgt_module, "get_consistency_policy", lambda: policy)

    tool = VideoGenerationTool()

    captured_prompts: list[str] = []

    async def fake_generate_video(self, params):
        captured_prompts.append(params.get("prompt", ""))
        return {
            "video_url": "https://stub.example/video.mp4",
            "provider": "stub",
            "model": params.get("model", "stub-model"),
        }

    tool._generate_video = types.MethodType(fake_generate_video, tool)

    params = {
        "prompt": "风格锁定：鲜血与尘土交织",
        "duration": 10,
        "scene_number": 5,
        "workflow_state_id": "wf-test",
        "_consistency_meta": {
            "style": {
                "5": {
                    "locked": ["鲜血与尘土交织"],
                    "suggestions": [],
                }
            },
            "negative": {},
        },
    }

    async def _run():
        await tool._generate_with_continuity(dict(params))

    asyncio.run(_run())

    assert captured_prompts, "tool should invoke _generate_video"
    final_prompt = captured_prompts[0]
    assert "鲜血与尘土交织" in final_prompt, "locked segment must remain unchanged"
    assert "墨色光芒" not in final_prompt, "sanitizer replacement should be skipped for locked segments"
    assert "PG-13" not in final_prompt, "advisory text must not appear in final prompt"


def test_sensitive_error_triggers_prompt_rewrite(monkeypatch):
    """Sensitive content errors should invoke rewrite flow and annotate the result."""

    policy = ConsistencyPolicy(
        prompt_safety=PromptSafetyPolicy(
            enabled=True,
            level="moderate",
            preserve_locked_sections=True,
            rewrite_model="glm-4.5-air",
            enable_rewrite_on_sensitive_error=True,
        )
    )
    monkeypatch.setattr(vgt_module, "get_consistency_policy", lambda: policy)

    rewritten_prompt = "改写后的安全提示词"

    def fake_generate_text(**kwargs):
        return {
            "content": rewritten_prompt,
            "usage": {"total_tokens": 12},
        }

    monkeypatch.setattr(vgt_module.enhanced_ai_client, "generate_text", fake_generate_text)

    tool = VideoGenerationTool()

    call_prompts: list[str] = []

    async def fake_generate_video(self, params):
        call_prompts.append(params.get("prompt", ""))
        if len(call_prompts) == 1:
            raise ToolError(
                "provider rejected content",
                self.metadata.name,
                error_code="OutputVideoSensitiveContentDetected",
            )
        return {
            "video_url": "https://stub.example/video.mp4",
            "provider": "stub",
            "model": params.get("model", "stub-model"),
        }

    tool._generate_video = types.MethodType(fake_generate_video, tool)

    params = {
        "prompt": "包含敏感描述的提示词",
        "duration": 10,
        "scene_number": 3,
        "workflow_state_id": "wf-sensitive",
        "_consistency_meta": {},
    }

    async def _run():
        return await tool._generate_with_continuity(dict(params))

    result = asyncio.run(_run())

    assert len(call_prompts) == 2, "tool should retry once after rewrite"
    assert all("PG-13" not in prompt for prompt in call_prompts), "advisory text must not appear in prompts"
    assert call_prompts[1] == rewritten_prompt
    assert result.get("prompt_safety_rewrite", {}).get("applied") is True
    assert result["prompt_safety_rewrite"].get("reason") == "sensitive_error"


def test_generate_video_propagates_sensitive_error_code(monkeypatch):
    """_generate_video should preserve provider error codes for downstream handling."""

    policy = ConsistencyPolicy()
    monkeypatch.setattr(vgt_module, "get_consistency_policy", lambda: policy)

    tool = VideoGenerationTool()
    tool._functional = True

    class _StubVideoService:
        async def generate_video(self, **kwargs):
            return {
                "status": "FAILED",
                "model": kwargs.get("model", "stub-model"),
                "provider": "doubao",
                "provider_error": {
                    "code": "OutputVideoSensitiveContentDetected",
                    "message": "provider rejected content",
                },
            }

    class _StubVideoConfig:
        def __init__(self):
            self._config = types.SimpleNamespace(
                resolution_options=[],
                resolution_aliases={},
                ratio_options=[],
                ratio_aliases={},
                duration_capabilities=[10],
                provider_name="stub-provider",
            )

        def get_current_provider_config(self):
            return self._config

    tool.video_service = _StubVideoService()
    tool.video_config = _StubVideoConfig()
    tool._fetch_capabilities = lambda: None  # skip capability lookup for test determinism

    params = {
        "prompt": "包含敏感描述的提示词",
        "duration": 10,
        "scene_number": 1,
        "workflow_state_id": "wf-sensitive",
    }

    async def _run():
        await tool._generate_video(dict(params))

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(_run())

    assert excinfo.value.error_code == "OutputVideoSensitiveContentDetected"
