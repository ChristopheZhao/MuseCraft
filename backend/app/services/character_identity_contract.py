"""
Helpers for the quick-flow character identity contract.

This module owns contract-boundary normalization only. It does not patch prompt
composition. The carrier remains the existing scene_info_payload / scene_info_ref.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


CHARACTER_IDENTITY_CONTRACT_VERSION = "v1"
CHARACTER_IDENTITY_CONTRACT_DOC_REF = (
    "docs/architecture/character_identity_contract_v1_freeze_20260510.md"
)
CHARACTER_IDENTITY_BUDGET_POLICY_REF = (
    "backend/config/mas/context_policies.yaml#CHARACTER_IDENTITY_LOCKS"
)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def build_character_identity_owner_matrix() -> Dict[str, Any]:
    """Return the ownership boundary for character identity semantics."""
    return {
        "runtime_owner": "mas_content_contract",
        "authoritative_carrier_path": (
            "scene_info_payload.character_identity_bible + "
            "scene_info_payload.scene_character_locks[]"
        ),
        "persisted_reference": "scene_info_ref",
        "carrier_evolution": "in_place_only",
        "parallel_carrier_forbidden": True,
        "source_inputs": [
            "concept_plan.content_elements.characters",
            "role_analysis_tool.output",
            "scene_scripts[*].character_constraints_struct",
        ],
        "legacy_read_fields": {
            "concept_plan.roles": "legacy_text_only",
            "scenes_to_generate[*].characters_present": "legacy_scene_cast",
            "scenes_to_generate[*].character_descriptions": "legacy_scene_descriptions",
        },
        "consumer_surfaces": [
            "ContextContractAssembler.scene_info_payload",
            "consistency_tool.get_prompt_assets",
            "image_prompt_composer",
            "video_prompt_composer",
            "quality_checker",
        ],
        "forbidden_surfaces": [
            "consumer_prompt_patch_as_identity_authority",
            "provider_specific_character_branching",
            "queue_or_worker_runtime_state",
            "frontend_inferred_identity_state",
            "working_memory_primary_slot_as_authority",
        ],
    }


def build_character_identity_contract_meta() -> Dict[str, Any]:
    """Return metadata that can annotate the existing scene_info_payload."""
    return {
        "contract_version": CHARACTER_IDENTITY_CONTRACT_VERSION,
        "status": "design_only",
        "semantic_unit": "workflow_character_identity",
        "carrier_evolution": "in_place_only",
        "character_identity_bible_path": "scene_info_payload.character_identity_bible",
        "scene_character_locks_path": "scene_info_payload.scene_character_locks[]",
        "quality_expectations_path": "scene_info_payload.quality_expectations.role_continuity",
        "budget_policy_ref": CHARACTER_IDENTITY_BUDGET_POLICY_REF,
        "hardcoded_budget_forbidden": True,
        "owner_matrix": build_character_identity_owner_matrix(),
        "doc_ref": CHARACTER_IDENTITY_CONTRACT_DOC_REF,
    }


def build_character_identity_contract_schema() -> Dict[str, Any]:
    """Return the structural contract for identity bible and per-scene locks."""
    character_item = {
        "type": "object",
        "required": ["canonical_id", "display_name", "stable_anchors"],
        "properties": {
            "canonical_id": {"type": "string"},
            "display_name": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "source": {"type": "string"},
            "stable_anchors": {
                "type": "object",
                "properties": {
                    "visual_identity": {"type": "array", "items": {"type": "string"}},
                    "signature_outfit_or_props": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "personality_identity": {"type": "array", "items": {"type": "string"}},
                    "identity_tags": {"type": "array", "items": {"type": "string"}},
                },
            },
            "allowed_variants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["variant_id", "age_stage"],
                    "properties": {
                        "variant_id": {"type": "string"},
                        "age_stage": {"type": "string"},
                        "applies_to_scenes": {
                            "type": "array",
                            "items": {"type": ["integer", "string"]},
                        },
                        "visual_overrides": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "required_anchors": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "allowed_changes": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "forbidden_drift": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "negative_drift_notes": {"type": "array", "items": {"type": "string"}},
            "reference_assets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "asset_type": {"type": "string"},
                        "uri": {"type": "string"},
                        "capability_required": {"type": "string"},
                    },
                },
            },
        },
    }

    scene_lock_item = {
        "type": "object",
        "required": ["scene_number", "cast"],
        "properties": {
            "scene_number": {"type": ["integer", "string"]},
            "cast": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["canonical_id", "variant_ref", "required_anchors"],
                    "properties": {
                        "canonical_id": {"type": "string"},
                        "display_name": {"type": "string"},
                        "variant_ref": {"type": "string"},
                        "age_stage": {"type": "string"},
                        "required_anchors": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "scene_specific_state": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "allowed_changes": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "forbidden_drift": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "source_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "source_confidence": {"type": "string"},
                    },
                },
            },
            "diagnostics": {"type": "array", "items": {"type": "object"}},
        },
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "CharacterIdentityContract",
        "type": "object",
        "required": [
            "character_identity_bible",
            "scene_character_locks",
            "quality_expectations",
        ],
        "properties": {
            "character_identity_bible": {
                "type": "object",
                "required": ["contract_version", "characters"],
                "properties": {
                    "contract_version": {"const": CHARACTER_IDENTITY_CONTRACT_VERSION},
                    "source": {"type": "string"},
                    "characters": {"type": "array", "items": character_item},
                    "diagnostics": {"type": "array", "items": {"type": "object"}},
                },
            },
            "scene_character_locks": {"type": "array", "items": scene_lock_item},
            "quality_expectations": {
                "type": "object",
                "properties": {
                    "role_continuity": {
                        "type": "object",
                        "required": [
                            "required",
                            "score_field",
                            "findings_field",
                            "fallback_reason_field",
                        ],
                        "properties": {
                            "required": {"type": "boolean"},
                            "score_field": {"const": "role_continuity_score"},
                            "findings_field": {"const": "identity_drift_findings"},
                            "fallback_reason_field": {"const": "fallback_reason"},
                            "score_cap_when_failed": {"type": "integer"},
                            "score_cap_when_contract_missing": {"type": "integer"},
                            "score_cap_when_unverified": {"type": "integer"},
                            "missing_contract_status": {"const": "needs_human_review"},
                        },
                    },
                },
            },
            "diagnostics": {"type": "array", "items": {"type": "object"}},
        },
    }


def build_default_role_continuity_expectations(*, required: bool = True) -> Dict[str, Any]:
    """Return the quality-check contract fields for role continuity."""
    return {
        "required": bool(required),
        "score_field": "role_continuity_score",
        "findings_field": "identity_drift_findings",
        "fallback_reason_field": "fallback_reason",
        "score_cap_when_failed": 79,
        "score_cap_when_contract_missing": 69,
        "score_cap_when_unverified": 89,
        "missing_contract_status": "needs_human_review",
    }


def _dedupe_texts(values: Any, *, max_items: Optional[int] = None) -> List[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    result: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if max_items is not None and len(result) >= max_items:
            break
    return result


def _load_budget() -> Dict[str, Any]:
    default = {
        "max_characters": 8,
        "max_anchors_per_character": 6,
        "max_scene_lock_chars": 700,
        "reference_assets": "capability_gated",
    }
    policy_path = _PROJECT_ROOT / "backend" / "config" / "mas" / "context_policies.yaml"
    try:
        import yaml

        payload = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        strategy = payload.get("CHARACTER_IDENTITY_LOCKS") or {}
        budget = strategy.get("budget") or {}
        if isinstance(budget, dict):
            default.update({key: value for key, value in budget.items() if value is not None})
    except Exception:
        pass
    return default


def _clip_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _split_stage_sequence(text: Any) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    candidate = raw
    if "：" in candidate:
        head, tail = candidate.split("：", 1)
        if "年龄" in head or "变化" in head:
            candidate = tail
    elif ":" in candidate:
        head, tail = candidate.split(":", 1)
        if "age" in head.lower() or "variant" in head.lower() or "变化" in head:
            candidate = tail

    if "→" in candidate or "->" in candidate:
        normalized = candidate.replace("->", "→")
        return _dedupe_texts([part.strip() for part in normalized.split("→")])

    if "从" in candidate and "到" in candidate:
        after_from = candidate.split("从", 1)[1]
        first, rest = after_from.split("到", 1)
        second = rest
        for marker in ("的", "，", "。", "；", ";", ",", "."):
            if marker in second:
                second = second.split(marker, 1)[0]
        return _dedupe_texts([first.strip(), second.strip()])

    return []


def _normalize_reference_assets(value: Any) -> List[Dict[str, Any]]:
    items = value.get("items") if isinstance(value, dict) else value
    if not isinstance(items, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append({"asset_type": "reference", "uri": text})
            continue
        if not isinstance(item, dict):
            continue
        uri = str(item.get("uri") or item.get("url") or item.get("path") or "").strip()
        if not uri:
            continue
        normalized.append(
            {
                "asset_type": str(item.get("asset_type") or item.get("type") or "reference").strip(),
                "uri": uri,
                "capability_required": str(item.get("capability_required") or "").strip(),
            }
        )
    return normalized


def _normalize_allowed_variants(character: Dict[str, Any]) -> List[Dict[str, Any]]:
    explicit = character.get("allowed_variants")
    variants: List[Dict[str, Any]] = []
    if isinstance(explicit, list):
        for index, item in enumerate(explicit, start=1):
            if not isinstance(item, dict):
                continue
            age_stage = str(item.get("age_stage") or item.get("stage") or "").strip()
            if not age_stage:
                continue
            variants.append(
                {
                    "variant_id": str(item.get("variant_id") or f"stage_{index}").strip(),
                    "age_stage": age_stage,
                    "applies_to_scenes": _dedupe_texts(item.get("applies_to_scenes") or []),
                    "visual_overrides": _dedupe_texts(item.get("visual_overrides") or []),
                    "required_anchors": _dedupe_texts(item.get("required_anchors") or []),
                    "allowed_changes": _dedupe_texts(item.get("allowed_changes") or []),
                    "forbidden_drift": _dedupe_texts(item.get("forbidden_drift") or []),
                }
            )

    if variants:
        return variants

    stage_values: List[str] = []
    for source in (
        character.get("visual_identity"),
        character.get("description"),
        character.get("backstory"),
    ):
        if isinstance(source, list):
            for text in source:
                stage_values.extend(_split_stage_sequence(text))
        else:
            stage_values.extend(_split_stage_sequence(source))
    stage_values = _dedupe_texts(stage_values)

    if stage_values:
        variants.append(
            {
                "variant_id": "default",
                "age_stage": "default",
                "applies_to_scenes": [],
                "visual_overrides": [],
                "required_anchors": [],
                "allowed_changes": [],
                "forbidden_drift": [],
            }
        )

    for index, stage in enumerate(stage_values, start=1):
        variants.append(
            {
                "variant_id": f"stage_{index}",
                "age_stage": stage,
                "applies_to_scenes": [],
                "visual_overrides": [],
                "required_anchors": [],
                "allowed_changes": [f"允许呈现{stage}阶段外观"],
                "forbidden_drift": [],
            }
        )

    if not variants:
        variants.append(
            {
                "variant_id": "default",
                "age_stage": "default",
                "applies_to_scenes": [],
                "visual_overrides": [],
                "required_anchors": [],
                "allowed_changes": [],
                "forbidden_drift": [],
            }
        )
    return variants


def _normalize_character_item(
    raw: Dict[str, Any],
    *,
    source: str,
    max_anchors: int,
) -> Dict[str, Any]:
    canonical_id = str(
        raw.get("canonical_id")
        or raw.get("id")
        or raw.get("canonical_name")
        or raw.get("name")
        or raw.get("display_name")
        or ""
    ).strip()
    display_name = str(raw.get("display_name") or raw.get("name") or raw.get("canonical_name") or canonical_id).strip()
    aliases = _dedupe_texts(
        [
            display_name,
            raw.get("canonical_name"),
            raw.get("name"),
            canonical_id,
            *_dedupe_texts(raw.get("aliases") or []),
        ]
    )
    visual_traits = raw.get("visual_traits") if isinstance(raw.get("visual_traits"), dict) else {}
    stable_anchors = {
        "visual_identity": _dedupe_texts(raw.get("visual_identity") or [], max_items=max_anchors),
        "signature_outfit_or_props": _dedupe_texts(
            [
                *_dedupe_texts(raw.get("signature_outfit_or_props") or []),
                *_dedupe_texts(visual_traits.get("signature_props") or []),
            ],
            max_items=max_anchors,
        ),
        "personality_identity": _dedupe_texts(
            [
                *_dedupe_texts(raw.get("abstract_traits") or []),
                *_dedupe_texts(raw.get("personality_traits") or []),
            ],
            max_items=max_anchors,
        ),
        "identity_tags": _dedupe_texts(visual_traits.get("identity_tags") or [], max_items=max_anchors),
    }
    if not stable_anchors["identity_tags"]:
        stable_anchors["identity_tags"] = _dedupe_texts(
            [display_name, canonical_id],
            max_items=max_anchors,
        )
    return {
        "canonical_id": canonical_id,
        "display_name": display_name,
        "aliases": aliases,
        "source": source,
        "stable_anchors": stable_anchors,
        "allowed_variants": _normalize_allowed_variants(raw),
        "negative_drift_notes": _dedupe_texts(raw.get("negative_drift_notes") or []),
        "reference_assets": _normalize_reference_assets(raw.get("reference_assets") or []),
    }


def _extract_source_characters(concept_plan: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str, List[Dict[str, Any]]]:
    diagnostics: List[Dict[str, Any]] = []
    content_elements = concept_plan.get("content_elements") if isinstance(concept_plan, dict) else {}
    characters = content_elements.get("characters") if isinstance(content_elements, dict) else None
    if isinstance(characters, list) and characters:
        return [item for item in characters if isinstance(item, dict)], "concept_plan.content_elements.characters", diagnostics

    roles = concept_plan.get("roles") if isinstance(concept_plan, dict) else None
    if isinstance(roles, list) and roles:
        diagnostics.append(
            {
                "code": "legacy_roles_source",
                "source": "concept_plan.roles",
                "message": "Structured content_elements.characters missing; using legacy roles as low-confidence input.",
            }
        )
        return [item for item in roles if isinstance(item, dict)], "legacy_text", diagnostics

    diagnostics.append(
        {
            "code": "structured_identity_missing",
            "source": "concept_plan.content_elements.characters",
            "message": "No structured character source was available at the contract boundary.",
        }
    )
    return [], "missing", diagnostics


def _build_alias_index(characters: List[Dict[str, Any]]) -> Dict[str, str]:
    alias_index: Dict[str, str] = {}
    for character in characters:
        canonical_id = str(character.get("canonical_id") or "").strip()
        if not canonical_id:
            continue
        for alias in _dedupe_texts(character.get("aliases") or []):
            alias_index[alias] = canonical_id
    return alias_index


def _coerce_scene_number(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _scene_text(scene: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in (
        "title",
        "scene_thesis",
        "visual_description",
        "narrative_description",
        "opening_state",
        "end_state",
    ):
        text = str(scene.get(key) or "").strip()
        if text:
            parts.append(text)
    for desc in _dedupe_texts(scene.get("character_descriptions") or []):
        parts.append(desc)
    return "\n".join(parts)


def _resolve_scene_cast_ids(
    scene: Dict[str, Any],
    characters: List[Dict[str, Any]],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    diagnostics: List[Dict[str, Any]] = []
    alias_index = _build_alias_index(characters)
    ordered_ids: List[str] = []

    structured = scene.get("character_constraints_struct")
    if isinstance(structured, list) and structured:
        for item in structured:
            if not isinstance(item, dict):
                continue
            raw_id = str(
                item.get("canonical_id")
                or item.get("character_id")
                or item.get("name")
                or item.get("display_name")
                or ""
            ).strip()
            canonical_id = alias_index.get(raw_id, raw_id)
            if canonical_id and canonical_id not in ordered_ids:
                ordered_ids.append(canonical_id)
        if ordered_ids:
            return ordered_ids, diagnostics

    present = _dedupe_texts(scene.get("characters_present") or [])
    for raw_name in present:
        canonical_id = alias_index.get(raw_name)
        if canonical_id and canonical_id not in ordered_ids:
            ordered_ids.append(canonical_id)
        elif raw_name:
            diagnostics.append(
                {
                    "code": "legacy_cast_unmatched",
                    "source": "scenes_to_generate[].characters_present",
                    "value": raw_name,
                }
            )

    if ordered_ids:
        by_position = {character["canonical_id"]: index for index, character in enumerate(characters)}
        ordered_ids.sort(key=lambda item: by_position.get(item, 9999))
        return ordered_ids, diagnostics

    text = _scene_text(scene)
    for character in characters:
        canonical_id = str(character.get("canonical_id") or "").strip()
        if not canonical_id:
            continue
        aliases = _dedupe_texts(character.get("aliases") or [])
        if any(alias and alias in text for alias in aliases):
            ordered_ids.append(canonical_id)

    return ordered_ids, diagnostics


def _select_variant(character: Dict[str, Any], scene: Dict[str, Any]) -> Dict[str, Any]:
    variants = character.get("allowed_variants") if isinstance(character.get("allowed_variants"), list) else []
    if not variants:
        return {
            "variant_id": "default",
            "age_stage": "default",
            "required_anchors": [],
            "allowed_changes": [],
            "forbidden_drift": [],
        }

    structured = scene.get("character_constraints_struct")
    if isinstance(structured, list):
        canonical_id = str(character.get("canonical_id") or "").strip()
        for item in structured:
            if not isinstance(item, dict):
                continue
            if str(item.get("canonical_id") or item.get("character_id") or "").strip() != canonical_id:
                continue
            requested = str(item.get("variant_ref") or item.get("age_stage") or "").strip()
            if requested:
                for variant in variants:
                    if requested in {
                        str(variant.get("variant_id") or "").strip(),
                        str(variant.get("age_stage") or "").strip(),
                    }:
                        return variant

    focused_parts: List[str] = []
    for desc in _dedupe_texts(scene.get("character_descriptions") or []):
        if "随年龄变化" in desc or "原型：" in desc or "物种：" in desc:
            continue
        focused_parts.append(desc)
    for key in ("visual_description", "opening_state", "end_state"):
        text = str(scene.get(key) or "").strip()
        if text:
            focused_parts.append(text)

    for text in ("\n".join(focused_parts),):
        for variant in variants:
            stage = str(variant.get("age_stage") or "").strip()
            if stage and stage != "default" and stage in text:
                return variant
    return variants[0]


def _anchor_terms(character: Dict[str, Any]) -> List[str]:
    stable = character.get("stable_anchors") if isinstance(character.get("stable_anchors"), dict) else {}
    variants = character.get("allowed_variants") if isinstance(character.get("allowed_variants"), list) else []
    variant_terms: List[str] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        variant_terms.extend(
            [
                str(variant.get("age_stage") or "").strip(),
                *_dedupe_texts(variant.get("visual_overrides") or []),
                *_dedupe_texts(variant.get("required_anchors") or []),
            ]
        )
    return _dedupe_texts(
        [
            *_dedupe_texts(stable.get("visual_identity") or []),
            *_dedupe_texts(stable.get("signature_outfit_or_props") or []),
            *_dedupe_texts(stable.get("identity_tags") or []),
            *variant_terms,
        ]
    )


def _description_explicit_target_ids(
    desc: str,
    characters: List[Dict[str, Any]],
) -> List[str]:
    text = str(desc or "").strip()
    if not text:
        return []
    targets: List[str] = []
    delimiters = ("：", ":", "，", ",", "。", "、", " ")
    for candidate in characters:
        canonical_id = str(candidate.get("canonical_id") or "").strip()
        if not canonical_id:
            continue
        aliases = _dedupe_texts(candidate.get("aliases") or [])
        for alias in aliases:
            if not alias:
                continue
            if text == alias or any(text.startswith(f"{alias}{mark}") for mark in delimiters):
                if canonical_id not in targets:
                    targets.append(canonical_id)
                break
    return targets


def _unique_anchor_terms(
    character: Dict[str, Any],
    all_characters: List[Dict[str, Any]],
) -> List[str]:
    canonical_id = str(character.get("canonical_id") or "").strip()
    own_terms = _anchor_terms(character)
    other_terms = set()
    alias_terms = set()
    for candidate in all_characters:
        alias_terms.update(_dedupe_texts(candidate.get("aliases") or []))
        if str(candidate.get("canonical_id") or "").strip() == canonical_id:
            continue
        other_terms.update(_anchor_terms(candidate))
    return [
        term
        for term in own_terms
        if term and term not in other_terms and term not in alias_terms
    ]


def _scene_specific_state(
    character: Dict[str, Any],
    scene: Dict[str, Any],
    *,
    all_characters: List[Dict[str, Any]],
    max_chars: int,
) -> List[str]:
    canonical_id = str(character.get("canonical_id") or "").strip()
    aliases = _dedupe_texts(character.get("aliases") or [])
    unique_anchors = _unique_anchor_terms(character, all_characters)
    descriptions = _dedupe_texts(scene.get("character_descriptions") or [])
    selected: List[str] = []
    for desc in descriptions:
        explicit_targets = _description_explicit_target_ids(desc, all_characters)
        if explicit_targets:
            if canonical_id in explicit_targets:
                selected.append(desc)
            continue

        if any(alias and str(desc).strip() == alias for alias in aliases):
            selected.append(desc)
            continue
        if any(anchor and anchor in desc for anchor in unique_anchors):
            selected.append(desc)
    return [_clip_text(item, max_chars) for item in _dedupe_texts(selected, max_items=3)]


def _build_scene_character_locks(
    *,
    scenes: List[Dict[str, Any]],
    characters: List[Dict[str, Any]],
    max_anchors: int,
    max_scene_lock_chars: int,
) -> List[Dict[str, Any]]:
    by_id = {str(item.get("canonical_id") or ""): item for item in characters}
    locks: List[Dict[str, Any]] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_number = _coerce_scene_number(scene.get("scene_number"))
        if scene_number is None:
            continue
        cast_ids, diagnostics = _resolve_scene_cast_ids(scene, characters)
        cast: List[Dict[str, Any]] = []
        for canonical_id in cast_ids:
            character = by_id.get(canonical_id)
            if not character:
                continue
            variant = _select_variant(character, scene)
            stable = character.get("stable_anchors") if isinstance(character.get("stable_anchors"), dict) else {}
            required_anchors = _dedupe_texts(
                [
                    *_dedupe_texts(variant.get("required_anchors") or []),
                    *_dedupe_texts(stable.get("visual_identity") or []),
                    *_dedupe_texts(stable.get("signature_outfit_or_props") or []),
                    *_dedupe_texts(stable.get("identity_tags") or []),
                ],
                max_items=max_anchors,
            )
            scene_state = _scene_specific_state(
                character,
                scene,
                all_characters=characters,
                max_chars=max_scene_lock_chars,
            )
            source_fields = ["character_identity_bible"]
            if scene.get("character_constraints_struct"):
                source_fields.append("scenes_to_generate[].character_constraints_struct")
            if scene.get("characters_present"):
                source_fields.append("scenes_to_generate[].characters_present")
            if scene.get("character_descriptions"):
                source_fields.append("scenes_to_generate[].character_descriptions")
            cast.append(
                {
                    "canonical_id": canonical_id,
                    "display_name": character.get("display_name") or canonical_id,
                    "variant_ref": variant.get("variant_id") or "default",
                    "age_stage": variant.get("age_stage") or "default",
                    "required_anchors": required_anchors,
                    "scene_specific_state": scene_state,
                    "allowed_changes": _dedupe_texts(
                        [
                            *_dedupe_texts(variant.get("allowed_changes") or []),
                            *scene_state[:1],
                        ],
                        max_items=4,
                    ),
                    "forbidden_drift": _dedupe_texts(
                        [
                            *_dedupe_texts(character.get("negative_drift_notes") or []),
                            *_dedupe_texts(variant.get("forbidden_drift") or []),
                        ],
                        max_items=4,
                    ),
                    "source_fields": source_fields,
                    "source_confidence": "structured",
                }
            )
        locks.append(
            {
                "scene_number": scene_number,
                "cast": cast,
                "diagnostics": diagnostics,
            }
        )
    return locks


def normalize_character_identity_contract(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Add workflow and scene character identity contracts to scene_info_payload.

    The normalization source order is contract-first:
    `concept_plan.content_elements.characters` is authoritative when present.
    Legacy role and scene text fields are diagnostic inputs, not the identity
    authority.
    """
    merged = annotate_character_identity_contract_design(payload)
    concept_plan = merged.get("concept_plan") if isinstance(merged.get("concept_plan"), dict) else {}
    budget = _load_budget()
    max_characters = int(budget.get("max_characters") or 8)
    max_anchors = int(budget.get("max_anchors_per_character") or 6)
    max_scene_lock_chars = int(budget.get("max_scene_lock_chars") or 700)

    source_characters, source, diagnostics = _extract_source_characters(concept_plan)
    characters = [
        _normalize_character_item(item, source=source, max_anchors=max_anchors)
        for item in source_characters[:max_characters]
        if isinstance(item, dict)
    ]
    characters = [item for item in characters if item.get("canonical_id")]
    if source_characters and len(source_characters) > len(characters):
        diagnostics.append(
            {
                "code": "character_budget_truncated",
                "source": source,
                "max_characters": max_characters,
            }
        )

    bible = {
        "contract_version": CHARACTER_IDENTITY_CONTRACT_VERSION,
        "source": source,
        "characters": characters,
        "diagnostics": diagnostics,
    }

    scenes = merged.get("scenes_to_generate") if isinstance(merged.get("scenes_to_generate"), list) else []
    scene_locks = _build_scene_character_locks(
        scenes=scenes,
        characters=characters,
        max_anchors=max_anchors,
        max_scene_lock_chars=max_scene_lock_chars,
    )

    quality_expectations = dict(merged.get("quality_expectations") or {})
    quality_expectations["role_continuity"] = build_default_role_continuity_expectations(
        required=bool(characters),
    )

    contract_diagnostics = list(diagnostics)
    if not characters:
        contract_diagnostics.append(
            {
                "code": "role_continuity_unverifiable",
                "fallback_reason": "character_identity_bible_missing",
                "status": "needs_human_review",
            }
        )
    elif any(lock.get("diagnostics") for lock in scene_locks):
        contract_diagnostics.append(
            {
                "code": "legacy_scene_cast_diagnostics",
                "source": "scenes_to_generate",
            }
        )

    merged["character_identity_bible"] = bible
    merged["scene_character_locks"] = scene_locks
    merged["quality_expectations"] = quality_expectations
    merged["character_identity_diagnostics"] = contract_diagnostics
    return merged


def annotate_character_identity_contract_design(
    payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Annotate scene_info_payload with design metadata only."""
    merged = dict(payload or {})
    merged["character_identity_contract_meta"] = build_character_identity_contract_meta()
    return merged


__all__ = [
    "CHARACTER_IDENTITY_BUDGET_POLICY_REF",
    "CHARACTER_IDENTITY_CONTRACT_DOC_REF",
    "CHARACTER_IDENTITY_CONTRACT_VERSION",
    "annotate_character_identity_contract_design",
    "build_default_role_continuity_expectations",
    "build_character_identity_contract_meta",
    "build_character_identity_contract_schema",
    "build_character_identity_owner_matrix",
    "normalize_character_identity_contract",
]
