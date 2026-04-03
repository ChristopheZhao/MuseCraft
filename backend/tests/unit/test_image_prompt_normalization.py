import pytest

from app.agents.tools import image_prompt_normalization as norm_module
from app.agents.tools.base_tool import ToolError
from app.agents.tools.image_prompt_composer_tool import ImagePromptComposerTool


def test_select_scene_opening_root_projects_montage_scene_to_single_still():
    root = norm_module.select_scene_opening_root(
        {
            "scene_number": 5,
            "title": "终极预告",
            "visual_description": "场景以快速切换的剪辑呈现，最终定格于韩立特写镜头，标题与上映日期闪现。",
            "opening_state": "韩立在古朴村落中沐浴神秘光芒",
            "action_phases": [
                {"phase": "极速混剪", "observable_actions": "画面在韩立持剑战巨蟒、施法斗修仙者之间快速切换"},
                {"phase": "水墨定格", "observable_actions": "韩立特写镜头定格，背景化作动态水墨晕染，标题与上映日期闪现"},
            ],
            "motion_beats": [{"visual_focus": "韩立在多场景中的战斗与成长"}],
        }
    )

    assert "韩立特写" in root
    assert "快速切换" not in root
    assert "标题" not in root


def test_select_scene_opening_root_prefers_end_state_for_high_risk_opening():
    root = norm_module.select_scene_opening_root(
        {
            "title": "秘境探险",
            "opening_state": "蓝绿色幽光笼罩残垣，巨蟒张开巨口扑向镜头",
            "end_state": "青竹剑光映亮韩立坚毅面庞，巨蟒盘踞在后方阴影中",
            "action_phases": [{"observable_actions": "韩立身形灵动后撤，青竹剑挥出弧形剑气"}],
        }
    )

    assert "青竹剑光映亮韩立坚毅面庞" in root
    assert "扑向镜头" not in root
    assert "巨口" not in root


def test_normalize_still_text_does_not_semantically_rewrite_scene_text():
    text = "蓝绿色幽光笼罩残垣，巨蟒张开巨口扑向镜头"

    normalized = norm_module.normalize_still_text(text)

    assert normalized == text


def test_infer_image_purpose_promotes_action_scene_to_action_keyframe():
    purpose = norm_module.infer_image_purpose(
        {
            "scene_thesis": "黑袍修士先手压制，韩立正面迎击，冲突迅速升级为失控爆炸",
            "event_trigger": "黑袍修士释放紫黑法术洪流直冲韩立",
            "action_phases": [
                {"phase": "交锋", "observable_actions": "韩立飞剑出鞘正面撞击紫黑法术"},
                {"phase": "爆发", "observable_actions": "巨大的爆炸引发雷电与火焰交织，周围山石瞬间粉碎"},
            ],
            "end_state": "爆炸强光吞没画面，余波仍在震颤",
            "duration": 10,
        }
    )

    assert purpose == "climax_peak"


def test_select_frame_thesis_prefers_late_event_for_action_keyframe():
    thesis = norm_module.select_frame_thesis(
        {
            "opening_state": "黑袍修士悬浮半空，韩立于破碎山石间迎战",
            "event_trigger": "黑袍修士释放紫黑法术洪流",
            "action_phases": [
                {"phase": "交锋", "observable_actions": "韩立飞剑出鞘正面撞击紫黑法术"},
                {"phase": "爆发", "observable_actions": "巨大的爆炸引发雷电与火焰交织，周围山石瞬间粉碎"},
            ],
            "end_state": "爆炸强光吞没画面，余波仍在震颤",
        },
        image_purpose="action_keyframe",
    )

    assert "吞没画面" in thesis
    assert "余波仍在震颤" in thesis
    assert "悬浮半空" not in thesis


def test_image_prompt_composer_keeps_owner_fields_explicit_only(monkeypatch):
    calls = []
    original = norm_module.normalize_still_text

    def spy(value, *, max_len=None):
        calls.append((str(value or ""), max_len))
        return original(value, max_len=max_len)

    monkeypatch.setattr(norm_module, "normalize_still_text", spy)

    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())

    scene_data = composer._build_scene_data(
        {
            "scene_number": 5,
            "title": "终极预告",
            "visual_description": "场景以快速切换的剪辑呈现，最终定格于韩立特写镜头，标题与上映日期闪现。",
            "opening_state": "韩立在古朴村落中沐浴神秘光芒",
            "action_phases": [
                {"phase": "极速混剪", "observable_actions": "画面在韩立持剑战巨蟒、施法斗修仙者之间快速切换"},
                {"phase": "水墨定格", "observable_actions": "韩立特写镜头定格，背景化作动态水墨晕染，标题与上映日期闪现"},
            ],
            "character_descriptions": ["韩立：青灰色长袍，青竹剑，坚毅沉稳"],
        },
        5,
    )
    before_prompt = len(calls)
    prompt = composer._compose_prompt_text(
        scene_data,
        style_name="动态水墨奇幻",
        style_guidance={"style_name": "动态水墨奇幻", "visual_approach": "动画"},
    )
    after_prompt = len(calls)

    block, _categories, _locks = composer._build_consistency_block(
        {
            "style": {"global_lock": {"headline": "动态水墨奇幻"}},
            "characters": {"scene_cast": {"present": ["韩立"], "descriptions": ["韩立：青灰色长袍，青竹剑，坚毅沉稳"]}},
            "environment": {
                "opening_anchor": {
                    "opening_state": "韩立特写镜头定格，背景化作动态水墨晕染，标题与上映日期闪现"
                }
            },
            "continuity": {"local_continuity": {"enabled": False}},
        }
    )
    after_block = len(calls)

    assert "image_purpose" not in scene_data
    assert "frame_thesis" not in scene_data
    assert after_prompt > before_prompt
    assert after_block > after_prompt
    assert "韩立在古朴村落中沐浴神秘光芒" in prompt
    assert "标题" not in block


def test_image_prompt_composer_ignores_scene_payload_owner_overrides():
    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())

    scene_data = composer._build_scene_data(
        {
            "scene_number": 6,
            "title": "失控爆发",
            "opening_state": "韩立压低重心，剑锋前指",
            "visual_description": "灵光与碎石在身前激荡",
            "image_purpose": "climax_peak",
            "frame_thesis": "爆炸强光吞没画面",
        },
        6,
    )

    assert "image_purpose" not in scene_data
    assert "frame_thesis" not in scene_data


def test_image_prompt_composer_reports_missing_non_reference_owner_fields():
    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    scene_data = composer._build_scene_data({"scene_number": 9}, 9)

    with pytest.raises(ToolError) as excinfo:
        composer._compose_prompt_text(scene_data, style_name="", style_guidance={})

    assert excinfo.value.error_code == "missing_owner_fields"
    assert excinfo.value.details["scene_number"] == 9
    assert excinfo.value.details["owner_boundary"] == "scene_root"
    assert excinfo.value.details["required_any_of"] == ["opening_state", "visual_description", "title"]
    assert "opening_state" in str(excinfo.value)
    assert "visual_description" in str(excinfo.value)
    assert "title" in str(excinfo.value)


def test_image_prompt_composer_reports_missing_character_reference_owner_fields():
    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    scene_data = composer._build_scene_data(
        {"scene_number": 10, "task_direction": "avatar"},
        10,
        image_purpose="character_reference",
        task_direction="avatar",
    )

    with pytest.raises(ToolError) as excinfo:
        composer._compose_prompt_text(scene_data, style_name="", style_guidance={})

    assert excinfo.value.error_code == "missing_owner_fields"
    assert excinfo.value.details["scene_number"] == 10
    assert excinfo.value.details["owner_boundary"] == "character_reference_subject"
    assert excinfo.value.details["required_any_of"] == ["characters_present", "title"]
    assert excinfo.value.details["task_direction"] == "avatar"
    assert "characters_present" in str(excinfo.value)
    assert "title" in str(excinfo.value)


def test_image_prompt_composer_does_not_promote_description_into_visual_description():
    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    scene_data = composer._build_scene_data(
        {"scene_number": 11, "description": "仅有旧字段 description 的场景描述"},
        11,
    )

    assert scene_data["visual_description"] == ""


def test_image_prompt_composer_does_not_promote_nested_character_alias():
    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    scene_data = composer._build_scene_data(
        {
            "scene_number": 12,
            "content_elements": {"characters_present": ["韩立"]},
        },
        12,
        image_purpose="character_reference",
        task_direction="avatar",
    )

    assert scene_data["characters_present"] == []
