"""Test ConsistencyTool with dependency injection (decoupled from global services).

验证工具与记忆服务解耦后的独立测试能力。
"""

import pytest
from typing import Any, Dict, Optional


# ===== Stub Providers =====


class StubFactsProvider:
    """测试用的事实提供者 - 返回预设数据。"""

    def __init__(
        self,
        facts: Optional[Dict[str, Any]] = None,
        scenes: Optional[Dict[int, Any]] = None,
        continuity: Optional[Dict[int, Dict[str, Any]]] = None,
    ):
        self._facts = facts or {}
        self._scenes = scenes or {}
        self._continuity = continuity or {}

    async def get_fact(self, workflow_state_id: str, key: str) -> Any:
        return self._facts.get(key)

    async def get_all_facts(self, workflow_state_id: str) -> Dict[str, Any]:
        return self._facts

    async def get_scene(self, workflow_state_id: str, scene_number: int) -> Optional[Any]:
        return self._scenes.get(scene_number)

    async def get_all_scenes(self, workflow_state_id: str) -> Dict[int, Any]:
        return self._scenes

    async def get_scene_continuity_info(self, workflow_state_id: str, scene_number: int) -> Dict[str, Any]:
        return self._continuity.get(scene_number, {})


class StubMemoryProvider:
    """测试用的记忆提供者 - 返回预设数据。"""

    def __init__(
        self,
        scene_references: Optional[Dict[str, Any]] = None,
        motion_guidance: Optional[Dict[str, Any]] = None,
        previous_frame: Optional[str] = None,
    ):
        self._scene_references = scene_references or {}
        self._motion_guidance = motion_guidance or {}
        self._previous_frame = previous_frame
        self._stored_frames: Dict[int, str] = {}

    async def retrieve_scene_references(
        self, workflow_state_id: str, scene_number: int, agent_name: str
    ) -> Dict[str, Any]:
        return self._scene_references

    async def retrieve_motion_guidance(
        self, workflow_state_id: str, scene_number: int, agent_name: str
    ) -> Dict[str, Any]:
        return self._motion_guidance

    async def store_scene_final_frame(self, scene_number: int, frame_url: str) -> None:
        self._stored_frames[scene_number] = frame_url

    async def retrieve_previous_frame_url(self, scene_number: int) -> Optional[str]:
        return self._previous_frame

    async def get_scene_continuity_info(self, scene_number: int) -> Dict[str, Any]:
        if self._previous_frame:
            return {
                "requires_continuity": True,
                "from_scene": max(scene_number - 1, 0),
                "previous_frame_path": self._previous_frame,
            }
        return {}


class MockSceneSnapshot:
    """模拟场景快照对象。"""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


# ===== Tests =====


@pytest.mark.asyncio
async def test_consistency_tool_empty_assets_without_concept_plan():
    """验证没有 concept_plan 时，工具返回空资产。

    这是核心测试：证明工具可以在没有全局服务的情况下独立运行。
    """
    from app.agents.tools.consistency_tool import ConsistencyTool

    # 准备空的 facts provider（没有 concept_plan）
    facts_provider = StubFactsProvider(facts={}, scenes={})
    memory_provider = StubMemoryProvider()

    # 使用依赖注入创建工具
    tool = ConsistencyTool(
        facts_provider=facts_provider,
        memory_provider=memory_provider,
    )

    # 执行查询
    result = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
            },
            "context": {"workflow_state_id": "test-wf"},
        }
    )

    # 验证结果
    assert result.success
    payload = result.result or {}
    assert payload.get("scene_number") == 1
    assert payload.get("workflow_state_id") == "test-wf"

    # 关键断言：没有 concept_plan，各资产类别应该为空
    assets = payload.get("assets", {})

    # 打印返回结果，便于调试
    print(f"\n返回的 assets: {assets}")

    assert assets.get("style") == {}, "没有 concept_plan，style 应该为空"
    assert assets.get("characters", {}).get("characters") == [], "没有角色信息时为空列表"
    # environment 在没有 scene 时返回空字典
    assert assets.get("environment") == {}, "没有场景信息时，environment 应该为空字典"


@pytest.mark.asyncio
async def test_consistency_tool_collects_style_from_concept_plan():
    """验证有 concept_plan 时，工具能正确收集风格资产。"""
    from app.agents.tools.consistency_tool import ConsistencyTool

    # 准备包含 concept_plan 的 facts
    concept_plan = {
        "intelligent_style_design": {
            "style_name": "水墨光影诗",
            "style_description": "墨色留白与光影交织",
            "visual_approach": "动画",
        },
        "consistency_guidelines": {
            "character_consistency": "画魂师保持白发与素色长袍",
            "environment_consistency": "画室保持月光与墨色对比",
        },
    }
    facts_provider = StubFactsProvider(facts={"concept_plan": concept_plan})
    memory_provider = StubMemoryProvider()

    tool = ConsistencyTool(
        facts_provider=facts_provider,
        memory_provider=memory_provider,
    )

    # 只请求 style 资产
    result = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
            },
            "context": {"workflow_state_id": "test-wf"},
        }
    )

    assert result.success
    assets = result.result["assets"]

    # 验证风格资产
    style = assets.get("style", {})
    assert style.get("intelligent_style_design", {}).get("style_name") == "水墨光影诗"
    assert "consistency_guidelines" in style
    assert "characters" in assets


@pytest.mark.asyncio
async def test_consistency_tool_collects_characters_from_concept_plan():
    """验证工具能正确收集角色资产。"""
    from app.agents.tools.consistency_tool import ConsistencyTool

    # 准备包含角色信息的 concept_plan
    concept_plan = {
        "roles": [
            {
                "name": "画魂师",
                "display_name": "画魂师",
                "key_traits": ["白发", "素色长袍"],
                "prompt_snippet": "保持白发与素色长袍的东方画师形象",
            }
        ],
        "scenes": [
            {
                "scene_number": 1,
                "characters_present": ["画魂师"],
                "character_descriptions": ["白发苍苍，素色长袍"],
            }
        ],
    }
    facts_provider = StubFactsProvider(facts={"concept_plan": concept_plan})
    memory_provider = StubMemoryProvider()

    tool = ConsistencyTool(
        facts_provider=facts_provider,
        memory_provider=memory_provider,
    )

    result = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
                "workflow_state_id": "test-wf",
            },
        }
    )

    assert result.success
    assets = result.result["assets"]

    # 验证角色资产
    characters = assets.get("characters", {})
    character_list = characters.get("characters", [])
    assert len(character_list) > 0, "应该有角色信息"
    assert any(char.get("name") == "画魂师" for char in character_list), "应该包含画魂师"


@pytest.mark.asyncio
async def test_consistency_tool_memory_integration():
    """验证工具能正确从 MemoryProvider 获取记忆数据。"""
    from app.agents.tools.consistency_tool import ConsistencyTool

    # 准备记忆数据
    memory_provider = StubMemoryProvider(
        scene_references={"reference_image": "https://example.com/ref.jpg"},
        motion_guidance={"camera_movement": "pan_right"},
        previous_frame="https://example.com/prev_frame.jpg",
    )
    facts_provider = StubFactsProvider()

    tool = ConsistencyTool(
        facts_provider=facts_provider,
        memory_provider=memory_provider,
    )

    result = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 2,
            },
            "context": {"workflow_state_id": "test-wf"},
        }
    )

    assert result.success
    assets = result.result["assets"]

    # 验证记忆资产
    assert "scene_references" in assets
    assert assets["scene_references"]["reference_image"] == "https://example.com/ref.jpg"

    continuity = assets.get("continuity", {})
    assert "motion_guidance" in continuity
    assert continuity["motion_guidance"]["camera_movement"] == "pan_right"


@pytest.mark.asyncio
async def test_consistency_tool_register_reference():
    """验证工具能注册参考资源。"""
    from app.agents.tools.consistency_tool import ConsistencyTool

    memory_provider = StubMemoryProvider()
    facts_provider = StubFactsProvider()

    tool = ConsistencyTool(
        facts_provider=facts_provider,
        memory_provider=memory_provider,
    )

    result = await tool.execute(
        {
            "action": "register_reference",
            "parameters": {
                "scene_number": 3,
                "reference_type": "final_frame",
                "reference_value": "https://example.com/scene3_final.jpg",
            },
            "context": {"workflow_state_id": "test-wf"},
        }
    )

    assert result.success
    assert result.result["stored"] is True

    # 验证数据被存储
    assert 3 in memory_provider._stored_frames
    assert memory_provider._stored_frames[3] == "https://example.com/scene3_final.jpg"


@pytest.mark.asyncio
async def test_consistency_tool_caching():
    """验证工具的缓存机制。"""
    from app.agents.tools.consistency_tool import ConsistencyTool

    concept_plan = {
        "intelligent_style_design": {"style_name": "测试风格"},
    }
    facts_provider = StubFactsProvider(facts={"concept_plan": concept_plan})
    memory_provider = StubMemoryProvider()

    tool = ConsistencyTool(
        facts_provider=facts_provider,
        memory_provider=memory_provider,
    )

    # 第一次查询
    result1 = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
            },
            "context": {"workflow_state_id": "test-wf"},
        }
    )

    # 第二次查询（应该使用缓存）
    result2 = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
                "use_cache": True,
            },
            "context": {"workflow_state_id": "test-wf"},
        }
    )

    assert result1.success
    assert result2.success
    # 两次结果应该一致（从缓存获取）
    assert result1.result["assets"] == result2.result["assets"]
