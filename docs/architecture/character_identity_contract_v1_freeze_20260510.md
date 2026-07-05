# Character Identity Contract v1 Freeze

Date: `2026-05-10`
Status: `design_only for PLAN-20260510-065 P0-B`

## 1. Goal

Character identity must be normalized at the MAS content contract boundary before
prompt assets and quality scoring consume it. The fix is not a prompt-side patch:
the same structured identity contract must be visible through `scene_info_ref`,
`consistency_tool`, prompt composers, and quality checker diagnostics.

## 2. Carrier and Owner

- carrier: existing `scene_info_payload` persisted by `scene_info_ref`
- owner: MAS content contract and context projection
- source inputs:
  - `concept_plan.content_elements.characters`
  - role analysis output
  - script stage `character_constraints_struct`
- authoritative additions:
  - `scene_info_payload.character_identity_bible`
  - `scene_info_payload.scene_character_locks[]`
  - `scene_info_payload.quality_expectations.role_continuity`
- compatibility fields:
  - `concept_plan.roles`
  - `scenes_to_generate[*].characters_present`
  - `scenes_to_generate[*].character_descriptions`
- compatibility rule: legacy fields may be read as evidence, but must be marked
  `source=legacy_text` and must not become the identity authority.

## 3. `character_identity_bible`

Workflow-level role identity library.

Required fields:
- `contract_version`
- `characters[]`
- `characters[].canonical_id`
- `characters[].display_name`
- `characters[].stable_anchors`

Character anchors:
- `visual_identity`
- `signature_outfit_or_props`
- `personality_identity`
- `identity_tags`
- `reference_assets`
- `negative_drift_notes`

Allowed variants are required for time jumps and scene-specific state changes:
- `variant_id`
- `age_stage`
- `applies_to_scenes`
- `visual_overrides`
- `required_anchors`
- `allowed_changes`
- `forbidden_drift`

Example intent:
- `child` may move from `young` to `teen` to `adult`
- `mother` may move from `adult` to `elderly`
- stable anchors such as apron, warm smile, suitcase, phone, or relationship role
  remain available without forcing all scenes to show the same age or outfit.

## 4. `scene_character_locks`

Scene-level cast projection.

Required fields:
- `scene_number`
- `cast[]`
- `cast[].canonical_id`
- `cast[].variant_ref`
- `cast[].required_anchors`

Scene lock fields:
- `display_name`
- `age_stage`
- `scene_specific_state`
- `allowed_changes`
- `forbidden_drift`
- `source_fields`
- `source_confidence`
- `diagnostics`

The scene lock is a compact projection. It should reference the bible and include
only scene-relevant anchors. It must not inject a full character biography into
every scene.

## 5. Prompt Asset Boundary

`consistency_tool.get_prompt_assets` should expose structured identity fields:
- `characters.identity_bible`
- `characters.scene_locks`
- `characters.global_lock.stable_anchors`
- `characters.allowed_variants`
- `characters.diagnostics`

If only legacy text exists, diagnostics must state:
- `source=legacy_text`
- `structured_identity_missing=true`
- `fallback_reason`

Prompt composers consume those fields after normalization. They should not infer
canonical identity from ad hoc regex, provider names, or localized display text.

## 6. Quality Boundary

Quality checker must include role continuity in its scoring contract:
- `role_continuity_score`
- `identity_drift_findings`
- `fallback_reason`
- `score_cap_when_failed`
- `score_cap_when_contract_missing`
- `missing_contract_status=needs_human_review`

If role continuity fails or cannot be evaluated because the contract is missing,
the result must not be graded `Excellent`.

## 7. Context Budget Strategy

Budget policy is configuration-owned:
- `backend/config/mas/context_policies.yaml#CHARACTER_IDENTITY_LOCKS`

The policy should cap:
- number of workflow characters projected
- anchors per character
- scene-specific lock text
- reference assets surfaced to tools

Hard-coded prompt composer thresholds are not the source of truth for this
contract.

## 8. Negative Cases

- requiring the same outfit and apparent age across a multi-year story
- treating `characters_present=["妈妈", "孩子"]` as sufficient identity lock
- reading only `concept_plan.roles` when `content_elements.characters` has richer
  canonical facts
- silently giving an Excellent quality grade when role continuity is missing or
  visibly drifting
- adding a one-off prompt sentence instead of fixing normalization at the
  contract boundary

## 9. Code Anchors

- [character_identity_contract.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/character_identity_contract.py)
- [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py)
- [consistency_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/consistency_tool.py)
- [image_prompt_composer_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/image_prompt_composer_tool.py)
- [video_prompt_composer_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/video_prompt_composer_tool.py)
- [quality_checker.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/quality_checker.py)
