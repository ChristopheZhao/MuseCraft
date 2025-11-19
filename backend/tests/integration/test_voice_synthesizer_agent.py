"""Tests for VoiceSynthesizerAgent orchestration without hitting external providers."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.voice_synthesizer import VoiceSynthesizerAgent
from app.agents.tools import register_default_tools
from app.services.monitoring_service import monitoring_service
from app.agents.services.mas_shared_memory import get_shared_wm
from app.services.memory_provider import build_memory_services, set_memory_services
from app.agents.memory.short_term.working_memory import SceneSnapshot
from app.models import AgentExecution


class DummySession:
    def __init__(self):
        self._objects = []

    def add(self, obj):
        self._objects.append(obj)
        if isinstance(obj, AgentExecution):
            obj.output_data = obj.output_data or {}
            obj.retry_count = obj.retry_count or 0
            obj.progress_percentage = obj.progress_percentage or 0

    def commit(self):
        pass

    def refresh(self, obj):
        # Ensure execution objects have an ID for downstream formatting
        setattr(obj, "id", getattr(obj, "id", 1))


@pytest.mark.asyncio
async def test_voice_synthesizer_agent_generates_voice_assets(tmp_path: Path, monkeypatch):
    register_default_tools()
    agent = VoiceSynthesizerAgent(llms={})
    monitoring_service.redis_client = None

    # 使用 Shared WM 构造一个需要旁白的场景
    wf_id = "wf-voice-synth-test"
    shared = get_shared_wm()
    memory_services = build_memory_services()
    set_memory_services(memory_services)
    store = memory_services.fact_store
    snap = SceneSnapshot(scene_number=1, duration=4.0, narrative_description="测试旁白内容。")
    shared.upsert_scene(wf_id, snap)
    store.put(wf_id, "project.voice_plan", {
        "enabled": True,
        "mode": "narration",
        "persona": "温柔的旁白者",
        "tone_keywords": ["温暖", "平静"],
        "scene_guidance": [
            {
                "scene_number": 1,
                "should_narrate": True,
                "objective": "介绍场景",
                "emotion": "宁静",
                "key_points": ["欢迎来到智能世界"],
                "pace_tag": "medium",
                "target_char_count": len("测试旁白内容。"),
            }
        ],
    })

    fake_audio = tmp_path / "voice.wav"
    fake_audio.write_bytes(b"RIFF....fake pcm data....")

    async def fake_use_tool(name: str, action: str, params):
        if name == "voice_synth_tool":
            return {
                "audio_path": str(fake_audio),
                "duration": 3.2,
                "voice_id": params.get("voice_id"),
                "provider": "aliyun",
                "metadata": {"scene_number": params.get("metadata", {}).get("scene_number")},
            }
        if name == "file_storage_tool":
            return {
                "local_path": str(fake_audio),
                "url": "https://example.com/voice.wav",
            }
        if name == "audio_processor":
            if action == "ensure_duration":
                return {
                    "output_path": str(fake_audio),
                    "final_duration": params.get("target_duration", 3.2),
                    "original_duration": 3.2,
                    "adjusted": False,
                    "target_duration": params.get("target_duration", 3.2),
                }
            return {"output_path": str(fake_audio)}
        if name == "audio_analysis_tool":
            return {"peaks": []}
        raise AssertionError(f"Unexpected tool call: {name}.{action}")

    monkeypatch.setattr(agent, "use_tool", fake_use_tool)

    task = SimpleNamespace(id=1, task_id="task-voice-1", update_progress=lambda *args, **kwargs: None)
    db = DummySession()

    result = await agent.execute(
        task=task,
        input_data={
            "workflow_state_id": wf_id,
            "voice_settings": {
                "voice_id": "zhiyu",
                "language": "zh-CN",
                "speed": 1.0,
                "pitch": 1.0,
            },
            # Voice plan 也可从 Shared WM 读取，这里冗余传入以覆盖
            "voice_plan": store.get(wf_id, "project.voice_plan", default={}),
        },
        db=db,
        execution_order=1,
    )

    assert result.get("success") is True or result.get("subtask_state") in {"complete", "partial"}
    assets = store.get(wf_id, "project.voice_assets", default={}) or {}
    assert 1 in assets, "Voice assets should be registered in Shared WM"
    asset = assets[1]
    assert asset.get("audio_path") == str(fake_audio)
    # 清理监控服务的异步任务，避免遗留 pending task
    try:
        shutdown_hook = getattr(monitoring_service, "shutdown", None)
        if callable(shutdown_hook):
            await shutdown_hook()
        else:
            monitoring_service.redis_client = None
    except Exception:
        monitoring_service.redis_client = None
