# Validation Ledger: PLAN-20260402-048

## Scope
- Validate root-cause repair for the `video_generator` failure chain:
  - execution binding no longer depends on LLM-facing `workflow_state_id`
  - helper success no longer pollutes delivery progress
  - completion no longer succeeds without accepted scene-video delivery facts

## Acceptance Gates
### Architecture / boundary gate
- [x] Review confirms `workflow_state_id` is treated as execution context, not planner-facing business input
- [x] Review confirms `execution contract` no longer acts as planner-visible semantic input for `video_generator`
- [x] Review confirms completion consumes delivery acceptance rather than raw helper/tool success
- [x] Review confirms progress projection includes provenance and remains non-authoritative

### Runtime behavior gate
- [ ] failing `video_generator` path no longer dies because FC omitted `workflow_state_id`
- [x] helper-only `build_prompt` rounds do not advance delivery completion
- [x] `task_complete=true` without delivery acceptance no longer finalizes success
- [x] successful accepted scene-video output advances progress and allows downstream compose input to assemble normally

## Automated Checks
- [x] targeted unit tests for execution-context binding pass
- [x] targeted unit tests for progress-read-model source tightening pass
- [x] targeted unit tests for completion gating against delivery acceptance pass
- [x] existing `video_generator` / `video_composer` boundary tests remain green on the patch

## Manual Checks
- [ ] inspect one successful video-generation FC call and confirm no planner-facing `workflow_state_id` is required
- [ ] inspect one helper-only round and confirm progress does not mark the scene delivered
- [ ] inspect one failing delivery path and confirm the diagnostic is emitted at the correct boundary layer
- [ ] inspect one full repaired run and confirm downstream compose input contains accepted `scene_videos`

## QC Rules
- No reintroduction of LLM-facing execution bookkeeping as a required business argument.
- No helper-success compatibility shim promoted into delivery truth.
- No widening into `PLAN-20260402-047` image-composer scope.
- No use of queue/worker/broker state as delivery progress authority.

## Evidence Log
- 2026-04-02T13:02:50Z plan created for `video_generator` execution-boundary and progress-authority repair.
- 2026-04-02T13:04:21Z validation ledger created after confirming `PLAN-20260402-047` has no direct implementation dependency on this repair stream.
- 2026-04-02T22:14:00Z updated `backend/tests/unit/test_plan_context_progress_read_model.py` to accepted-delivery semantics; `uv run pytest -q tests/unit/test_plan_context_progress_read_model.py` passed (`3 passed`).
- 2026-04-02T22:15:00Z targeted `048` validation slice passed: `uv run pytest -q tests/unit/test_plan_context_progress_read_model.py tests/unit/test_video_generator_audio_route_injection.py tests/unit/test_video_generator_progress_boundary.py tests/unit/test_react_contract_precedence_runtime.py tests/unit/test_video_composer_execution_boundary.py` (`25 passed`).
