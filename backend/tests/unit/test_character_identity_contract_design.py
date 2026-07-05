from pathlib import Path
import json

import yaml

from app.services.character_identity_contract import (
    CHARACTER_IDENTITY_BUDGET_POLICY_REF,
    CHARACTER_IDENTITY_CONTRACT_DOC_REF,
    CHARACTER_IDENTITY_CONTRACT_VERSION,
    annotate_character_identity_contract_design,
    build_character_identity_contract_meta,
    build_character_identity_contract_schema,
    build_character_identity_owner_matrix,
    normalize_character_identity_contract,
)


def test_character_identity_contract_meta_preserves_scene_info_owner_boundary():
    meta = build_character_identity_contract_meta()
    owner = meta["owner_matrix"]

    assert meta["contract_version"] == CHARACTER_IDENTITY_CONTRACT_VERSION
    assert meta["status"] == "design_only"
    assert meta["carrier_evolution"] == "in_place_only"
    assert meta["budget_policy_ref"] == CHARACTER_IDENTITY_BUDGET_POLICY_REF
    assert meta["hardcoded_budget_forbidden"] is True
    assert meta["doc_ref"] == CHARACTER_IDENTITY_CONTRACT_DOC_REF

    assert owner["runtime_owner"] == "mas_content_contract"
    assert owner["persisted_reference"] == "scene_info_ref"
    assert owner["parallel_carrier_forbidden"] is True
    assert "concept_plan.content_elements.characters" in owner["source_inputs"]
    assert owner["legacy_read_fields"]["concept_plan.roles"] == "legacy_text_only"
    assert "consumer_prompt_patch_as_identity_authority" in owner["forbidden_surfaces"]
    assert "quality_checker" in owner["consumer_surfaces"]


def test_character_identity_contract_schema_models_allowed_variants_not_fixed_age():
    schema = build_character_identity_contract_schema()
    bible = schema["properties"]["character_identity_bible"]
    character_item = bible["properties"]["characters"]["items"]
    character_props = character_item["properties"]
    variant_props = character_props["allowed_variants"]["items"]["properties"]

    assert character_item["required"] == [
        "canonical_id",
        "display_name",
        "stable_anchors",
    ]
    assert {"visual_identity", "signature_outfit_or_props", "identity_tags"}.issubset(
        set(character_props["stable_anchors"]["properties"])
    )
    assert {
        "variant_id",
        "age_stage",
        "applies_to_scenes",
        "visual_overrides",
        "required_anchors",
        "allowed_changes",
        "forbidden_drift",
    }.issubset(set(variant_props))
    assert "same_age_required" not in variant_props
    assert "same_outfit_required" not in variant_props


def test_scene_character_locks_and_quality_expectations_are_explicit_contract_fields():
    schema = build_character_identity_contract_schema()
    assert schema["required"] == [
        "character_identity_bible",
        "scene_character_locks",
        "quality_expectations",
    ]

    scene_lock = schema["properties"]["scene_character_locks"]["items"]
    cast_props = scene_lock["properties"]["cast"]["items"]["properties"]
    quality_props = (
        schema["properties"]["quality_expectations"]["properties"]["role_continuity"][
            "properties"
        ]
    )

    assert scene_lock["required"] == ["scene_number", "cast"]
    assert {"canonical_id", "variant_ref", "required_anchors"}.issubset(set(cast_props))
    assert {"allowed_changes", "forbidden_drift", "source_fields"}.issubset(
        set(cast_props)
    )
    assert quality_props["score_field"]["const"] == "role_continuity_score"
    assert quality_props["findings_field"]["const"] == "identity_drift_findings"
    assert quality_props["fallback_reason_field"]["const"] == "fallback_reason"
    assert quality_props["score_cap_when_unverified"]["type"] == "integer"
    assert quality_props["missing_contract_status"]["const"] == "needs_human_review"


def test_character_identity_budget_strategy_is_config_owned():
    backend_root = Path(__file__).resolve().parents[2]
    policy_path = backend_root / "config" / "mas" / "context_policies.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))

    assert "CHARACTER_IDENTITY_LOCKS" in policy
    strategy = policy["CHARACTER_IDENTITY_LOCKS"]
    assert strategy["scope"] == {"workflow": "required", "scene": "required"}
    assert strategy["budget"]["max_characters"] == 8
    assert strategy["budget"]["max_anchors_per_character"] == 6
    assert strategy["budget"]["max_scene_lock_chars"] == 700
    assert strategy["budget"]["reference_assets"] == "capability_gated"


def test_annotate_character_identity_contract_design_adds_meta_only():
    payload = {"scene_info_payload": {"unused": True}, "scenes_to_generate": []}

    annotated = annotate_character_identity_contract_design(payload)

    assert annotated["scene_info_payload"] == {"unused": True}
    assert annotated["scenes_to_generate"] == []
    assert annotated["character_identity_contract_meta"]["status"] == "design_only"
    assert "character_identity_bible" not in annotated
    assert "scene_character_locks" not in annotated


def test_normalize_character_identity_contract_builds_task_1080_bible_and_scene_locks():
    backend_root = Path(__file__).resolve().parents[2]
    fixture = json.loads(
        (
            backend_root
            / "tests"
            / "fixtures"
            / "task_1080_character_identity_gap.json"
        ).read_text(encoding="utf-8")
    )

    normalized = normalize_character_identity_contract(fixture["image_context"])
    bible = normalized["character_identity_bible"]
    scene_locks = {
        item["scene_number"]: item for item in normalized["scene_character_locks"]
    }

    assert bible["source"] == "concept_plan.content_elements.characters"
    by_id = {item["canonical_id"]: item for item in bible["characters"]}
    assert set(by_id) == {"mother", "child"}
    assert by_id["mother"]["stable_anchors"]["visual_identity"] == [
        "暖棕色长发",
        "围裙",
        "柔和微笑",
    ]
    assert "雨伞" in by_id["mother"]["stable_anchors"]["signature_outfit_or_props"]
    assert [
        variant["age_stage"]
        for variant in by_id["child"]["allowed_variants"]
        if variant["age_stage"] != "default"
    ][:3] == ["幼年", "少年", "青年"]

    assert [cast["canonical_id"] for cast in scene_locks[1]["cast"]] == [
        "mother",
        "child",
    ]
    assert scene_locks[1]["cast"][1]["variant_ref"] == "stage_1"
    assert scene_locks[2]["cast"][1]["age_stage"] == "少年"
    assert scene_locks[6]["cast"][1]["age_stage"] == "青年"
    assert scene_locks[6]["cast"][0]["age_stage"] == "default"
    assert "围裙" in scene_locks[6]["cast"][0]["required_anchors"]
    assert normalized["quality_expectations"]["role_continuity"] == {
        "required": True,
        "score_field": "role_continuity_score",
        "findings_field": "identity_drift_findings",
        "fallback_reason_field": "fallback_reason",
        "score_cap_when_failed": 79,
        "score_cap_when_contract_missing": 69,
        "score_cap_when_unverified": 89,
        "missing_contract_status": "needs_human_review",
    }


def test_normalize_character_identity_contract_keeps_scene_cast_order_deterministic():
    payload = {
        "concept_plan": {
            "content_elements": {
                "characters": [
                    {
                        "canonical_id": "mother",
                        "display_name": "妈妈",
                        "visual_identity": ["围裙"],
                    },
                    {
                        "canonical_id": "child",
                        "display_name": "孩子",
                        "visual_identity": ["书包"],
                    },
                ]
            }
        },
        "scenes_to_generate": [
            {
                "scene_number": 1,
                "characters_present": ["孩子", "妈妈"],
                "character_descriptions": [],
            }
        ],
    }

    normalized = normalize_character_identity_contract(payload)

    assert [
        item["canonical_id"]
        for item in normalized["scene_character_locks"][0]["cast"]
    ] == ["mother", "child"]


def test_scene_character_state_binding_does_not_treat_object_mentions_as_owner():
    payload = {
        "concept_plan": {
            "content_elements": {
                "characters": [
                    {
                        "canonical_id": "daughter",
                        "display_name": "女儿",
                        "visual_identity": ["棕色长发", "温暖笑容"],
                        "signature_outfit_or_props": ["学生时期校服", "手机"],
                        "description": "年龄变化：童年→成年",
                    },
                    {
                        "canonical_id": "mother",
                        "display_name": "妈妈",
                        "visual_identity": ["短发或盘发", "围裙", "温暖眼神"],
                        "signature_outfit_or_props": ["雨伞", "热牛奶"],
                    },
                ]
            }
        },
        "scenes_to_generate": [
            {
                "scene_number": 2,
                "characters_present": ["女儿", "妈妈"],
                "character_descriptions": [
                    "撑着旧伞，伞面倾向女儿一侧，自己半边身子暴露在雨中，微笑低头看女儿。",
                    "在伞下安然无恙，穿着校服，仰头看着妈妈，表情安心。",
                    "女儿：原型：成长中的子女；棕色长发，温暖笑容。",
                    "妈妈：原型：守护者；短发或盘发，围裙，温暖眼神。",
                ],
            },
            {
                "scene_number": 3,
                "characters_present": ["女儿", "妈妈"],
                "character_descriptions": [
                    "穿着围裙，端着冒热气的牛奶杯，坐在一旁，眼神温柔地看着女儿。",
                    "穿着睡衣或校服，伏案学习，后来在台灯下睡着，表情安详。",
                    "女儿：原型：成长中的子女；棕色长发，温暖笑容。",
                    "妈妈：原型：守护者；短发或盘发，围裙，温暖眼神。",
                ],
            },
        ],
    }

    normalized = normalize_character_identity_contract(payload)
    locks = {
        item["scene_number"]: {
            cast["canonical_id"]: cast for cast in item["cast"]
        }
        for item in normalized["scene_character_locks"]
    }

    scene_2_daughter_state = "；".join(locks[2]["daughter"]["scene_specific_state"])
    scene_2_mother_state = "；".join(locks[2]["mother"]["scene_specific_state"])
    scene_3_daughter_state = "；".join(locks[3]["daughter"]["scene_specific_state"])
    scene_3_mother_state = "；".join(locks[3]["mother"]["scene_specific_state"])

    assert "撑着旧伞" not in scene_2_daughter_state
    assert "在伞下安然无恙" not in scene_2_mother_state
    assert "穿着围裙，端着冒热气的牛奶杯" in scene_3_mother_state
    assert "穿着围裙，端着冒热气的牛奶杯" not in scene_3_daughter_state
    assert "穿着睡衣或校服" not in scene_3_mother_state
