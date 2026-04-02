# Validation Ledger: PLAN-20260331-043

## Scope
- Validate the amendment that replaces duplicate-gate mainline handling with a planner-visible progress file/read-model.
- Preserve the already-valid `plan contract precedence` and `lease fresh-read + diagnostics` slices.
- Keep lifecycle gates here and keep design rationale in [PLAN-20260331-043-progress-read-model-note.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260331-043-progress-read-model-note.md).

## Acceptance Gates
### Review / amend gate
- [x] Current code and prior `043` closeout claims were reviewed against the current handoff, architecture docs, deferred constraints, and scene-contract freeze
- [x] Review confirmed `contract precedence` remains directionally valid
- [x] Review confirmed `lease fresh-read + diagnostics` remains directionally valid
- [x] Review confirmed duplicate gate is no longer the accepted mainline for repeated-scene work
- [x] Governance assets now present progress read-model as the accepted direction

### Stage 1 gate: architecture and SoT freeze
- [x] Review confirms this slice is framed as planner-input / context-editing behavior rather than MAS gate behavior
- [x] Review confirms this slice is no longer framed as an agent-level duplicate-gate initiative
- [x] Review confirms source mapping is frozen:
  - planned scenes from `scene_info_ref`
  - execution facts from WM structured receipts
  - `scene_outputs.*` remains artifact/reference only
- [x] Review confirms the progress file/read-model is derived, rebuildable, and non-authoritative

### Stage 2 gate: progress-file contract freeze
- [x] Review confirms the minimum progress file/read-model contract is explicit enough to implement
- [x] Review confirms planner consumption happens before planning and does not introduce a new phase
- [x] Review confirms no duplicate-gate compatibility layer is preserved as part of the accepted contract

### Stage 3 gate: implementation must validate before integrated closeout
- [x] A progress builder is implemented on the context assembly / plan-input path
- [x] The planner receives the progress file/read-model before tool-call planning
- [x] Planner input keeps explicit diagnostics when the progress projection degrades or cannot be rebuilt
- [x] The image-agent duplicate gate is removed from the active execution path
- [x] Static review confirms no second SoT, no planner-owned completion authority, and no new `scene_outputs.*` semantics were introduced

### Stage 4 gate: retained slices must still validate together before status promotion
- [x] `task_complete=true` with non-empty `tool_calls` still stops before ACT
- [x] `complete_node_attempt_sync` fresh-reads before lease validation/mutation
- [x] `fail_node_attempt_sync` fresh-reads before lease validation/mutation
- [x] Failure diagnostics still preserve an `execution_lease_snapshot` across cross-session heartbeat scenarios
- [x] Targeted tests pass for all retained slices plus the progress-read-model slice
- [x] Final review confirms the stream stays inside planner-input/context-editing semantics and does not become a new authority migration

## Automated Checks
- [x] ReAct contract-precedence regression was previously revalidated and remains accepted baseline evidence
- [x] Runtime lease fresh-read regression was previously revalidated and remains accepted baseline evidence
- [x] Runtime lease diagnostics preservation regression was previously revalidated and remains accepted baseline evidence
- [x] Progress-file determinism regression
- [x] Planner-consumption regression
- [x] Planner decision-level regression proves remaining scenes are preferred after prior successes
- [x] Duplicate-gate removal regression on the active image path

## Manual Checks
- [x] Architecture docs were reviewed before amending owner/layer conclusions
- [x] Review confirmed the compatibility-layer absorption risk is high enough that duplicate gate should not remain as a transitional semantic path
- [x] Review confirmed the supplement note contains the detailed design freeze and SoT rationale

## QC Rules
- This plan exists to correct drift inside the current mainline, not to reopen historical plan ownership.
- [PLAN-20260330-042.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260330-042.md) remains historical and must not be reused as the current execution entrypoint.
- The progress file/read-model remains a derived read-model only; it may guide the planner but may not silently become correctness authority.
- If the progress file/read-model cannot be rebuilt, the degradation must remain explicitly diagnosable instead of silently disappearing from planner input.
- `scene_info_ref` remains the authoritative media-input carrier only.
- `scene_outputs.*` must not gain new long-horizon authority semantics under the name of progress tracking.
- This slice is a planner-input correction, not a MAS authority migration.
- Review must confirm that `scene_info_ref` remains a persisted boundary input reference rather than a runtime completion surface.
- Review must confirm that planned membership is read from `scene_info_ref.scenes_to_generate[]` for the current media-generation slice.
- Review must confirm that execution success facts come from WM structured receipts / obs facts.
- Review must confirm that `scene_outputs.*` is not reused as planned-membership authority or completion authority.

## Evidence Log
- 2026-03-31T07:24:56Z validation ledger created together with `PLAN-20260331-043`
- 2026-03-31T09:26:32Z earlier amendment downgraded the duplicate slice back to design-freeze
- 2026-03-31T10:22:37Z image-side duplicate rewrite landed inside the then-current duplicate-gate envelope, but that direction is now superseded history
- 2026-03-31T12:49:17Z amendment changed the accepted mainline from duplicate gate to planner-visible progress file/read-model
- 2026-03-31T12:54:52Z validation ledger was slimmed so lifecycle gates stay here while design rationale moved to the supplement note
- 2026-03-31T14:54:21Z amendment added planner-input degradation diagnostics and decision-level planner regression as explicit validation requirements
- 2026-03-31T16:01:14Z focused validation passed for progress-read-model and retained slices: `test_plan_context_progress_read_model.py` (3 passed), `test_image_generator_progress_mainline.py` (2 passed), `test_orchestrator_image_context_boundary.py` (8 passed), `test_progress_snapshot.py` (1 passed), `test_react_contract_precedence_runtime.py` (1 passed), and retained `runtime_session_service` lease/diagnostics cases (4 passed)
