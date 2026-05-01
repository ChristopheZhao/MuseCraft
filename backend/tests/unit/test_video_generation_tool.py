import asyncio
import json
import logging
import types

import pytest

from app.agents.tools.ai_services import video_generation_tool_v2 as vgt_module
from app.agents.tools.ai_services import service_interfaces
from app.agents.tools.ai_services.video_generation_tool_v2 import VideoGenerationTool
from app.services.execution_host_lease import ExecutionHostKeepaliveLostError
from app.core.consistency_policy import ConsistencyPolicy, PromptSafetyPolicy
from app.agents.tools.base_tool import ToolError
import app.agents.tools.tool_registry as tool_registry_module


def _make_video_tool_without_init():
    tool = object.__new__(VideoGenerationTool)
    tool.metadata = VideoGenerationTool.get_metadata()
    tool.config = {}
    tool.logger = logging.getLogger("test.video_generation")
    tool.video_service = None
    tool._telemetry_logger = logging.getLogger("test.video_generation.telemetry")

    class _StubVideoConfig:
        def __init__(self):
            self._config = types.SimpleNamespace(
                provider_name="stub-provider",
                model_name="stub-model",
                duration_capabilities=[5, 10],
                max_duration=10,
                default_duration=5,
                supports_first_last_frame=True,
                resolution_options=[],
                resolution_aliases={},
                ratio_options=[],
                ratio_aliases={},
                supports_native_audio=False,
                native_audio_default_enabled=False,
                native_audio_param_name="generate_audio",
                amplification_ratio=1.0,
            )

        def get_current_provider_config(self):
            return self._config

    tool.video_config = _StubVideoConfig()
    return tool


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

    async def fake_generate_video(self, params, *, execution_liveness_probe=None):
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

    async def fake_rewrite_prompt_preserving_locks(*args, **kwargs):
        return rewritten_prompt, {
            "result": "success",
            "backend": "test",
            "usage": {"total_tokens": 12},
        }

    monkeypatch.setattr(
        vgt_module,
        "ps_rewrite_preserving_locks",
        fake_rewrite_prompt_preserving_locks,
    )

    tool = VideoGenerationTool()

    call_prompts: list[str] = []

    async def fake_generate_video(self, params, *, execution_liveness_probe=None):
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


def test_generate_video_maps_keepalive_loss_to_tool_error(monkeypatch):
    tool = VideoGenerationTool()
    tool._functional = True

    class _StubVideoService:
        async def generate_video(self, **kwargs):
            raise ExecutionHostKeepaliveLostError(
                "Execution host keepalive lost",
                diagnostic={"reason_code": "heartbeat_validation_failed", "state": "stopped"},
            )

    class _StubVideoConfig:
        def __init__(self):
            self._config = types.SimpleNamespace(
                resolution_options=[],
                resolution_aliases={},
                ratio_options=[],
                ratio_aliases={},
                duration_capabilities=[10],
                provider_name="stub-provider",
                supports_native_audio=False,
                native_audio_default_enabled=False,
            )

        def get_current_provider_config(self):
            return self._config

    tool.video_service = _StubVideoService()
    tool.video_config = _StubVideoConfig()
    tool._fetch_capabilities = lambda: None

    params = {
        "prompt": "安全提示词",
        "duration": 10,
        "scene_number": 1,
        "workflow_state_id": "wf-keepalive",
    }

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(tool._generate_video(dict(params)))

    assert excinfo.value.error_code == "execution_host_keepalive_lost"
    assert excinfo.value.details["reason_code"] == "heartbeat_validation_failed"


def test_generate_video_missing_service_fails_fast_without_vendor_fallback(monkeypatch):
    tool = object.__new__(VideoGenerationTool)
    tool.metadata = VideoGenerationTool.get_metadata()
    tool.config = {}
    tool.logger = logging.getLogger("test.video_generation.missing_service")
    tool._functional = False
    tool.video_service = None

    class _StubVideoConfig:
        def get_current_provider_config(self):
            return types.SimpleNamespace(provider_name="stub-provider", model_name="stub-model")

    tool.video_config = _StubVideoConfig()

    class _StubServiceManager:
        def get_available_services(self):
            return {"video": []}

    monkeypatch.setattr(service_interfaces, "get_video_service", lambda: None)
    monkeypatch.setattr(service_interfaces, "get_service_manager", lambda: _StubServiceManager())

    def _unexpected_registry_lookup():
        raise AssertionError("vendor fallback must not be used")

    monkeypatch.setattr(tool_registry_module, "get_tool_registry", _unexpected_registry_lookup)

    params = {
        "prompt": "安全提示词",
        "duration": 5,
        "scene_number": 1,
        "workflow_state_id": "wf-missing-video-service",
    }

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(tool._generate_video(dict(params)))

    assert excinfo.value.error_code == "video_service_unavailable"
    assert excinfo.value.details["reason_code"] == "service_missing_generate_video"
    assert excinfo.value.details["service_none"] is True
    assert excinfo.value.details["missing_generate"] is True
    assert excinfo.value.details["available_video_services"] == []


def test_get_capabilities_filters_blank_supported_models():
    tool = object.__new__(VideoGenerationTool)
    tool.logger = types.SimpleNamespace(warning=lambda *args, **kwargs: None)

    provider_cfg = types.SimpleNamespace(
        provider_name="doubao",
        model_name="",
        duration_capabilities=[5, 10],
        max_duration=10,
        default_duration=5,
        supports_first_last_frame=True,
        resolution_options=["720p"],
        frame_rate_options=[24],
        supports_native_audio=True,
        native_audio_param_name="generate_audio",
        native_audio_default_enabled=True,
        amplification_ratio=1.0,
    )

    class _StubVideoConfig:
        def get_current_provider_config(self):
            return provider_cfg

        def get_system_duration_capability(self):
            return {"min_duration": 5, "max_duration": 10}

    class _StubVideoService:
        def get_supported_models(self):
            return ["", "  ", "doubao-seedance-1-5-pro", "doubao-seedance-1-5-pro"]

    tool.video_config = _StubVideoConfig()
    tool.video_service = _StubVideoService()

    result = asyncio.run(tool._get_capabilities())
    assert result["supported_models"] == ["doubao-seedance-1-5-pro"]


def test_determine_generation_mode_prefers_factual_image_inputs():
    tool = object.__new__(VideoGenerationTool)

    assert (
        tool._determine_generation_mode(
            "https://example.com/keyframe.png",
            "",
            "",
        )
        == "image_to_video"
    )


def test_generate_with_continuity_hydrates_image_url_from_scene_info_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(vgt_module, "get_consistency_policy", lambda: ConsistencyPolicy())

    scene_info = {
        "scenes_to_generate": [
            {
                "scene_number": 2,
                "duration": 10,
                "image_url": "https://example.com/scene2.png",
                "depends_on_scene": 1,
            }
        ]
    }
    scene_path = tmp_path / "scene_info.json"
    scene_path.write_text(json.dumps(scene_info, ensure_ascii=False), encoding="utf-8")

    class _FakeComposer:
        async def execute(self, tool_input):
            return types.SimpleNamespace(
                result={
                    "prompt_text": "场景 2：\n主生成目标：\n- 测试场景",
                    "metadata": {},
                }
            )

    class _FakeRegistry:
        def get_tool(self, name):
            if name == "video_prompt_composer":
                return _FakeComposer()
            raise AssertionError(f"unexpected tool lookup: {name}")

    monkeypatch.setattr(tool_registry_module, "get_tool_registry", lambda: _FakeRegistry())

    tool = VideoGenerationTool()
    tool._functional = True

    class _StubVideoService:
        async def generate_video(self, **kwargs):
            return {
                "status": "SUCCEEDED",
                "video_url": "https://stub.example/video.mp4",
                "provider": "stub",
                "model": kwargs.get("model", "stub-model"),
            }

    class _StubVideoConfig:
        def __init__(self):
            self._config = types.SimpleNamespace(
                provider_name="stub-provider",
                model_name="stub-model",
                duration_capabilities=[5, 10],
                max_duration=10,
                default_duration=5,
                supports_first_last_frame=True,
                resolution_options=[],
                resolution_aliases={},
                ratio_options=[],
                ratio_aliases={},
                supports_native_audio=True,
                native_audio_default_enabled=True,
                native_audio_param_name="generate_audio",
                amplification_ratio=1.0,
            )

        def get_current_provider_config(self):
            return self._config

        def get_system_duration_capability(self):
            return {"min_duration": 5, "max_duration": 10}

    tool.video_service = _StubVideoService()
    tool.video_config = _StubVideoConfig()
    tool._fetch_capabilities = lambda: None

    result = asyncio.run(
        tool._generate_with_continuity(
            {
                "scene_number": 2,
                "scene_info_ref": str(scene_path),
                "duration": 10,
                "workflow_state_id": "wf-hydrate",
            }
        )
    )

    exec_params = result["execution_params"]
    assert exec_params["has_reference_image"] is True
    assert exec_params["generation_mode"] == "image_to_video"
    assert exec_params["image_input_url"] == "https://example.com/scene2.png"
    assert (
        tool._determine_generation_mode(
            "https://example.com/opening.png",
            "",
            "",
        )
        == "image_to_video"
    )
    assert (
        tool._determine_generation_mode(
            "https://example.com/continuity.png",
            "",
            "",
            image_from_continuity=True,
        )
        == "image_to_video"
    )


def test_generate_with_continuity_reports_continuity_extract_failure(monkeypatch):
    monkeypatch.setattr(
        vgt_module,
        "get_consistency_policy",
        lambda: ConsistencyPolicy(prompt_safety=PromptSafetyPolicy(enabled=False)),
    )

    class _FailingContinuityTool:
        async def execute(self, tool_input):
            raise RuntimeError("extract failed")

    class _FakeRegistry:
        def get_tool(self, name):
            if name == "scene_continuity_preparation":
                return _FailingContinuityTool()
            raise AssertionError(f"unexpected tool lookup: {name}")

    monkeypatch.setattr(tool_registry_module, "get_tool_registry", lambda: _FakeRegistry())

    tool = _make_video_tool_without_init()

    async def fake_generate_video(self, params, *, execution_liveness_probe=None):
        return {
            "video_url": "https://stub.example/video.mp4",
            "provider": "stub",
            "model": "stub-model",
        }

    tool._generate_video = types.MethodType(fake_generate_video, tool)

    result = asyncio.run(
        tool._generate_with_continuity(
            {
                "prompt": "安全提示词",
                "duration": 5,
                "scene_number": 2,
                "previous_video_url": "https://stub.example/scene1.mp4",
                "emit_last_frame": "never",
            }
        )
    )

    continuity = result["continuity"]
    assert "continuity_extract_failed" in continuity["fallback_reasons"]
    assert continuity["diagnostics"][0]["error_type"] == "RuntimeError"


def test_generate_with_continuity_reports_last_frame_emit_failure(monkeypatch):
    monkeypatch.setattr(
        vgt_module,
        "get_consistency_policy",
        lambda: ConsistencyPolicy(prompt_safety=PromptSafetyPolicy(enabled=False)),
    )

    tool = _make_video_tool_without_init()

    async def fake_generate_video(self, params, *, execution_liveness_probe=None):
        return {
            "video_url": "https://stub.example/video.mp4",
            "provider": "stub",
            "model": "stub-model",
        }

    async def fake_emit_last_frame(self, video_url, scene_no=None):
        raise RuntimeError("final frame tool failed")

    tool._generate_video = types.MethodType(fake_generate_video, tool)
    tool._emit_last_frame = types.MethodType(fake_emit_last_frame, tool)

    result = asyncio.run(
        tool._generate_with_continuity(
            {
                "prompt": "安全提示词",
                "duration": 5,
                "scene_number": 3,
                "emit_last_frame": "always",
            }
        )
    )

    continuity = result["continuity"]
    assert "last_frame_emit_failed" in continuity["fallback_reasons"]
    assert any(
        item.get("fallback_reason") == "last_frame_emit_failed"
        and item.get("error_type") == "RuntimeError"
        for item in continuity["diagnostics"]
    )
