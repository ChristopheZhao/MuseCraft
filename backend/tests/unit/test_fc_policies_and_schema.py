import pytest

from app.agents.base import BaseAgent
from app.agents.tools.base_tool import ToolOutput
from app.agents.tools.tool_registry import get_tool_registry
from app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool
from app.agents.tools.ai_services.video_generation_tool_v2 import VideoGenerationTool
from app.domain import AgentExecutionRequest, AgentType
from app.services.memory_provider import build_memory_services


class _DummyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            tools=["image_generation", "video_generation"],
            memory_services=build_memory_services(),
        )

    async def _execute_impl(self, request: AgentExecutionRequest):
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


@pytest.mark.asyncio
async def test_execute_tool_calls_emits_json_payload_instead_of_tool_runtime_object(monkeypatch):
    agent = _DummyAgent()

    async def _execute_function_call(*_args, **_kwargs):
        return ToolOutput(
            success=True,
            result={"output_path": "/tmp/result.mp4"},
            metadata={"provider": "stub"},
            execution_time=0.1,
        )

    monkeypatch.setattr(agent, "_execute_function_call", _execute_function_call)

    result = await agent.execute_tool_calls(
        [
            {
                "function": {
                    "name": "image_generation.generate_image",
                    "arguments": {"prompt": "test frame"},
                }
            }
        ],
        collect_facts=True,
    )

    assert result["executed_calls"][0]["result"] == {"output_path": "/tmp/result.mp4"}
    assert not isinstance(result["executed_calls"][0]["result"], ToolOutput)


@pytest.mark.asyncio
async def test_execute_tool_calls_turns_non_json_tool_output_into_explicit_failure(monkeypatch):
    agent = _DummyAgent()

    async def _execute_function_call(*_args, **_kwargs):
        return ToolOutput(
            success=True,
            result={"runtime_dependency": object()},
            execution_time=0.1,
        )

    monkeypatch.setattr(agent, "_execute_function_call", _execute_function_call)

    result = await agent.execute_tool_calls(
        [
            {
                "function": {
                    "name": "image_generation.generate_image",
                    "arguments": {"prompt": "test frame"},
                }
            }
        ],
        collect_facts=True,
    )

    call = result["executed_calls"][0]
    assert call["success"] is False
    assert "agent_contract_invalid_json_value" in call["error"]
    assert "runtime_dependency" in call["error"]
