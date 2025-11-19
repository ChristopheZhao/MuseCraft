"""Manual voice synthesis check using the VoiceSynthesizerAgent.

Run with:
    uv run python scripts/manual_voice_synthesis.py

Make sure Aliyun TTS credentials are configured in .env beforehand.
"""
import asyncio
from types import SimpleNamespace
from typing import Any

from app.agents.voice_synthesizer import VoiceSynthesizerAgent
from app.agents.tools import register_default_tools
from app.core.workflow_state import workflow_manager, SceneData
from app.models import AgentExecution


class DummySession:
    """Minimal SQLAlchemy session stub for manual runs."""

    def add(self, obj: Any) -> None:
        if isinstance(obj, AgentExecution):
            obj.output_data = obj.output_data or {}
            obj.retry_count = obj.retry_count or 0
            obj.progress_percentage = obj.progress_percentage or 0

    def commit(self) -> None:
        pass

    def refresh(self, obj: Any) -> None:
        setattr(obj, "id", getattr(obj, "id", 1))

    def close(self) -> None:
        pass


async def main() -> None:
    register_default_tools()
    agent = VoiceSynthesizerAgent(llms={})

    workflow_state = workflow_manager.create_workflow(
        user_prompt="Manual voice synthesis check",
        style_preference="tech",
        duration=12,
        aspect_ratio="16:9",
    )
    workflow_state.add_scene(
        SceneData(
            scene_number=1,
            duration=4.0,
            voice_over_text="欢迎使用智能配音服务，这是一次真实接口调用验证。",
        )
    )
    workflow_state.voice_plan = {
        "enabled": True,
        "mode": "narration",
        "scene_guidance": [
            {
                "scene_number": 1,
                "should_narrate": True,
                "objective": "介绍功能",
                "emotion": "友好",
                "key_points": ["智能配音服务", "真实接口验证"],
            }
        ],
    }

    task = SimpleNamespace(
        id=1,
        task_id="manual-voice-test",
        update_progress=lambda *args, **kwargs: None,
    )
    db = DummySession()

    result = await agent.execute(
        task=task,
        input_data={
            "workflow_state_id": workflow_state.task_id,
            "voice_plan": workflow_state.voice_plan,
        },
        db=db,
        execution_order=1,
    )

    print("Voice agent result:", result)
    print("Registered voice assets:", workflow_state.voice_over_assets)


if __name__ == "__main__":
    asyncio.run(main())
