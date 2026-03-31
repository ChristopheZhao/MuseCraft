import json

import pytest

from app.agents.tools.base_tool import ToolInput
from app.agents.tools.video_prompt_builder_tool import VideoPromptBuilderTool


@pytest.mark.asyncio
async def test_video_prompt_builder_uses_action_phases_as_prompt_body(tmp_path):
    scene_info = {
        "scenes_to_generate": [
            {
                "scene_number": 4,
                "duration": 10,
                "image_url": "https://example.com/scene4.png",
                "opening_state": "韩立半跪稳住身形，剑尖擦地拖出石屑",
                "event_trigger": "黑袍修士逼近施压，迫使韩立强行起身聚气",
                "action_phases": [
                    {
                        "phase": "起势",
                        "observable_actions": "韩立压低重心稳住身形，衣摆被气流扯动",
                        "camera_hint": "中景缓推",
                    },
                    {
                        "phase": "爆发",
                        "observable_actions": "金光骤然爆开，碎石和尘浪向外掀开，黑袍修士被震退",
                        "camera_hint": "推进后定住",
                    },
                ],
                "end_state": "镜头停在韩立抬头定格，金光未散",
                "camera_language": "以中景建立受压状态，随后推近到爆发定格",
                "script_text": "韩立被压制后强行起身，聚气反击，最终用爆发的金光震退黑袍修士。",
                "narrative_description": "突出成长与反击的情绪转折",
            }
        ]
    }
    scene_path = tmp_path / "scene_info.json"
    scene_path.write_text(json.dumps(scene_info, ensure_ascii=False), encoding="utf-8")

    tool = VideoPromptBuilderTool()
    result = await tool.execute(
        ToolInput(
            action="build_prompt",
            parameters={"scene_number": 4, "scene_info_ref": str(scene_path)},
        )
    )

    assert result.success is True
    payload = result.result
    prompt_text = payload["prompt_text"]
    assert "开场状态" in prompt_text
    assert "动作推进" in prompt_text
    assert "韩立压低重心稳住身形" in prompt_text
    assert "金光骤然爆开" in prompt_text
    assert "镜头语言" in prompt_text
    assert "收束画面" in prompt_text
    assert "叙事要点" not in prompt_text
    assert payload["metadata"]["prompt_mode"] == "image_to_video"
    assert payload["metadata"]["action_source"] == "action_phases"


@pytest.mark.asyncio
async def test_video_prompt_builder_reads_legacy_motion_beats_schema(tmp_path):
    scene_info = {
        "scenes_to_generate": [
            {
                "scene_number": 2,
                "duration": 10,
                "image_url": "https://example.com/scene2.png",
                "visual_description": "韩立在密室中被压制",
                "motion_beats": [
                    {"visual_focus": "韩立稳住身形", "beat_summary": "剑尖擦地拖出石屑"},
                    {"visual_focus": "金光爆发", "beat_summary": "黑袍修士被冲击逼退"},
                ],
                "narrative_description": "通过战斗突出主角的压力",
            }
        ]
    }
    scene_path = tmp_path / "scene_info_motion.json"
    scene_path.write_text(json.dumps(scene_info, ensure_ascii=False), encoding="utf-8")

    tool = VideoPromptBuilderTool()
    result = await tool.execute(
        ToolInput(
            action="build_prompt",
            parameters={"scene_number": 2, "scene_info_ref": str(scene_path)},
        )
    )

    assert result.success is True
    payload = result.result
    prompt_text = payload["prompt_text"]
    assert "剑尖擦地拖出石屑" in prompt_text
    assert "黑袍修士被冲击逼退" in prompt_text
    assert "beat: ; beat:" not in prompt_text
    assert "收束画面" in prompt_text
    assert payload["metadata"]["action_source"] == "motion_beats"


@pytest.mark.asyncio
async def test_video_prompt_builder_prefers_action_phases_over_legacy_motion_beats(tmp_path):
    scene_info = {
        "scenes_to_generate": [
            {
                "scene_number": 2,
                "duration": 10,
                "image_url": "https://example.com/scene2.png",
                "opening_state": "韩立执剑立于秘境入口",
                "action_phases": [
                    {
                        "phase": "试探推进",
                        "observable_actions": "韩立侧身踏入入口，先观察四周符文流向",
                    },
                    {
                        "phase": "警觉收束",
                        "observable_actions": "他停步握紧长剑，将注意力锁定在前方异动",
                    },
                ],
                "motion_beats": [
                    {
                        "visual_focus": "旧版描述不应进入 prompt",
                        "beat_summary": "如果这里出现，说明 fallback 越权了",
                    }
                ],
            }
        ]
    }
    scene_path = tmp_path / "scene_info_prefer_action_phases.json"
    scene_path.write_text(json.dumps(scene_info, ensure_ascii=False), encoding="utf-8")

    tool = VideoPromptBuilderTool()
    result = await tool.execute(
        ToolInput(
            action="build_prompt",
            parameters={"scene_number": 2, "scene_info_ref": str(scene_path)},
        )
    )

    assert result.success is True
    prompt_text = result.result["prompt_text"]
    assert "试探推进" in prompt_text
    assert "警觉收束" in prompt_text
    assert "旧版描述不应进入 prompt" not in prompt_text
    assert "fallback 越权了" not in prompt_text
    assert result.result["metadata"]["action_source"] == "action_phases"


@pytest.mark.asyncio
async def test_video_prompt_builder_compacts_legacy_motion_beats_and_summary_prose(tmp_path):
    scene_info = {
        "scenes_to_generate": [
            {
                "scene_number": 2,
                "duration": 10,
                "image_url": "https://example.com/scene2.png",
                "visual_description": "场景设定在古老秘境户外，以冷色调为主，幽蓝与深绿交织的光影对比强烈；秘境入口布满符文雕刻，奇异植被如水墨线条般流动生长，隐约妖兽身影在背景中低吼移动，增强神秘压迫感。",
                "motion_beats": [
                    {
                        "visual_focus": "韩立踏入秘境入口，符文闪烁",
                        "beat_summary": "引入秘境，符文闪烁，营造神秘感",
                    },
                    {
                        "visual_focus": "奇异植被流动生长，光影幽蓝深绿交织",
                        "beat_summary": "植被流动，光影对比，增强奇幻氛围",
                    },
                    {
                        "visual_focus": "妖兽身影在背景中低吼移动，压迫感渐强",
                        "beat_summary": "妖兽低吼，压迫感增强，埋下冲突伏笔",
                    },
                ],
                "script_text": "秘境探幽，未知世界危机暗藏，韩立踏入幽蓝深绿交织的古老秘境，符文闪烁，妖兽低吼，压迫感渐强。",
            }
        ]
    }
    scene_path = tmp_path / "scene_info_legacy_compact.json"
    scene_path.write_text(json.dumps(scene_info, ensure_ascii=False), encoding="utf-8")

    tool = VideoPromptBuilderTool()
    result = await tool.execute(
        ToolInput(
            action="build_prompt",
            parameters={"scene_number": 2, "scene_info_ref": str(scene_path)},
        )
    )

    assert result.success is True
    prompt_text = result.result["prompt_text"]
    assert prompt_text.count("符文闪烁") == 1
    assert "营造神秘感" not in prompt_text
    assert "增强奇幻氛围" not in prompt_text
    assert "埋下冲突伏笔" not in prompt_text
    assert "未知世界危机暗藏" in prompt_text
    assert "韩立踏入幽蓝深绿交织的古老秘境" not in prompt_text
    assert "收束画面：妖兽身影在背景中低吼移动，压迫感渐强" in prompt_text


@pytest.mark.asyncio
async def test_video_prompt_builder_keeps_duration_scalable_action_arc_for_20s_scene(tmp_path):
    scene_info = {
        "scenes_to_generate": [
            {
                "scene_number": 6,
                "duration": 20,
                "opening_state": "韩立独自穿行在秘境回廊，四周幽蓝光影晃动",
                "event_trigger": "回廊尽头传来低沉震响，黑袍修士拖着暗红尾迹缓步现身",
                "action_phases": [
                    {
                        "phase": "建立压迫",
                        "observable_actions": "长廊纵深被拉开，韩立放慢脚步观察前方异动",
                        "camera_hint": "远景缓慢前推",
                        "relative_weight": 3,
                    },
                    {
                        "phase": "接近试探",
                        "observable_actions": "黑袍修士逼近，法杖暗光擦过墙面，韩立后撤半步稳住剑势",
                        "camera_hint": "中景跟随",
                        "relative_weight": 2,
                    },
                    {
                        "phase": "对峙升级",
                        "observable_actions": "两股灵力在回廊中央相撞，空气震颤，地面碎屑被卷起",
                        "camera_hint": "推进到近中景",
                        "relative_weight": 3,
                    },
                    {
                        "phase": "爆发前收束",
                        "observable_actions": "韩立握剑定势，镜头停在双方力量拉紧的瞬间，为下一场爆发留出入口",
                        "camera_hint": "定住并轻微压近",
                        "relative_weight": 2,
                    },
                ],
                "end_state": "空间被两股力量拉紧，冲突即将爆开",
                "camera_language": "从远景建立纵深压迫，再逐步推进到对峙收束",
                "script_text": "韩立在漫长回廊中先感知威胁，再与黑袍修士形成逐步升级的对峙。",
            }
        ]
    }
    scene_path = tmp_path / "scene_info_20s.json"
    scene_path.write_text(json.dumps(scene_info, ensure_ascii=False), encoding="utf-8")

    tool = VideoPromptBuilderTool()
    result = await tool.execute(
        ToolInput(
            action="build_prompt",
            parameters={"scene_number": 6, "scene_info_ref": str(scene_path)},
        )
    )

    assert result.success is True
    payload = result.result
    prompt_text = payload["prompt_text"]
    assert "- 目标时长：20s" in prompt_text
    assert "先建立压迫" in prompt_text
    assert "随后接近试探" in prompt_text
    assert "接着对峙升级" in prompt_text
    assert "最后爆发前收束" in prompt_text
    assert "0-3s" not in prompt_text
    assert payload["metadata"]["prompt_mode"] == "text_to_video"
    assert payload["metadata"]["action_source"] == "action_phases"
