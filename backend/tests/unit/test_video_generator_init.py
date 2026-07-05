from app.agents.base import BaseAgent
from app.agents.video_generator import VideoGeneratorAgent
from app.services.memory_provider import build_memory_services


def _disable_tool_loading(monkeypatch):
    monkeypatch.setattr(
        BaseAgent,
        "_load_tools",
        lambda self, names: setattr(self, "_available_tools", {}),
    )


def test_video_generator_has_video_config(monkeypatch):
    _disable_tool_loading(monkeypatch)
    agent = VideoGeneratorAgent(memory_services=build_memory_services())
    # __init__ 应初始化视频配置（用于提供商能力约束等）
    assert hasattr(agent, "video_config") and agent.video_config is not None


def test_video_generator_builds_react_plan_messages(monkeypatch):
    _disable_tool_loading(monkeypatch)
    agent = VideoGeneratorAgent(memory_services=build_memory_services())
    messages = agent.build_plan_messages(
        {
            "workflow_state_id": "wf-video-init",
            "ready_scenes": [1, 2],
        }
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "wf-video-init" in messages[1]["content"]
    assert "ready_scenes" in messages[1]["content"]
