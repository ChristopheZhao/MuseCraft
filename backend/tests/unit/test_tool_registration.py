"""Default tool registration contract tests."""

import pytest

from app.agents.tools import register_default_tools
from app.agents.tools.agent_tool_allocation import AgentToolAllocator
from app.agents.tools.base_tool import ToolError
from app.agents.tools.tool_registry import get_tool_registry
from app.domain import AgentType


def test_default_tool_registration_exposes_core_capabilities() -> None:
    register_default_tools()
    registry = get_tool_registry()

    expected = {
        "consistency_tool",
        "image_generation_client",
        "openai_client",
        "zhipu_client",
    }

    assert {name: registry.get_tool(name).metadata.name for name in expected} == {
        name: name for name in expected
    }


def test_video_generator_has_no_keyword_scene_analysis_dependency() -> None:
    tools = AgentToolAllocator().get_tools_for_agent(AgentType.VIDEO_GENERATOR)

    assert "scene_analysis" not in tools


def test_default_registration_does_not_expose_unused_parameter_optimizer() -> None:
    register_default_tools()

    with pytest.raises(ToolError, match="Tool not registered: parameter_optimization"):
        get_tool_registry().get_tool("parameter_optimization")


@pytest.mark.parametrize(
    "tool_name",
    ["scene_analysis", "intelligent_scene_planning"],
)
def test_default_registration_does_not_expose_semantic_heuristic_tools(tool_name) -> None:
    register_default_tools()

    with pytest.raises(ToolError, match=f"Tool not registered: {tool_name}"):
        get_tool_registry().get_tool(tool_name)
