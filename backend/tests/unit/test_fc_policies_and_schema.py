import pytest

from backend.app.agents.base import BaseAgent
from backend.app.agents.tools.tool_registry import get_tool_registry
from backend.app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool
from backend.app.agents.tools.ai_services.video_generation_tool_v2 import VideoGenerationTool
from backend.app.models import AgentType
from backend.app.services.memory_provider import build_memory_services


class _DummyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            tools=["image_generation", "video_generation"],
            memory_services=build_memory_services(),
        )

    async def _execute_impl(self, task, input_data, execution, db):  # type: ignore
        return {}


@pytest.mark.asyncio
async def test_fc_schema_uses_policies_and_tool_defaults(monkeypatch):
    # 确保工具注册
    reg = get_tool_registry()
    reg.register_tool(ImageGenerationTool, name="image_generation", auto_load=False)
    reg.register_tool(VideoGenerationTool, name="video_generation", auto_load=False)
    reg._tool_instances["image_generation"] = ImageGenerationTool()  # type: ignore[attr-defined]
    reg._tool_instances["video_generation"] = VideoGenerationTool()  # type: ignore[attr-defined]

    agent = _DummyAgent()
    schema = agent._build_function_call_schema()

    names = [f["function"]["name"] for f in schema]

    # image_generation 工具默认仅暴露 execution-only generate_image
    assert "image_generation.generate_image" in names
    assert "image_generation.gen_image_prompt" not in names
    assert "image_generation.generate_with_autoprompt" not in names

    # video_generation 工具默认仅暴露连续性生成动作
    assert "video_generation.generate_with_continuity" in names
    # 不应包含非声明动作
    assert "video_generation.get_capabilities" not in names
    assert "video_generation.generate_video" not in names
