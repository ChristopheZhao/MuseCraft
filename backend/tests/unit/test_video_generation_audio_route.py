from types import SimpleNamespace

from app.agents.tools.ai_services.video_generation_tool_v2 import VideoGenerationTool


def _build_tool(
    *,
    supports_native_audio: bool,
    native_audio_default_enabled=None,
) -> VideoGenerationTool:
    tool = object.__new__(VideoGenerationTool)
    tool.video_config = SimpleNamespace(
        get_current_provider_config=lambda: SimpleNamespace(
            provider_name="doubao",
            supports_native_audio=supports_native_audio,
            native_audio_default_enabled=native_audio_default_enabled,
        )
    )
    return tool


def test_native_audio_request_uses_explicit_param():
    tool = _build_tool(supports_native_audio=True)
    resolved = tool._resolve_native_audio_request({"generate_audio": True})
    assert resolved["decision_source"] == "explicit_param"
    assert resolved["strategy"] == "explicit"
    assert resolved["generate_audio"] is True


def test_native_audio_request_explicit_is_bounded_by_provider_capability():
    tool = _build_tool(supports_native_audio=False)
    resolved = tool._resolve_native_audio_request({"generate_audio": True})
    assert resolved["decision_source"] == "explicit_param"
    assert resolved["generate_audio"] is False
    assert resolved["supports_native_audio"] is False


def test_native_audio_request_uses_provider_default_when_explicit_missing():
    tool = _build_tool(supports_native_audio=True, native_audio_default_enabled=True)
    resolved = tool._resolve_native_audio_request({})
    assert resolved["decision_source"] == "provider_default"
    assert resolved["strategy"] == "provider_default"
    assert resolved["generate_audio"] is True


def test_native_audio_request_disables_when_no_explicit_or_provider_default():
    tool = _build_tool(supports_native_audio=True, native_audio_default_enabled=None)
    resolved = tool._resolve_native_audio_request({})
    assert resolved["decision_source"] == "implicit_disabled"
    assert resolved["strategy"] == "implicit_disabled"
    assert resolved["generate_audio"] is False
