"""专门验证 consistency_tool.get_prompt_assets 在没有前置数据时返回空资产。

这是对应日志中根因的精确测试：
- 工具执行成功但返回空 assets
- 合约无法写入 prepared_assets
- 下一轮 OBS 看不到准备完成，LLM 反复调用
"""

import pytest
import json
from typing import Any, Dict, Optional


class StubFactsProvider:
    """空的事实提供者。"""

    def __init__(self, continuity: Optional[Dict[int, Dict[str, Any]]] = None):
        self._continuity = continuity or {}

    async def get_fact(self, workflow_state_id: str, key: str) -> Any:
        return None

    async def get_all_facts(self, workflow_state_id: str) -> Dict[str, Any]:
        return {}

    async def get_scene(self, workflow_state_id: str, scene_number: int) -> Optional[Any]:
        return None

    async def get_all_scenes(self, workflow_state_id: str) -> Dict[int, Any]:
        return {}

    async def get_scene_continuity_info(self, workflow_state_id: str, scene_number: int) -> Dict[str, Any]:
        return self._continuity.get(scene_number, {})


class StubMemoryProvider:
    """空的记忆提供者。"""

    async def retrieve_scene_references(
        self, workflow_state_id: str, scene_number: int, agent_name: str
    ) -> Dict[str, Any]:
        return {}

    async def retrieve_motion_guidance(
        self, workflow_state_id: str, scene_number: int, agent_name: str
    ) -> Dict[str, Any]:
        return {}

    async def store_scene_final_frame(self, scene_number: int, frame_url: str) -> None:
        pass

    async def retrieve_previous_frame_url(self, scene_number: int) -> Optional[str]:
        return None

    async def get_scene_continuity_info(self, scene_number: int) -> Dict[str, Any]:
        return {}


@pytest.mark.asyncio
async def test_consistency_tool_returns_empty_assets_without_data():
    """
    核心根因测试：验证没有前置数据时，consistency_tool 返回空资产。

    模拟场景：
    - Shared WM 没有 concept_plan
    - Shared WM 没有 scene 信息
    - Memory 没有任何记录

    预期结果：
    - 工具执行成功（success=True）
    - 但 assets 各字段为空：style={}, characters={characters: []}, environment={}
    - 这会导致合约写回时没有有效数据，prepared_assets_refs 保持为 []
    """
    from app.agents.tools.consistency_tool import ConsistencyTool

    # 完全空的 provider
    facts_provider = StubFactsProvider()
    memory_provider = StubMemoryProvider()

    tool = ConsistencyTool(
        facts_provider=facts_provider,
        memory_provider=memory_provider,
    )

    # 执行 get_prompt_assets
    result = await tool.execute(
        {
            "action": "get_prompt_assets",
            "parameters": {
                "scene_number": 1,
            },
            "context": {"workflow_state_id": "wf-test-empty"},
        }
    )

    # 验证执行成功
    assert result.success, "工具应该执行成功，即使没有数据"

    payload = result.result
    assets = payload.get("assets", {})

    # 打印详细信息
    print("\n" + "=" * 80)
    print("【根因验证】consistency_tool 无前置数据时的返回值：")
    print("=" * 80)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("=" * 80)

    # 验证各资产类别为空
    print("\n验证各资产类别：")
    print(f"  style: {assets.get('style')}")
    print(f"  characters: {assets.get('characters')}")
    print(f"  environment: {assets.get('environment')}")
    print(f"  continuity: {assets.get('continuity')}")

    # 关键断言：这些空值会导致合约写回失败
    assert assets.get("style") == {}, "❌ style 为空，无法写入 prepared_assets"

    characters = assets.get("characters", {})
    assert characters.get("characters") == [], "❌ characters 为空列表，无法写入 prepared_assets"

    assert assets.get("environment") == {}, "❌ environment 为空，无法写入 prepared_assets"

    # continuity 可能返回空字典
    continuity = assets.get("continuity", {})
    assert not continuity or all(
        not v for v in continuity.values()
    ), "❌ continuity 为空或全部值为空"

    print("\n✅ 验证完成：工具返回空资产，符合日志中观察到的根因")
    print("   → 这会导致 _apply_tool_output_contract 无数据写入")
    print("   → prepared_assets_refs 保持为 []")
    print("   → 下一轮 OBS 看不到'场景已准备'")
    print("   → LLM 继续调用同一个工具，进入死循环\n")


@pytest.mark.asyncio
async def test_consistency_tool_returns_valid_assets_with_data():
    """
    对比测试：验证有前置数据时，工具返回有效资产。

    这个测试证明问题不在工具本身，而在前置数据缺失。
    """
    from app.agents.tools.consistency_tool import ConsistencyTool

    # 准备有效的 concept_plan
    class FactsProviderWithData:
        async def get_all_facts(self, workflow_state_id: str) -> Dict[str, Any]:
            return {
                "concept_plan": {
                    "intelligent_style_design": {
                        "style_name": "测试风格",
                        "visual_approach": "真人实拍",
                    },
                    "roles": [
                        {
                            "name": "测试角色",
                            "display_name": "测试角色",
                            "key_traits": ["特征1", "特征2"],
                        }
                    ],
                    "scenes": [
                        {
                            "scene_number": 1,
                            "characters_present": ["测试角色"],
                            "character_descriptions": ["角色描述"],
                        }
                    ],
                }
            }

        async def get_scene(self, workflow_state_id: str, scene_number: int):
            return None

    facts_provider = FactsProviderWithData()
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
            },
            "context": {"workflow_state_id": "wf-test-valid"},
        }
    )

    assert result.success
    assets = result.result.get("assets", {})

    print("\n" + "=" * 80)
    print("【对比】有前置数据时的返回值：")
    print("=" * 80)
    print(json.dumps(assets, indent=2, ensure_ascii=False))
    print("=" * 80)

    # 验证返回了有效数据
    assert assets.get("style") != {}, "✅ style 有数据"
    assert len(assets.get("characters", {}).get("characters", [])) > 0, "✅ characters 有数据"

    print("\n✅ 对比验证：有前置数据时，工具正常返回资产")
    print("   → 合约可以成功写入 prepared_assets")
    print("   → LLM 可以看到准备完成，继续下一步\n")
