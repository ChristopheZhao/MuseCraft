"""Tests for VoiceSynthesizerAgent orchestration without hitting external providers."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.voice_synthesizer import VoiceSynthesizerAgent
from app.agents.tools import register_default_tools
from app.services.monitoring_service import monitoring_service
from app.core.workflow_state import workflow_manager, SceneData
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

    # Create workflow with a single scene requiring voice-over
    workflow_state = workflow_manager.create_workflow(
        user_prompt="Test prompt",
        style_preference="tech",
        duration=10,
        aspect_ratio="16:9"
    )
    scene_video = tmp_path / "scene1.mp4"
    scene_video.write_bytes(b"FAKE")
    scene = SceneData(scene_number=1, duration=4.0, voice_over_text="测试旁白内容。")
    scene.video_prompt = "女剑客在竹林中练剑"
    scene.video_path = str(scene_video)
    workflow_state.add_scene(scene)
    workflow_state.voice_plan = {
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
    }

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
            "workflow_state_id": workflow_state.task_id,
            "voice_settings": {
                "voice_id": "zhiyu",
                "language": "zh-CN",
                "speed": 1.0,
                "pitch": 1.0,
            },
            "voice_plan": workflow_state.voice_plan,
        },
        db=db,
        execution_order=1,
    )

    assert result.get("success") is True or result.get("subtask_state") in {"complete", "partial"}
    assert workflow_state.voice_over_assets, "Voice assets should be registered"
    asset = workflow_state.voice_over_assets[0]
    assert asset["scene_number"] == 1
    assert asset["local_path"] == str(fake_audio)
    assert workflow_state.scenes[0].voice_over_text == "测试旁白内容。"

    workflow_manager.remove_workflow(workflow_state.task_id)
    # 清理监控服务的异步任务，避免遗留 pending task
    try:
        shutdown_hook = getattr(monitoring_service, "shutdown", None)
        if callable(shutdown_hook):
            await shutdown_hook()
        else:
            monitoring_service.redis_client = None
    except Exception:
        monitoring_service.redis_client = None
