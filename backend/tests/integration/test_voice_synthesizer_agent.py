"""Tests for VoiceSynthesizerAgent orchestration without hitting external providers."""
from types import SimpleNamespace

import pytest

from app.agents.voice_synthesizer import VoiceSynthesizerAgent
from app.agents.tools import register_default_tools
from app.services.monitoring_service import monitoring_service
from app.agents.memory.short_term import get_working_memory_service
from app.agents.memory.short_term import SceneSnapshot
from app.agents.utils.memory_helpers import agent_scope
from app.agents.adapters.video.memory_adapter import VideoMemoryAdapter


class DummySession:
    def __init__(self):
        self._objects = []

    def add(self, obj):
        self._objects.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        # Ensure execution objects have an ID for downstream formatting
        setattr(obj, "id", getattr(obj, "id", 1))


@pytest.mark.asyncio
async def test_voice_synthesizer_agent_generates_voice_assets():
    register_default_tools()
    agent = VoiceSynthesizerAgent()
    monitoring_service.redis_client = None

    # 使用 Shared WM 构造一个需要旁白的场景
    wf_id = "wf-voice-synth-test"
    wm_service = get_working_memory_service()
    mas_wm = wm_service.create_or_get(wf_id, f"mas:{wf_id}")
    wm_service.create_or_get(wf_id, agent_scope(wf_id, agent.agent_name), shared_view=mas_wm)
    agent_wm = wm_service.get(wf_id, agent_scope(wf_id, agent.agent_name))
    print(f"[TEST] MAS WM keys after init: {mas_wm.list_keys()}")
    video_adapter = VideoMemoryAdapter(mas_wm)
    snap = SceneSnapshot(scene_number=1, duration=4.0, narrative_description="测试旁白内容。")
    video_adapter.upsert_scene(snap)
    mas_wm.put("project.voice_plan", {
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
    agent_wm.put("facts", {
        "voice_scene_facts": [
            {
                "scene_number": 1,
                "should_narrate": True,
                "has_voice_asset": False,
                "fact_status": "pending",
                "target_duration": 4.0,
                "existing_text": "测试旁白内容。",
                "voice_guidance": {},
            }
        ]
    })

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
            "voice_plan": mas_wm.get("project.voice_plan", {}),
        },
        db=db,
        execution_order=1,
    )



    assert result.get("success") is True or result.get("subtask_state") in {"complete", "partial"}
    assets = mas_wm.get("voice_assets", {}) or {}
    print(f"[TEST] MAS WM voice_assets keys: {list(assets.keys())}")
    assert 1 in assets, "Voice assets should be registered in MAS WM"
    # 清理监控服务的异步任务，避免遗留 pending task
    try:
        shutdown_hook = getattr(monitoring_service, "shutdown", None)
        if callable(shutdown_hook):
            await shutdown_hook()
        else:
            monitoring_service.redis_client = None
    except Exception:
        monitoring_service.redis_client = None
