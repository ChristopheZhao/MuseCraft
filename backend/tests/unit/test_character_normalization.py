"""Unit tests for character schema normalization utilities."""

from app.core.story_plan import (
    CharacterProfile,
    merge_character_bibles,
    normalize_character_bible,
    normalize_character_elements,
)


def _find_character(sanitized, canonical):
    return next((item for item in sanitized if item["canonical_name"] == canonical), None)


def test_normalize_character_elements_coerces_scalar_fields():
    raw_payload = [
        {
            "canonical_name": "zhao_yun",
            "display_name": "赵子龙",
            "aliases": "子龙;赵云",
            "type": "human",
            "abstract_traits": "英勇,冷静",
            "visual_identity": "银甲,长枪",
            "signature_outfit_or_props": ["银甲", "亮银枪"],
            "role": "主角",
            "style_preferences": ["史诗", "武侠"],
            "voice_profile": "厚重而坚定",
            "metadata": {"origin": "project_existing"},
        }
    ]

    sanitized, profiles = normalize_character_elements(raw_payload)

    assert len(sanitized) == 1
    hero = sanitized[0]
    assert hero["canonical_name"] == "zhao_yun"
    assert hero["aliases"] == ["子龙", "赵云", "赵子龙"]
    assert hero["visual_traits"]["identity_tags"] == ["银甲", "长枪"]
    assert hero["style_preferences"] == {"keywords": ["史诗", "武侠"]}
    assert hero["voice_profile"] == {"notes": "厚重而坚定"}
    assert hero["metadata"]["origin"] == "project_existing"

    profile = profiles["zhao_yun"]
    assert isinstance(profile, CharacterProfile)
    assert profile.display_name == "赵子龙"
    assert "银甲" in profile.visual_traits.get("identity_tags", [])


def test_normalize_character_elements_separates_conflicting_display_names():
    raw_payload = [
        {"canonical_name": "hero", "display_name": "Hero Prime"},
        {"canonical_name": "hero", "display_name": "Hero Variant", "aliases": []},
    ]

    sanitized, profiles = normalize_character_elements(raw_payload)

    assert len(sanitized) == 2
    primary = _find_character(sanitized, "hero")
    variant = next(item for item in sanitized if item["canonical_name"].startswith("hero-") and item["canonical_name"] != "hero")

    assert primary["display_name"] == "Hero Prime"
    assert "hero" in variant["aliases"]
    assert profiles[primary["canonical_name"]].display_name == "Hero Prime"
    assert profiles[variant["canonical_name"]].display_name == "Hero Variant"


def test_normalize_character_bible_is_consistent_with_elements():
    raw_payload = {
        "villain": {
            "display_name": "Villain",
            "visual_identity": ["黑甲"],
            "metadata": {"origin": "project_new"},
        }
    }

    sanitized, from_elements = normalize_character_elements(raw_payload)
    via_bible = normalize_character_bible(raw_payload)

    assert set(from_elements.keys()) == set(via_bible.keys())
    villain = sanitized[0]
    assert villain["metadata"]["origin"] == "project_new"
    merged = merge_character_bibles({}, from_elements)
    assert "villain" in merged
    assert merged["villain"].display_name == "Villain"
