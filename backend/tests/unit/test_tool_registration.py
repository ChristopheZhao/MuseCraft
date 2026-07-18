"""Default tool registration contract tests."""

from app.agents.tools import register_default_tools
from app.agents.tools.tool_registry import get_tool_registry


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
