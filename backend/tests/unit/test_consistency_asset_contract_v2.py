import asyncio
import json

import pytest

from app.agents.tools.base_tool import ToolInput
from app.agents.tools.consistency_tool import ConsistencyTool
from app.agents.tools.image_prompt_composer_tool import ImagePromptComposerTool
from app.agents.tools.video_prompt_composer_tool import VideoPromptComposerTool


class _StubMemoryProvider:
    async def retrieve_scene_references(self, workflow_state_id: str, scene_number: int, agent_name: str):
        return {}

    async def retrieve_motion_guidance(self, workflow_state_id: str, scene_number: int, agent_name: str):
        return {}

    async def store_scene_final_frame(self, scene_number: int, frame_url: str) -> None:
        return None

    async def retrieve_previous_frame_url(self, scene_number: int):
        return "https://example.com/scene_3_tail.jpg"

    async def get_scene_continuity_info(self, workflow_state_id: str, scene_number: int):
        return {
            "requires_continuity": True,
            "motion_guidance": {"scene_guidance": {"description": "延续前冲后的爆发趋势"}},
            "transition_notes": "接住上一场尾帧的前冲势能",
        }


def test_consistency_tool_emits_global_opening_and_local_layers(tmp_path):
    scene_info = {
        "concept_plan": {
            "consistency_guidelines": {
                "style_consistency": "非写实仙侠动态水墨，墨色边缘与灵光粒子保持统一",
                "character_consistency": "韩立与黑袍修士保持既定造型",
                "environment_consistency": "秘境静室保持冷暖对比与压迫感",
                "object_consistency": "长剑与经卷保持既定造型",
            },
            "intelligent_style_design": {
                "style_name": "仙侠动态水墨",
                "style_tags": ["非写实", "水墨", "灵光粒子"],
                "color_palette": ["深蓝灰", "金白"],
            },
            "roles": [
                {"name": "韩立", "key_traits": ["青年男性", "深蓝灰修仙袍"]},
                {"name": "黑袍修士", "key_traits": ["黑袍", "暗红纹路法术"]},
            ],
        },
        "scenes_to_generate": [
            {
                "scene_number": 4,
                "visual_description": "韩立在秘境静室中聚气反击",
                "opening_state": "韩立半跪稳住身形，剑尖擦地拖出石屑",
                "mood_and_atmosphere": "压迫感强、风暴前的收束",
                "camera_angle": "中景缓推",
                "image_url": "https://example.com/scene4.png",
                "characters_present": ["韩立", "黑袍修士"],
                "character_descriptions": ["韩立深蓝灰修仙袍", "黑袍修士黑袍与暗红纹路"],
                "depends_on_scene": 3,
                "continuity_reason": "接住上一场尾帧的前冲势能",
            }
        ],
    }
    scene_path = tmp_path / "scene_info.json"
    scene_path.write_text(json.dumps(scene_info, ensure_ascii=False), encoding="utf-8")

    tool = ConsistencyTool(memory_provider=_StubMemoryProvider())
    result = asyncio.run(
        tool.execute(
            ToolInput(
                action="get_prompt_assets",
                parameters={"scene_number": 4, "scene_info_ref": str(scene_path)},
                context={"workflow_state_id": "wf-consistency-v2"},
            )
        )
    )

    assert result.success is True
    assets = result.result["assets"]
    assert assets["style"]["global_lock"]["headline"] == "仙侠动态水墨"
    assert assets["characters"]["global_lock"]["guidelines"] == "韩立与黑袍修士保持既定造型"
    assert assets["environment"]["opening_anchor"]["opening_state"] == "韩立半跪稳住身形，剑尖擦地拖出石屑"
    assert assets["continuity"]["local_continuity"]["enabled"] is True
    assert assets["continuity"]["local_continuity"]["depends_on_scene"] == 3
    assert assets["continuity"]["local_continuity"]["previous_frame_available"] is True


def test_video_prompt_composer_uses_structured_consistency_labels():
    assets = {
        "style": {"global_lock": {"style_guidelines": "非写实仙侠动态水墨", "headline": "仙侠动态水墨"}},
        "characters": {
            "global_lock": {"guidelines": "角色造型保持稳定", "stable_traits": ["韩立深蓝灰修仙袍"]},
            "scene_cast": {"present": ["韩立"], "descriptions": ["深蓝灰修仙袍"]},
        },
        "environment": {
            "global_lock": {"guidelines": "秘境静室冷暖对比"},
            "opening_anchor": {"opening_state": "韩立半跪稳住身形", "camera_angle": "中景缓推"},
        },
        "continuity": {"local_continuity": {"depends_on_scene": 3, "transition_notes": "接住前冲势能"}},
    }

    composer = VideoPromptComposerTool(metadata=VideoPromptComposerTool.get_metadata())
    sections, categories = composer._build_consistency_sections(assets)
    outline = composer._merge_prompt_outline(
        {
            "main_key": "韩立稳住身形后准备反击黑袍修士",
            "event_arc": ["开场状态：韩立半跪稳住身形"],
            "motion_guidance": ["动作补充：韩立压低重心准备反击"],
            "style_continuity": [],
            "technical_note": ["目标时长：10s"],
        },
        sections,
    )
    prompt_text = composer._render_prompt_outline(4, outline)

    assert "风格与连续性" in prompt_text
    assert "全局画风锁定" in prompt_text
    assert "角色锁定" in prompt_text
    assert "开场锚点" in prompt_text
    assert "局部连续性" in prompt_text
    assert "一致性要求" not in prompt_text
    assert "道具" not in prompt_text
    assert categories == ["global_style_lock", "character_lock", "opening_anchor", "local_continuity"]


def test_video_prompt_composer_compresses_consistency_block_to_short_locks():
    assets = {
        "style": {
            "global_lock": {
                "style_guidelines": "坚持既定的风格组合和色彩基调，并持续强化流动墨色线条、灵光粒子和古典仙侠质感。",
                "headline": "仙侠动态水墨",
                "style_tags": ["非写实", "水墨", "灵光粒子", "古典仙侠"],
                "object_guidelines": "重复出现的关键道具需保持造型与用途一致。",
            }
        },
        "characters": {
            "global_lock": {"guidelines": "确保角色外形与特征在所有场景保持一致。"},
            "scene_cast": {
                "present": ["韩立"],
                "descriptions": [
                    "韩立：原型：逆袭者；物种：人类；青年形象，坚毅沉稳，从凡人到修仙者的蜕变，内在潜力觉醒，逆天改命的象征；深蓝与灰色服饰，简约修仙袍，灵光微绕；古朴修炼典籍，长剑；主角，展现成长与抗争",
                    "身着深蓝灰色修仙袍，手持长剑，警惕地观察周围环境，在幽蓝与深绿交织的光影中显得格外醒目。",
                ],
            },
        },
        "environment": {
            "global_lock": {"guidelines": "场景氛围和叙事节奏需延续骨架设定。"},
            "opening_anchor": {
                "opening_state": "场景设定在古老秘境户外，以冷色调为主，幽蓝与深绿交织的光影对比强烈；秘境入口布满符文雕刻，奇异植被如水墨线条般流动生长。",
                "mood_and_atmosphere": "神秘且略带压迫感",
                "camera_angle": "广角摇镜结合中景跟踪镜头",
            },
        },
        "continuity": {"local_continuity": {"depends_on_scene": 3, "transition_notes": "接住上一场尾帧的前冲势能并保持韩立主体"}}
    }

    composer = VideoPromptComposerTool(metadata=VideoPromptComposerTool.get_metadata())
    sections, categories = composer._build_consistency_sections(assets)
    outline = composer._merge_prompt_outline(
        {
            "main_key": "韩立接住前冲势能，继续推进对抗",
            "event_arc": ["开场状态：韩立在秘境入口前警惕前行"],
            "motion_guidance": [],
            "style_continuity": [],
            "technical_note": ["目标时长：10s"],
        },
        sections,
    )
    prompt_text = composer._render_prompt_outline(4, outline)

    assert "全局画风锁定" in prompt_text
    assert "角色锁定" in prompt_text
    assert "开场锚点" in prompt_text
    assert "局部连续性" in prompt_text
    assert "原型：" not in prompt_text
    assert "物种：" not in prompt_text
    assert "镜头起点" not in prompt_text
    assert "氛围：" not in prompt_text
    assert "一致性要求" not in prompt_text
    assert len(prompt_text) < 360
    assert categories == ["global_style_lock", "character_lock", "opening_anchor", "local_continuity"]


def test_image_prompt_composer_uses_opening_anchor_label():
    assets = {
        "style": {"global_lock": {"style_guidelines": "非写实水墨风", "headline": "水墨光影诗"}},
        "characters": {
            "global_lock": {"guidelines": "画魂师保持白发与素色长袍"},
            "scene_cast": {"present": ["画魂师"], "descriptions": ["白发苍苍，素色长袍"]},
        },
        "environment": {
            "global_lock": {"guidelines": "画室保持月光与墨色对比"},
            "opening_anchor": {"opening_state": "月光洒在空白画卷上", "mood_and_atmosphere": "静谧神秘"},
        },
        "continuity": {"local_continuity": {"enabled": False}},
    }

    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    block, categories, locked_segments = composer._build_consistency_block(assets)

    assert "全局画风锁定" in block
    assert "开场锚点" in block
    assert "月光洒在空白画卷上" in block
    assert "局部连续性" not in block
    assert "氛围" not in block
    assert "镜头" not in block
    assert categories == ["global_style_lock", "character_lock", "opening_anchor"]
    assert locked_segments == [
        "水墨光影诗",
        "角色：画魂师；场景特征：白发苍苍，素色长袍",
        "开场状态：月光洒在空白画卷上；环境基调：画室保持月光与墨色对比",
    ]


def test_image_prompt_composer_merges_consistency_into_structured_sections(monkeypatch):
    tool = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    captured = {}

    monkeypatch.setattr(tool, "_load_scene_info", lambda ref: {"scenes_to_generate": [{"scene_number": 3}]})
    monkeypatch.setattr(tool, "_extract_scene_entry", lambda scene_info, scene_number: {"scene_number": scene_number})
    monkeypatch.setattr(
        tool,
        "_build_scene_data",
        lambda scene_entry, scene_number, **_kwargs: {
            "scene_number": scene_number,
            "image_purpose": "action_keyframe",
            "frame_thesis": "韩立挥剑迎击黑袍修士的关键瞬间",
        },
    )
    monkeypatch.setattr(tool, "_build_style_guidance", lambda scene_info: {})
    monkeypatch.setattr(tool, "_resolve_style_name", lambda style_guidance: "")

    class FakeImageTool:
        async def _create_image_prompt_from_scene(self, scene_data, style_name, style_guidance):
            return (
                "关键帧构图：\n"
                "韩立挥剑迎击黑袍修士的关键瞬间\n\n"
                "画面焦点：\n"
                "- 飞剑与紫黑法术正面对撞\n\n"
                "主体锁定：\n"
                "- 韩立青衫持剑，黑袍修士悬空施压\n\n"
                "风格指导：\n"
                "- 非写实仙侠水墨，能量粒子清晰\n\n"
                "画面要求：关键帧静态画面，主体姿态明确，空间关系清晰，可自然衔接后续运动，无文字无水印。"
            )

        async def execute(self, tool_input):
            captured["prompt"] = tool_input.parameters["prompt"]
            return {"success": True, "result": {"image_url": "https://img.example.com/keyframe.jpg"}}

    class FakeConsistencyTool:
        async def execute(self, tool_input):
            return {
                "success": True,
                "result": {
                    "assets": {
                        "style": {
                            "global_lock": {
                                "headline": "修仙水墨风暴",
                                "style_guidelines": "保持冷暖对撞与水墨粒子质感",
                            }
                        },
                        "characters": {
                            "scene_cast": {
                                "present": ["韩立", "黑袍修士"],
                                "descriptions": ["韩立青衫持剑", "黑袍修士操控紫黑法器"],
                            }
                        },
                        "environment": {
                            "global_lock": {"guidelines": "废墟空间保持冲击后的碎裂压迫感"},
                            "opening_anchor": {"opening_state": "碎石与尘浪向外掀开，空间仍在震颤"},
                        },
                        "continuity": {
                            "local_continuity": {
                                "depends_on_scene": 2,
                                "transition_notes": "接住上一场法术对撞后的前冲势能",
                            }
                        },
                    }
                },
            }

    class FakeRegistry:
        def get_tool(self, name):
            if name == "image_generation":
                return FakeImageTool()
            if name == "consistency_tool":
                return FakeConsistencyTool()
            raise AssertionError(f"unexpected tool {name}")

    monkeypatch.setattr("app.agents.tools.tool_registry.get_tool_registry", lambda: FakeRegistry())

    result = asyncio.run(
        tool._execute_impl(
            ToolInput(
                action="generate",
                parameters={"scene_number": 3, "scene_info_ref": "unused.json"},
                context={},
            )
        )
    )

    prompt_text = captured["prompt"]
    assert result["image_url"] == "https://img.example.com/keyframe.jpg"
    assert "一致性要求" not in prompt_text
    assert "风格指导" in prompt_text
    assert "主体锁定" in prompt_text
    assert "画面焦点" in prompt_text
    assert "连续性提示" in prompt_text
    assert "全局画风锁定：修仙水墨风暴" in prompt_text
    assert "局部连续性：承接场景2：接住上一场法术对撞后的前冲势能" in prompt_text
    assert prompt_text.count("风格指导：") == 1
    assert "画面要求：" in prompt_text
    assert result["metadata"]["frame_thesis"] == "韩立挥剑迎击黑袍修士的关键瞬间"
    assert "diagnostics" not in result["metadata"]


def test_image_prompt_composer_filters_montage_language_from_still_consistency():
    assets = {
        "style": {"global_lock": {"headline": "动态水墨奇幻", "style_tags": ["水墨", "奇幻"], "color_palette": ["青灰", "金白"]}},
        "characters": {
            "global_lock": {"stable_traits": ["青灰长袍", "青竹剑"], "guidelines": "韩立造型保持稳定"},
            "scene_cast": {
                "present": ["韩立", "阴影人物"],
                "descriptions": [
                    "韩立：青灰长袍，青竹剑，坚毅沉稳",
                    "快速切换场景中展现不同状态，最终以标题文字闪现收尾",
                ],
            },
        },
        "environment": {
            "global_lock": {"guidelines": "高潮场景保持水墨明暗对比"},
            "opening_anchor": {
                "opening_state": "韩立在古朴村落中沐浴神秘光芒",
                "mood_and_atmosphere": "高潮激昂，快速剪辑增强节奏感",
                "camera_angle": "快速切换的中近景与动态推拉镜头",
            },
        },
        "continuity": {"local_continuity": {"depends_on_scene": 4, "transition_notes": "承接前序悬念并收束到韩立主体特写"}},
    }

    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    block, categories, locked_segments = composer._build_consistency_block(assets)

    assert "快速切换" not in block
    assert "标题" not in block
    assert "镜头" not in block
    assert "韩立在古朴村落中沐浴神秘光芒" in block
    assert categories == ["global_style_lock", "character_lock", "opening_anchor", "local_continuity"]
    assert all("快速切换" not in item for item in locked_segments)
    assert all("标题" not in item for item in locked_segments)


def test_image_prompt_composer_character_reference_omits_environment_and_continuity():
    assets = {
        "style": {"global_lock": {"headline": "动态水墨奇幻"}},
        "characters": {
            "global_lock": {"stable_traits": ["青灰长袍", "黑发束起"]},
            "scene_cast": {"present": ["韩立"], "descriptions": ["韩立：青灰长袍，黑发束起，神情坚毅"]},
        },
        "environment": {"opening_anchor": {"opening_state": "不应进入角色参考图"}},
        "continuity": {"local_continuity": {"depends_on_scene": 4, "transition_notes": "不应进入角色参考图"}},
    }

    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    block, categories, locked_segments = composer._build_consistency_block(
        assets,
        image_purpose="character_reference",
        task_direction="avatar",
    )

    assert "开场锚点" not in block
    assert "局部连续性" not in block
    assert categories == ["global_style_lock", "character_lock"]
    assert locked_segments == [
        "动态水墨奇幻",
        "参考方向：avatar；角色：韩立；稳定特征：青灰长袍、黑发束起；场景特征：韩立：青灰长袍，黑发束起，神情坚毅",
    ]


def test_image_prompt_composer_prefers_static_end_state_for_high_risk_anchor():
    assets = {
        "style": {"global_lock": {"headline": "动态水墨奇幻"}},
        "characters": {
            "scene_cast": {"present": ["韩立"], "descriptions": ["韩立：青灰色长袍，青竹剑，坚毅沉稳"]},
        },
        "environment": {
            "global_lock": {"guidelines": "幽暗遗迹保持蓝绿冷光与静态压迫感"},
            "opening_anchor": {
                "opening_state": "蓝绿色幽光笼罩残垣，巨蟒张开巨口扑向镜头",
                "end_state": "青竹剑光映亮韩立坚毅面庞，巨蟒盘踞在后方阴影中",
                "visual_description": "幽暗遗迹与苔藓残垣",
            },
        },
        "continuity": {"local_continuity": {"enabled": False}},
    }

    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    block, categories, locked_segments = composer._build_consistency_block(assets)

    assert "静态落点：青竹剑光映亮韩立坚毅面庞" in block
    assert "扑向镜头" not in block
    assert "巨口" not in block
    assert categories == ["global_style_lock", "character_lock", "opening_anchor"]
    assert any("静态落点" in item for item in locked_segments)


def test_image_prompt_composer_compresses_role_card_character_lock():
    assets = {
        "style": {"global_lock": {"headline": "动态水墨奇幻"}},
        "characters": {
            "global_lock": {"stable_traits": ["青灰长袍", "青竹剑"]},
            "scene_cast": {
                "present": ["韩立", "阴影人物"],
                "descriptions": [
                    "韩立：原型：成长者；物种：人类；从凡人蜕变的修仙者，坚毅沉稳，成长型主角，手持法器，神秘气质；青灰色长袍，水墨线条勾勒，动态光影效果；青竹剑，储物袋；主角，展现从平凡到超凡的成长历程",
                    "阴影人物：原型：挑战者；物种：人类；神秘莫测，反派势力代表，阴影笼罩，未知威胁；深紫色调，模糊轮廓，低光环境；暗纹长袍；反派或神秘势力，制造悬念与冲突",
                ],
            },
        },
        "environment": {"opening_anchor": {"opening_state": "韩立特写定格，背景化作动态水墨晕染"}},
        "continuity": {"local_continuity": {"enabled": False}},
    }

    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    block, _categories, locked_segments = composer._build_consistency_block(assets)

    assert "成长历程" not in block
    assert "未知威胁" not in block
    assert "悬念与冲突" not in block
    assert "青灰色长袍" in block
    assert "青竹剑" in block
    assert "暗纹长袍" in block
    assert all("成长历程" not in item for item in locked_segments)
