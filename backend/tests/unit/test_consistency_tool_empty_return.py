"""Fail-closed tests for the ConsistencyTool scene-info boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.tools.consistency_tool import ConsistencyTool


class EmptyMemoryProvider:
    async def store_scene_final_frame(self, _scene_number: int, _frame_url: str) -> None:
        return None

    async def retrieve_previous_frame_url(self, _scene_number: int) -> None:
        return None

    async def get_scene_continuity_info(
        self,
        _workflow_state_id: str,
        _scene_number: int,
    ) -> dict:
        return {}


@pytest.mark.asyncio
async def test_consistency_tool_rejects_missing_scene_info_ref() -> None:
    tool = ConsistencyTool(memory_provider=EmptyMemoryProvider())

    result = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {"scene_number": 1},
            "context": {"workflow_state_id": "wf-test-missing"},
        }
    )

    assert result.success is False
    assert "scene_info_ref is required" in str(result.error)


@pytest.mark.asyncio
async def test_consistency_tool_rejects_unknown_scene_info_ref(tmp_path: Path) -> None:
    tool = ConsistencyTool(memory_provider=EmptyMemoryProvider())

    result = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
                "scene_info_ref": str(tmp_path / "missing.json"),
            },
            "context": {"workflow_state_id": "wf-test-missing-file"},
        }
    )

    assert result.success is False
    assert "scene_info_ref not found" in str(result.error)


@pytest.mark.asyncio
async def test_consistency_tool_reads_valid_scene_info_snapshot(tmp_path: Path) -> None:
    scene_info_ref = tmp_path / "scene-info.json"
    scene_info_ref.write_text(
        json.dumps(
            {
                "concept_plan": {
                    "intelligent_style_design": {"style_name": "documentary"},
                    "roles": [{"name": "Host"}],
                    "scenes": [{"scene_number": 1, "characters_present": ["Host"]}],
                }
            }
        ),
        encoding="utf-8",
    )
    tool = ConsistencyTool(memory_provider=EmptyMemoryProvider())

    result = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
                "scene_info_ref": str(scene_info_ref),
            },
            "context": {"workflow_state_id": "wf-test-valid"},
        }
    )

    assert result.success
    assert result.result["assets"]["style"]["intelligent_style_design"]["style_name"] == (
        "documentary"
    )
    assert result.result["assets"]["characters"]["scene_cast"]["present"] == ["Host"]
