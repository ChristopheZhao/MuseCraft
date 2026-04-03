# Validation Ledger: PLAN-20260402-046

## Scope
- Validate owner-boundary restoration for the image mainline.
- Confirm helper/adapter/composer/tool layers no longer perform semantic owner work that belongs to scene contract or consistency assets.

## Acceptance Gates
### Review / boundary gate
- [x] Review confirms `image_purpose` and `frame_thesis` are excluded from shared scene contract authority and are not treated as authoritative runtime contract inputs in image mainline
- [x] Review confirms stable character traits are consumed from structured owner fields, not helper lexical guessing
- [x] Review confirms `image_generation_tool` is execution-only and no longer owns prompt-building compatibility paths

### Stage 1 gate: owner restoration
- [x] `memory_views` no longer invents image-mainline semantics during payload assembly
- [x] `image_prompt_composer_tool` no longer re-infers strategy/timepoint fields or writes guessed values back into scene data
- [x] `image_prompt_normalization.py` no longer rewrites semantic text in runtime mainline

### Stage 2 gate: runtime mainline cleanup
- [x] runtime image generation no longer falls back to helper-driven semantic character filtering
- [x] representative scene prompts still render coherently from accepted upstream fields after the `image_purpose` / `frame_thesis` owner decision closes
- [ ] missing owner fields surface as explicit diagnostics rather than silent helper repair

## Automated Checks
- [ ] updated targeted unit tests for image payload assembly / composer owner boundaries complete on the current patch in this environment
- [ ] updated targeted unit tests for runtime image tool behavior without semantic helper fallback complete on the current patch in this environment
- [ ] `backend/tests/unit/test_fc_policies_and_schema.py` completes in this environment after the exposure change
- [ ] `backend/tests/unit/test_react_contract_precedence_runtime.py` completes in this environment after SQLite test storage is available

## Manual Checks
- [x] inspect representative scene prompt before/after cleanup and confirm semantic source is traceable to explicit owner fields
- [x] inspect one action scene and one calm scene to confirm no helper lexical “best frame” selection remains

## QC Rules
- No compatibility shim for proven-wrong helper owner logic.
- No lexical or keyword rules that decide stable traits, frame choice, or scene strategy inside runtime helper/composer layers.
- No execution-tool prompt-building fallback that reinstates semantic owner drift.

## Evidence Log
- 2026-04-02T08:00:00Z validation ledger created together with PLAN-20260402-046 after subagent audit confirmed image-mainline owner drift.
- 2026-04-02T09:15:30Z Review verdict tightened: Stage 1 downstream cleanup is in place, but `image_purpose` / `frame_thesis` still do not have a single accepted upstream owner because `scene_contract` does not freeze them while the composer can still consume them when explicitly present.
- 2026-04-02T09:15:30Z Automated checks passed with `PYTHONPATH=. backend/.venv/bin/pytest` for `test_scene_contract.py`, `test_consistency_asset_contract_v2.py`, `test_image_prompt_normalization.py`, `test_image_generation_tool.py`, and `test_image_size_contract.py`.
- 2026-04-02T09:15:30Z `backend/tests/unit/test_fc_policies_and_schema.py` remained unresolved in this environment because schema initialization hung during the targeted run.
- 2026-04-02T09:15:30Z `backend/tests/unit/test_react_contract_precedence_runtime.py` remained unresolved in this environment because SQLite long-term memory storage could not open its database file before the assertion path ran.
- 2026-04-02T09:40:28Z Multi-agent review and local code analysis converged on the same decision: do not promote `image_purpose` / `frame_thesis` into `scene_contract`; keep `image_purpose` request-local and remove `frame_thesis` from accepted image-mainline inputs.
- 2026-04-02T09:40:28Z Direct local boundary check passed via `backend/.venv/bin/python -c`: composer ignores scene-payload `image_purpose/frame_thesis`, and prompt synthesis falls back to frozen scene fields (`owner_boundary_ok`).
- 2026-04-02T09:40:28Z Re-running narrowed pytest files (`test_scene_contract.py`, `test_image_prompt_normalization.py`) timed out at startup in this environment before producing assertion output, so current-patch pytest validation remains blocked by the workspace test harness state rather than a confirmed assertion failure.
- 2026-04-02T09:52:58Z Representative prompt checks passed via direct composer execution: calm-scene prompt stayed anchored on `opening_state`, action-scene prompt stayed anchored on `opening_state/content_focus`, and the action-scene consistency block retained `opening_anchor` without falling back to `end_state` (`calm_prompt_ok`, `action_prompt_ok`).
