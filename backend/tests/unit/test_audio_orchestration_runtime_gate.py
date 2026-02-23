import pytest
from types import SimpleNamespace

from app.agents import orchestrator as orchestrator_module
from app.agents.orchestrator import OrchestratorAgent
from app.agents.tools.video_composition import composition_tool as composition_module
from app.agents.tools.video_composition.composition_tool import CompositionTool
from app.core.config import settings


class _FakeWM:
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class _StubFFmpegTool:
    def __init__(self, payload_by_path):
        self.payload_by_path = payload_by_path

    async def execute(self, tool_input):
        file_path = tool_input.parameters.get("file_path")
        payload = self.payload_by_path.get(file_path)
        if isinstance(payload, Exception):
            raise payload
        return payload


def _build_video_wm(total_scenes, scene_records):
    return _FakeWM(
        {
            "scene_overview": {
                "scenes": [{"scene_number": i + 1} for i in range(total_scenes)],
            },
            "scene_outputs.video": scene_records,
        }
    )


def test_orchestrator_skips_audio_agent_only_when_all_scene_videos_have_audio(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())

    monkeypatch.setattr(settings, "VIDEO_AUDIO_STRATEGY", "adaptive", raising=False)
    wm = _build_video_wm(
        total_scenes=2,
        scene_records={
            1: {"scene_number": 1, "video_path": "/tmp/s1.mp4"},
            2: {"scene_number": 2, "video_path": "/tmp/s2.mp4"},
        },
    )
    monkeypatch.setattr(orchestrator_module, "get_mas_working_memory", lambda workflow_id, service=None: wm)
    monkeypatch.setattr(orchestrator_module.os.path, "exists", lambda _: True)
    agent._probe_video_audio_stream = lambda _: True

    facts = agent._collect_runtime_video_audio_facts("wf-1")
    assert facts["all_have_audio"] is True
    assert agent._should_run_audio_generator("wf-1") is False


def test_orchestrator_runs_audio_agent_when_runtime_audio_is_unknown(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())

    monkeypatch.setattr(settings, "VIDEO_AUDIO_STRATEGY", "adaptive", raising=False)
    wm = _build_video_wm(
        total_scenes=2,
        scene_records={
            1: {"scene_number": 1, "video_path": "/tmp/s1.mp4"},
            2: {"scene_number": 2, "video_url": "https://example.com/s2.mp4"},
        },
    )
    monkeypatch.setattr(orchestrator_module, "get_mas_working_memory", lambda workflow_id, service=None: wm)
    monkeypatch.setattr(orchestrator_module.os.path, "exists", lambda _: True)
    agent._probe_video_audio_stream = lambda _: True

    facts = agent._collect_runtime_video_audio_facts("wf-2")
    assert facts["all_have_audio"] is False
    assert facts["unknown"] >= 1
    assert agent._should_run_audio_generator("wf-2") is True


def test_orchestrator_runs_audio_agent_when_any_scene_video_is_silent(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())

    monkeypatch.setattr(settings, "VIDEO_AUDIO_STRATEGY", "provider_only", raising=False)
    wm = _build_video_wm(
        total_scenes=2,
        scene_records={
            1: {"scene_number": 1, "video_path": "/tmp/s1.mp4"},
            2: {"scene_number": 2, "video_path": "/tmp/s2.mp4"},
        },
    )
    monkeypatch.setattr(orchestrator_module, "get_mas_working_memory", lambda workflow_id, service=None: wm)
    monkeypatch.setattr(orchestrator_module.os.path, "exists", lambda _: True)
    agent._probe_video_audio_stream = lambda path: path.endswith("s1.mp4")

    facts = agent._collect_runtime_video_audio_facts("wf-3")
    assert facts["without_audio"] == 1
    assert agent._should_run_audio_generator("wf-3") is True


def test_orchestrator_mas_only_keeps_audio_agent_enabled(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())

    monkeypatch.setattr(settings, "VIDEO_AUDIO_STRATEGY", "mas_only", raising=False)
    wm = _build_video_wm(
        total_scenes=1,
        scene_records={1: {"scene_number": 1, "video_path": "/tmp/s1.mp4"}},
    )
    monkeypatch.setattr(orchestrator_module, "get_mas_working_memory", lambda workflow_id, service=None: wm)
    monkeypatch.setattr(orchestrator_module.os.path, "exists", lambda _: True)
    agent._probe_video_audio_stream = lambda _: True

    assert agent._should_run_audio_generator("wf-4") is True


@pytest.mark.asyncio
async def test_composition_probe_clip_has_audio_detects_audio_stream(monkeypatch):
    tool = object.__new__(CompositionTool)
    monkeypatch.setattr(composition_module.os.path, "exists", lambda _: True)

    ffmpeg = _StubFFmpegTool(
        {"/tmp/clip.mp4": {"audio_codec": "aac", "sample_rate": 48000, "channels": 2}}
    )
    result = await tool._probe_clip_has_audio(ffmpeg, "/tmp/clip.mp4")
    assert result is True


@pytest.mark.asyncio
async def test_composition_probe_clip_has_audio_returns_none_when_probe_fails(monkeypatch):
    tool = object.__new__(CompositionTool)
    monkeypatch.setattr(composition_module.os.path, "exists", lambda _: True)

    ffmpeg = _StubFFmpegTool({"/tmp/clip.mp4": RuntimeError("probe failed")})
    result = await tool._probe_clip_has_audio(ffmpeg, "/tmp/clip.mp4")
    assert result is None


@pytest.mark.asyncio
async def test_composition_preserve_audio_requires_all_clips_with_audio_in_adaptive(monkeypatch):
    tool = object.__new__(CompositionTool)
    monkeypatch.setattr(settings, "VIDEO_AUDIO_STRATEGY", "adaptive", raising=False)
    monkeypatch.setattr(settings, "COMPOSER_PRESERVE_SOURCE_AUDIO_DEFAULT", False, raising=False)

    async def _probe_all_audio(_ffmpeg_tool, _clip_path):
        return {"has_audio": True, "audio_codec": "aac", "sample_rate": 48000, "channels": 2}

    monkeypatch.setattr(tool, "_probe_clip_audio_profile", _probe_all_audio)
    preserve = await tool._resolve_preserve_source_audio(
        {},
        clips=["/tmp/s1.mp4", "/tmp/s2.mp4"],
        ffmpeg_tool=object(),
    )
    assert preserve is True

    async def _probe_partial(_ffmpeg_tool, clip_path):
        if clip_path.endswith("s1.mp4"):
            return {"has_audio": True, "audio_codec": "aac", "sample_rate": 48000, "channels": 2}
        return None

    monkeypatch.setattr(tool, "_probe_clip_audio_profile", _probe_partial)
    preserve_unknown = await tool._resolve_preserve_source_audio(
        {},
        clips=["/tmp/s1.mp4", "/tmp/s2.mp4"],
        ffmpeg_tool=object(),
    )
    assert preserve_unknown is False

    async def _probe_incompatible(_ffmpeg_tool, clip_path):
        if clip_path.endswith("s1.mp4"):
            return {"has_audio": True, "audio_codec": "aac", "sample_rate": 48000, "channels": 2}
        return {"has_audio": True, "audio_codec": "aac", "sample_rate": 44100, "channels": 2}

    monkeypatch.setattr(tool, "_probe_clip_audio_profile", _probe_incompatible)
    preserve_incompatible = await tool._resolve_preserve_source_audio(
        {},
        clips=["/tmp/s1.mp4", "/tmp/s2.mp4"],
        ffmpeg_tool=object(),
    )
    assert preserve_incompatible is False


@pytest.mark.asyncio
async def test_composition_explicit_and_mas_only_policy(monkeypatch):
    tool = object.__new__(CompositionTool)
    monkeypatch.setattr(settings, "VIDEO_AUDIO_STRATEGY", "mas_only", raising=False)

    preserve_explicit = await tool._resolve_preserve_source_audio(
        {"preserve_audio": True},
        clips=[],
        ffmpeg_tool=object(),
    )
    assert preserve_explicit is True

    async def _probe_all_audio(_ffmpeg_tool, _clip_path):
        return {"has_audio": True, "audio_codec": "aac", "sample_rate": 48000, "channels": 2}

    monkeypatch.setattr(tool, "_probe_clip_audio_profile", _probe_all_audio)
    preserve_mas_only = await tool._resolve_preserve_source_audio(
        {},
        clips=["/tmp/s1.mp4"],
        ffmpeg_tool=object(),
    )
    assert preserve_mas_only is False
