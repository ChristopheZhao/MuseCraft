import asyncio
import pytest

from backend.app.agents.base import BaseAgent
from backend.app.agents.tools.tool_registry import get_tool_registry
from backend.app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool
from backend.app.agents.tools.ai_services.video_generation_tool_v2 import VideoGenerationTool


class _DummyAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_type=None, agent_name="dummy_agent", tools=["image_generation", "video_generation"])  # type: ignore

    async def _execute_impl(self, task, input_data, execution, db):  # type: ignore
        return {}


@pytest.mark.asyncio
async def test_fc_schema_uses_policies_and_tool_defaults(monkeypatch):
    # 确保工具注册
    reg = get_tool_registry()
    reg.register_tool(ImageGenerationTool, name="image_generation")
    reg.register_tool(VideoGenerationTool, name="video_generation")

    agent = _DummyAgent()
    schema = agent._build_function_call_schema()

    names = [f["function"]["name"] for f in schema]

    # image_generation 工具默认仅暴露 execution-only generate_image
    assert any(n.startswith("image_generation_generate_image") for n in names)
    assert not any(n.startswith("image_generation_gen_image_prompt") for n in names)
    assert not any(n.startswith("image_generation_generate_with_autoprompt") for n in names)

    # video_generation 工具默认仅暴露 generate_video
    assert any(n.startswith("video_generation_generate_video") for n in names)
    # 不应包含非声明动作
    assert not any(n.startswith("video_generation_get_capabilities") for n in names)
