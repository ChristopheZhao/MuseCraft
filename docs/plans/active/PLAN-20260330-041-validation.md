# Validation Ledger: PLAN-20260330-041

## Scope
- Validate only the post-`040` architecture hardening needed to remove duplicated still/reference contract hardcoding from the existing image mainline.
- Validate boundary consolidation, single-owner normalization, and anti-hardcoding compliance without expanding into new image workflows or upstream/video changes.

## Acceptance Gates
### Pre-implementation governance
- [x] New window reviewed the plan/ledger pair before coding
- [x] Review confirms the task remains a narrow image-mainline hardening plan rather than a new image architecture mainline
- [x] If owner/scope/test gates changed, amendment was made before implementation
- [x] Review confirms `image_purpose / task_direction` remains context input, not an agent-level decision table

### Boundary consolidation
- [x] Single-owner means one reusable raw-to-contract still/reference normalization implementation shared by prompt-root and consistency-lock consumers
- [x] Still/reference normalization has a clear single owner boundary
- [x] Tool and composer no longer keep duplicated still/reference rule centers
- [x] Composer no longer performs raw still/reference normalization through its own marker/replacement/character-compression rule set
- [x] No parallel image carrier/workflow/consistency mainline is introduced
- [x] No scene/script/video/runtime owner is pulled into this plan

### Anti-hardcoding closure
- [x] Structure-driven projection is preferred over duplicated content-level short-phrase replacements
- [x] Any remaining lexical guards are minimal, centralized, and explicitly justified
- [x] Character/reference compression is no longer independently reimplemented in multiple consumption sites
- [x] A shared helper only counts if both consumers actually call it; “shared helper plus residual local rule center” fails this gate
- [x] `040` functional behavior is preserved while removing duplicated hardcoding

## Automated Checks
- [x] Owner-layer unit test covers montage/high-risk opening/role-card normalization as a reusable contract surface
- [x] Regression test covers centralized still/reference normalization for `scene_opening_anchor`
- [x] Regression test covers centralized still/reference normalization for `character_reference`
- [x] Regression test proves montage/mixed scene still projects to one dominant still composition
- [x] Regression test proves prompt-root generation and consistency-lock generation consume the same normalization owner for the same contract behavior
- [x] Existing `040` regressions still pass after consolidation

## Manual Checks
- [x] Code review can point to one owner for still/reference normalization
- [x] Source review cannot find duplicated still/reference marker/replacement/compression rule centers in both tool and composer after consolidation
- [x] Review confirms no second image mainline or hidden policy center was introduced
- [x] `040` blocker note can be removed because duplicated hardcoding is no longer the residual architecture risk

## QC Rules
- This plan exists only because `040` is functionally complete but not yet architecture-clean.
- `040` must not be reopened as a wider implementation bucket; `041` owns only the still/reference de-hardcoding hardening.
- If the work expands into broader image architecture, stop and amend instead of silently growing scope.

## Evidence Log
- 2026-03-30T09:11:48Z validation ledger created together with `PLAN-20260330-041` to hold the post-implementation architecture gate that remains after `040`: remove duplicated still/reference hardcoding while preserving the same image mainline and the already-validated `040` behavior.
- 2026-03-30T09:27:32Z review-first amendment tightened the acceptance gate so `041` cannot pass with two disguised rule centers. Single-owner now explicitly means one reusable normalization surface shared by prompt-root and consistency-lock consumers, with source review expected to confirm the duplicated marker/replacement/compression rules are actually gone.
- 2026-03-30T10:10:02Z shared helper `backend/app/agents/tools/image_prompt_normalization.py` became the sole still/reference normalization owner, `image_generation_tool` and `image_prompt_composer_tool` now both consume that owner, and focused regressions passed: `uv run pytest tests/unit/test_image_prompt_normalization.py tests/unit/test_image_generation_tool.py tests/unit/test_consistency_asset_contract_v2.py tests/unit/test_prompt_safety_rewrite.py tests/unit/test_image_size_contract.py -q` (`28 passed`).
- 2026-03-30T10:10:02Z user approved closeout of `041`; the remaining centralized lexical guards are accepted as a separate non-blocking future TODO rather than an in-scope blocker.
