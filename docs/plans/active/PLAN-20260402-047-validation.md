# Validation Ledger: PLAN-20260402-047

## Scope
- Validate explicit diagnostics for missing accepted owner fields at the image composer boundary.
- Confirm the new diagnostics do not reopen `PLAN-20260402-046` owner decisions or reintroduce placeholder/heuristic repair.

## Acceptance Gates
### Review / boundary gate
- [x] Review confirms this plan stays local to `image_prompt_composer_tool` diagnostics and does not expand shared scene contract authority
- [x] Review confirms no placeholder text fallback (`单帧静态画面`, `角色`) remains as a silent substitute for missing owner fields

### Runtime diagnostic gate
- [x] non-reference scenes missing `opening_state`, `visual_description`, and `title` fail with explicit missing-owner diagnostics
- [x] character-reference scenes missing `characters_present` and `title` fail with explicit missing-owner diagnostics
- [x] explicit caller-owned fallback, if retained, does not suppress the missing-owner reason
- [x] representative valid prompts still compose normally from accepted upstream fields

## Automated Checks
- [x] targeted unit tests for missing non-reference root fields pass on the current patch
- [x] targeted unit tests for missing character-reference subject fields pass on the current patch
- [x] existing image composer owner-boundary tests remain green on the current patch

## Manual Checks
- [x] inspect one non-reference missing-field failure and confirm the diagnostic names the accepted owner fields
- [x] inspect one character-reference missing-field failure and confirm the diagnostic names the accepted owner fields
- [x] inspect one valid scene prompt and confirm diagnostics hardening does not change normal output unexpectedly

## QC Rules
- No helper-side repair for missing owner fields.
- No generic placeholder text used to hide missing contract inputs.
- No widening of `scene_contract` or reuse of retired `image_purpose` / `frame_thesis` semantics.

## Evidence Log
- 2026-04-02T10:00:59Z validation ledger created for follow-on diagnostics plan after `PLAN-20260402-046` closed with automation deferred as non-blocking.
- 2026-04-02T10:02:40Z plan governance moved to `in_progress`; scope remained narrow to composer-boundary diagnostics and explicitly excluded scene-contract expansion, helper cleanup, and workspace-wide test-harness stabilization.
- 2026-04-03T09:06:00Z review confirmed `047` remains scoped to `image_prompt_composer_tool` diagnostics only; the fix removed placeholder fallbacks and the remaining `description` / `content_elements.characters_present` compatibility leaks instead of widening owner authority.
- 2026-04-03T09:06:00Z isolated unit-harness verification passed with 11 targeted tests: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest --confcutdir=tests/unit -o addopts='' -o required_plugins='' ... -q`; direct local verification also confirmed explicit diagnostics and valid-scene non-regression.
