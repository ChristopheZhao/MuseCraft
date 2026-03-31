import asyncio

from app.agents.tools import image_prompt_normalization as norm_module
from app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool
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


def test_compress_character_description_strips_role_card_prose():
    compressed = norm_module.compress_character_description(
        "韩立：原型：成长者；物种：人类；从凡人蜕变的修仙者，坚毅沉稳，成长型主角，手持法器，神秘气质；青灰色长袍，水墨线条勾勒，动态光影效果；青竹剑，储物袋；主角，展现从平凡到超凡的成长历程",
        segment_max_len=64,
        fallback_max_len=80,
    )

    assert "成长历程" not in compressed
    assert "青灰色长袍" in compressed
    assert "青竹剑" in compressed


def test_prompt_root_and_consistency_block_share_normalization_owner(monkeypatch):
    calls = []
    original = norm_module.normalize_still_text

    def spy(value, *, max_len=None):
        calls.append((str(value or ""), max_len))
        return original(value, max_len=max_len)

    monkeypatch.setattr(norm_module, "normalize_still_text", spy)

    image_tool = ImageGenerationTool()
    composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())

    before_prompt = len(calls)
    prompt = asyncio.run(
        image_tool._create_image_prompt_from_scene(
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
            "动态水墨奇幻",
            {"style_name": "动态水墨奇幻", "visual_approach": "动画"},
        )
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

    assert after_prompt > before_prompt
    assert after_block > after_prompt
    assert "韩立特写" in prompt
    assert "标题" not in block
