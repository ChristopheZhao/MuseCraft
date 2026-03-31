import json

import pytest

from app.agents.tools.base_tool import ToolInput
from app.agents.tools.consistency_tool import ConsistencyTool


class _BoundaryMemoryProvider:
    def __init__(self):
        self.store_calls = []

    async def retrieve_scene_references(self, workflow_state_id: str, scene_number: int, agent_name: str):
        return {}

    async def retrieve_motion_guidance(self, workflow_state_id: str, scene_number: int, agent_name: str):
        return {}

    async def store_scene_final_frame(self, scene_number: int, frame_url: str) -> None:
        self.store_calls.append((scene_number, frame_url))

    async def retrieve_previous_frame_url(self, scene_number: int):
        return None

    async def get_scene_continuity_info(self, workflow_state_id: str, scene_number: int):
        return {}


def _write_scene_info(tmp_path):
    payload = {
        "concept_plan": {
            "consistency_guidelines": {
                "style_consistency": "非写实仙侠动态水墨",
                "character_consistency": "韩立保持既定造型",
            },
            "intelligent_style_design": {
                "style_name": "仙侠动态水墨",
                "style_tags": ["非写实", "水墨"],
            },
        },
        "scenes_to_generate": [
            {
                "scene_number": 2,
                "visual_description": "韩立在秘境静室中起身反击",
                "opening_state": "韩立半跪稳住身形",
                "characters_present": ["韩立"],
            }
        ],
    }
    scene_path = tmp_path / "scene_info_boundary.json"
    scene_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return scene_path


@pytest.mark.asyncio
async def test_consistency_tool_get_prompt_assets_is_read_only(tmp_path):
    scene_path = _write_scene_info(tmp_path)
    memory_provider = _BoundaryMemoryProvider()
    tool = ConsistencyTool(memory_provider=memory_provider)

    result = await tool.execute(
        ToolInput(
            action="get_prompt_assets",
            parameters={"scene_number": 2, "scene_info_ref": str(scene_path)},
            context={"workflow_state_id": "wf-consistency-boundary"},
        )
    )

    assert result.success is True
    assert memory_provider.store_calls == []


@pytest.mark.asyncio
async def test_consistency_tool_register_reference_is_explicit_write_path(tmp_path):
    scene_path = _write_scene_info(tmp_path)
    memory_provider = _BoundaryMemoryProvider()
    tool = ConsistencyTool(memory_provider=memory_provider)

    await tool.execute(
        ToolInput(
            action="get_prompt_assets",
            parameters={"scene_number": 2, "scene_info_ref": str(scene_path)},
            context={"workflow_state_id": "wf-consistency-boundary"},
        )
    )
    result = await tool.execute(
        ToolInput(
            action="register_reference",
            parameters={
                "scene_number": 2,
                "reference_type": "final_frame",
                "reference_value": "https://example.com/scene-2-final.jpg",
            },
            context={"workflow_state_id": "wf-consistency-boundary"},
        )
    )

    assert result.success is True
    assert result.result == {"stored": True, "scene_number": 2}
    assert memory_provider.store_calls == [(2, "https://example.com/scene-2-final.jpg")]

