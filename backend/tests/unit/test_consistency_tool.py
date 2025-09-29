"""Unit tests for the ConsistencyTool."""

import pytest

from app.agents.tools import register_default_tools
from app.agents.tools.consistency_tool import ConsistencyTool
from app.core.workflow_state import workflow_manager, SceneData
from app.core.scene_continuity_memory import get_scene_continuity_memory


@pytest.mark.asyncio
async def test_consistency_tool_collects_assets():
    register_default_tools()
    tool = ConsistencyTool()

    workflow_state = workflow_manager.create_workflow(
        user_prompt="测试一致性工具",
        style_preference="ink",
        duration=30,
        aspect_ratio="16:9",
    )

    workflow_state.intelligent_style_design = {
        "style_name": "水墨光影诗",
        "style_description": "墨色留白与光影交织",
        "visual_approach": "动画",
    }
    workflow_state.consistency_hints = {"visual": "保持柔和光影过渡"}
    workflow_state.concept_plan = {
        "consistency_guidelines": {
            "character_consistency": "画魂师保持白发与素色长袍",
            "environment_consistency": "画室保持月光与墨色对比",
        },
        "roles": [
            {
                "name": "画魂师",
                "display_name": "画魂师",
                "key_traits": ["白发", "素色长袍"],
                "prompt_snippet": "保持白发与素色长袍的东方画师形象",
            }
        ],
    }

    scene = SceneData(
        scene_number=1,
        title="寂静画室",
        visual_description="月光洒在空白画卷上",
        narrative_description="老画师准备赋予画卷生命",
        characters_present=["画魂师"],
        character_descriptions=["白发苍苍，素色长袍"],
        props_and_objects=["画卷", "毛笔"],
        color_palette=["墨黑", "月白"],
    )
    workflow_state.add_scene(scene)

    memory = get_scene_continuity_memory()
    await memory.clear_all()
    await memory.store_scene_final_frame(1, "https://example.com/scene_1_tail.jpg")

    first = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
                "workflow_state_id": workflow_state.task_id,
                "asset_categories": ["style"],
            },
        }
    )

    assert first.success
    style_assets = first.result["assets"].get("style")
    assert style_assets
    assert style_assets.get("intelligent_style_design", {}).get("style_name") == "水墨光影诗"
    assert "characters" not in first.result["assets"]

    second = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
                "workflow_state_id": workflow_state.task_id,
                "asset_categories": ["characters"],
            },
        }
    )

    assert second.success
    characters_assets = second.result["assets"].get("characters")
    assert characters_assets
    character_bundle = characters_assets["characters"]
    assert any(entry.get("name") == "画魂师" for entry in character_bundle)

    third = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
                "workflow_state_id": workflow_state.task_id,
            },
        }
    )

    assert third.success
    merged_assets = third.result["assets"]
    assert {"style", "characters"}.issubset(set(merged_assets.keys()))
    continuity = merged_assets.get("continuity")
    assert continuity is not None
    diag = third.result["diagnostics"]
    assert diag.get("cached_full") is True
    assert set(diag.get("cached_categories", [])) >= {"style", "characters", "continuity"}

    cache_key = (workflow_state.task_id, 1)
    assert cache_key in tool._asset_cache

    # 注册新的连续性参考应使缓存失效
    await tool.execute(
        {
            "action": "register_reference",
            "parameters": {
                "scene_number": 1,
                "workflow_state_id": workflow_state.task_id,
                "reference_type": "final_frame",
                "reference_value": "https://example.com/scene_1_tail_v2.jpg",
            },
        }
    )

    assert cache_key not in tool._asset_cache

    await memory.clear_all()
    workflow_manager.remove_workflow(workflow_state.task_id)
