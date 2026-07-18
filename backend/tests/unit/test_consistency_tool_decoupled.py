"""Contract tests for scene-info based consistency asset collection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.agents.tools.consistency_tool import ConsistencyTool


class StubMemoryProvider:
    def __init__(
        self,
        *,
        previous_frame: str | None = None,
        continuity: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        self._previous_frame = previous_frame
        self._continuity = continuity or {}
        self.stored_frames: dict[int, str] = {}

    async def store_scene_final_frame(self, scene_number: int, frame_url: str) -> None:
        self.stored_frames[scene_number] = frame_url

    async def retrieve_previous_frame_url(self, _scene_number: int) -> str | None:
        return self._previous_frame

    async def get_scene_continuity_info(
        self,
        _workflow_state_id: str,
        scene_number: int,
    ) -> dict[str, Any]:
        return self._continuity.get(scene_number, {})


def _write_scene_info(tmp_path: Path, payload: dict[str, Any]) -> str:
    path = tmp_path / "scene-info.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


async def _collect(
    tool: ConsistencyTool,
    *,
    scene_number: int,
    scene_info_ref: str,
    use_cache: bool | None = None,
):
    parameters: dict[str, Any] = {
        "scene_number": scene_number,
        "scene_info_ref": scene_info_ref,
    }
    if use_cache is not None:
        parameters["use_cache"] = use_cache
    return await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": parameters,
            "context": {"workflow_state_id": "test-wf"},
        }
    )


@pytest.mark.asyncio
async def test_consistency_tool_returns_normalized_empty_assets(tmp_path: Path) -> None:
    tool = ConsistencyTool(memory_provider=StubMemoryProvider())

    result = await _collect(
        tool,
        scene_number=1,
        scene_info_ref=_write_scene_info(tmp_path, {}),
    )

    assert result.success
    payload = result.result
    assert payload["workflow_state_id"] == "test-wf"
    assert payload["scene_number"] == 1
    assert payload["assets"]["style"]["global_lock"]["style_guidelines"] == ""
    assert payload["assets"]["characters"]["characters"] == []
    assert payload["assets"]["environment"]["scene_number"] == 1
    assert payload["assets"]["continuity"]["local_continuity"]["enabled"] is False
    assert payload["diagnostics"]["source"] == "scene_info_ref"


@pytest.mark.asyncio
async def test_consistency_tool_collects_style_from_scene_info_ref(tmp_path: Path) -> None:
    concept_plan = {
        "intelligent_style_design": {
            "style_name": "ink light",
            "style_description": "ink and moonlight",
        },
        "consistency_guidelines": {
            "style_consistency": "preserve ink texture",
        },
    }
    tool = ConsistencyTool(memory_provider=StubMemoryProvider())

    result = await _collect(
        tool,
        scene_number=1,
        scene_info_ref=_write_scene_info(tmp_path, {"concept_plan": concept_plan}),
    )

    assert result.success
    style = result.result["assets"]["style"]
    assert style["intelligent_style_design"]["style_name"] == "ink light"
    assert style["global_lock"]["style_guidelines"] == "preserve ink texture"


@pytest.mark.asyncio
async def test_consistency_tool_collects_characters_from_scene_info_ref(
    tmp_path: Path,
) -> None:
    concept_plan = {
        "roles": [{"name": "Painter", "key_traits": ["white hair", "plain robe"]}],
        "scenes": [
            {
                "scene_number": 1,
                "characters_present": ["Painter"],
                "character_descriptions": ["white hair and plain robe"],
            }
        ],
    }
    tool = ConsistencyTool(memory_provider=StubMemoryProvider())

    result = await _collect(
        tool,
        scene_number=1,
        scene_info_ref=_write_scene_info(tmp_path, {"concept_plan": concept_plan}),
    )

    assert result.success
    characters = result.result["assets"]["characters"]
    assert [entry["name"] for entry in characters["characters"]] == ["Painter"]
    assert characters["scene_cast"]["present"] == ["Painter"]


@pytest.mark.asyncio
async def test_consistency_tool_adds_continuity_memory_to_snapshot(
    tmp_path: Path,
) -> None:
    previous_frame = "https://example.com/prev-frame.jpg"
    memory_provider = StubMemoryProvider(
        previous_frame=previous_frame,
        continuity={
            2: {
                "requires_continuity": True,
                "motion_guidance": {"camera_movement": "pan_right"},
            }
        },
    )
    tool = ConsistencyTool(memory_provider=memory_provider)
    scene_info_ref = _write_scene_info(
        tmp_path,
        {"concept_plan": {"scenes": [{"scene_number": 2, "depends_on_scene": 1}]}},
    )

    result = await _collect(tool, scene_number=2, scene_info_ref=scene_info_ref)

    assert result.success
    continuity = result.result["assets"]["continuity"]
    assert continuity["local_continuity"]["previous_frame_url"] == previous_frame
    assert continuity["local_continuity"]["depends_on_scene"] == 1
    assert continuity["motion_guidance"]["camera_movement"] == "pan_right"


@pytest.mark.asyncio
async def test_consistency_tool_registers_final_frame_reference() -> None:
    memory_provider = StubMemoryProvider()
    tool = ConsistencyTool(memory_provider=memory_provider)

    result = await tool.execute(
        {
            "action": "register_reference",
            "parameters": {
                "scene_number": 3,
                "reference_type": "final_frame",
                "reference_value": "https://example.com/scene3-final.jpg",
            },
            "context": {"workflow_state_id": "test-wf"},
        }
    )

    assert result.success
    assert memory_provider.stored_frames == {3: "https://example.com/scene3-final.jpg"}


@pytest.mark.asyncio
async def test_consistency_tool_cache_is_scoped_to_scene_snapshot(tmp_path: Path) -> None:
    tool = ConsistencyTool(memory_provider=StubMemoryProvider())
    scene_info_ref = _write_scene_info(
        tmp_path,
        {"concept_plan": {"intelligent_style_design": {"style_name": "test style"}}},
    )

    first = await _collect(tool, scene_number=1, scene_info_ref=scene_info_ref)
    second = await _collect(
        tool,
        scene_number=1,
        scene_info_ref=scene_info_ref,
        use_cache=True,
    )

    assert first.success and second.success
    assert first.result["assets"] == second.result["assets"]
    assert second.result["diagnostics"]["cached_full"] is True
