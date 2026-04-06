from app.agents.tools.consistency_tool import ConsistencyTool
from app.agents.tools.manager import ToolManager, Exposure
from app.agents.utils.tool_contracts import extract_contract_slot_writes


def test_contract_writes_trim_and_scope_assets():
    tool = ConsistencyTool()
    contract = tool.get_output_contract("get_prompt_assets")

    payload = {
        "scene_number": 3,
        "assets": {
            "style": {
                "color_palette": [f"color-{i}" for i in range(10)],
                "mood": "calm " * 100,
                "intelligent_style_design": {
                    "style_name": "dreamscape" * 40,
                    "style_tags": [f"tag-{i}" for i in range(12)],
                },
            },
            "characters": {
                "characters": [
                    {
                        "name": f"hero-{i}",
                        "description": "desc " * 80,
                        "key_traits": ["brave", "curious", "resilient", "calm", "extra"],
                    }
                    for i in range(10)
                ]
            },
            "continuity": {
                "motion_guidance": "guide " * 200,
                "prev_scene_no": 2,
            },
        },
    }

    writes = extract_contract_slot_writes(payload, contract, default_scene=3)

    assert writes, "contract should produce at least one slot write"
    write = writes[0]
    assert write.slot == "prepared_assets"
    assert write.scene_number == 3
    value = write.value
    assert "style" in value and "characters" in value and "continuity" in value
    assert len(value["style"]["color_palette"]) <= 8
    assert len(value["style"]["mood"]) <= 120
    characters_bundle = value["characters"].get("characters") or []
    assert len(characters_bundle) <= 8
    assert len(value["continuity"]["motion_guidance"]) <= 400


def test_tool_manager_parameters_schema_is_pure_json_schema():
    class _StubFacts:
        async def get_fact(self, *_args, **_kwargs):
            return None

        async def get_all_facts(self, *_args, **_kwargs):
            return {}

        async def get_scene(self, *_args, **_kwargs):
            return None

        async def get_all_scenes(self, *_args, **_kwargs):
            return {}

        async def get_scene_continuity_info(self, *_args, **_kwargs):
            return {}

    class _StubMemory:
        async def retrieve_scene_references(self, *_args, **_kwargs):
            return {}

        async def retrieve_motion_guidance(self, *_args, **_kwargs):
            return {}

        async def store_scene_final_frame(self, *_args, **_kwargs):
            return None

        async def retrieve_previous_frame_url(self, *_args, **_kwargs):
            return None

        async def get_scene_continuity_info(self, *_args, **_kwargs):
            return {}

    tool = ConsistencyTool(facts_provider=_StubFacts(), memory_provider=_StubMemory())
    manager = ToolManager(policy_path="")
    allocated = {"consistency_tool": tool}
    exposure = {"consistency_tool": Exposure(expose=True, allowed_actions=["get_prompt_assets"])}

    fc_schema = manager.build_fc_schema(allocated_tools=allocated, exposure=exposure)

    assert fc_schema, "manager 应生成至少一个函数定义"
    function_def = fc_schema[0]["function"]

    params = function_def["parameters"]
    assert isinstance(params, dict)
    assert params.get("type") == "object"
    assert "description" not in params, "参数 schema 不应包含动作级描述"
    assert all(not key.startswith("x-") for key in params.keys()), "参数 schema 不应包含扩展字段"

    properties = params.get("properties") or {}
    assert "scene_number" in properties
    assert properties["scene_number"]["description"] == "目标场景编号"
