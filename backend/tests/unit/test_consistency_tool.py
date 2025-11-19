"""Unit tests for the ConsistencyTool."""

import pytest

from app.agents.tools import register_default_tools
from app.agents.tools.consistency_tool import ConsistencyTool
from app.agents.services.mas_shared_memory import get_shared_wm
from app.services.memory_provider import build_memory_services, set_memory_services
from app.agents.memory.short_term.working_memory import SceneSnapshot
from app.core.scene_continuity_memory import get_scene_continuity_memory


@pytest.mark.asyncio
async def test_consistency_tool_collects_assets():
    register_default_tools()
    tool = ConsistencyTool()

    wf_id = "wf-consistency-tool"
    shared = get_shared_wm()
    memory_services = build_memory_services()
    set_memory_services(memory_services)
    store = memory_services.fact_store
    # 写入概念计划（含风格）到 Shared WM facts
    concept_plan = {
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
        "intelligent_style_design": {
            "style_name": "水墨光影诗",
            "style_description": "墨色留白与光影交织",
            "visual_approach": "动画",
        },
        "scenes": [
            {
                "scene_number": 1,
                "characters_present": ["画魂师"],
                "character_descriptions": ["白发苍苍，素色长袍"],
            }
        ],
    }
    store.put(wf_id, "project.concept_plan", concept_plan)
    # 写入场景快照
    scene = SceneSnapshot(
        scene_number=1,
        duration=5.0,
        visual_description="月光洒在空白画卷上",
        narrative_description="老画师准备赋予画卷生命",
        image_url="",
        motion_beats=[],
    )
    # 扩展：在 scene_scripts facts 中写入角色提示
    shared.upsert_scene(wf_id, scene)
    scripts = {
        "1": {
            "characters_present": ["画魂师"],
            "character_descriptions": ["白发苍苍，素色长袍"],
        }
    }
    store.put(wf_id, "project.scene_scripts", scripts)

    memory = get_scene_continuity_memory()
    await memory.clear_all()
    await memory.store_scene_final_frame(1, "https://example.com/scene_1_tail.jpg")

    context = {"workflow_state_id": wf_id}

    first = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
            },
            "context": context,
        }
    )

    assert first.success
    assets_first = first.result["assets"]
    style_assets = assets_first.get("style")
    assert style_assets and style_assets.get("intelligent_style_design", {}).get("style_name") == "水墨光影诗"
    characters_assets = assets_first.get("characters")
    assert characters_assets and characters_assets.get("characters")
    assert any(entry.get("name") == "画魂师" for entry in characters_assets["characters"])
    assert "environment" in assets_first
    assert "continuity" in assets_first

    second = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
            },
            "context": context,
        }
    )

    assert second.success
    merged_assets = second.result["assets"]
    assert {"style", "characters", "environment", "continuity"}.issubset(set(merged_assets.keys()))
    continuity = merged_assets.get("continuity")
    assert continuity is not None
    diag = second.result["diagnostics"]
    assert diag.get("cached_full") is True
    assert set(diag.get("cached_categories", [])) >= {"style", "characters", "environment", "continuity"}

    cache_key = (wf_id, 1)
    assert cache_key in tool._asset_cache

    # 注册新的连续性参考应使缓存失效
    await tool.execute(
        {
            "action": "register_reference",
            "parameters": {
                "scene_number": 1,
                "reference_type": "final_frame",
                "reference_value": "https://example.com/scene_1_tail_v2.jpg",
            },
            "context": context,
        }
    )

    assert cache_key not in tool._asset_cache

    await memory.clear_all()


@pytest.mark.asyncio
async def test_consistency_tool_empty_assets_without_concept_plan():
    register_default_tools()
    tool = ConsistencyTool()

    wf_id = "wf-consistency-empty"
    shared = get_shared_wm()
    memory = get_scene_continuity_memory()
    await memory.clear_all()

    shared.upsert_scene(
        wf_id,
        SceneSnapshot(
            scene_number=1,
            duration=10.0,
            visual_description="夜晚的古井",
            narrative_description="缺少概念计划",
            image_url="",
            motion_beats=[],
        ),
    )
    # 不写入 concept_plan / roles，让工具无法收集资产

    result = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
            },
            "context": {"workflow_state_id": wf_id},
        }
    )

    assert result.success
    payload = result.result or {}
    assert payload.get("scene_number") == 1
    assets = payload.get("assets") or {}
    assert assets.get("style") == {}
    assert assets.get("characters", {}).get("characters") == []
    environment = assets.get("environment", {})
    assert environment.get("visual_description") == "夜晚的古井"
    continuity = assets.get("continuity") or {}
    assert continuity.get("requires_continuity") is False
    assert continuity.get("previous_frame_available") is False
    assert (continuity.get("from_scene") is None) or (continuity.get("from_scene") == "")
    motion_guidance = continuity.get("motion_guidance") or {}
    assert motion_guidance.get("has_guidance") is False
