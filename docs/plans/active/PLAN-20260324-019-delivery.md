# Delivery: PLAN-20260324-019
- Plan ID: PLAN-20260324-019
- Source Request Baseline: [docs/session-handoff/SHO-20260325-0006.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/session-handoff/SHO-20260325-0006.md)
- Updated At: 2026-03-25T06:15:26Z

## 1. Purpose
This is a delivery/review artifact for the original window to verify whether the work requested after `SHO-20260325-0006` has been completed.

It is not a continuation pack and does not imply opening a new window.

Current status:
- the original mainline contract-closure work landed
- the follow-up fixes for the review-discovered blocker have now also landed
- original-window re-review then found a new backend contract blocker on `force_rerun`
- that blocker has now also been fail-closed
- original-window re-review found no new blocker after the final follow-up patch
- user then confirmed closeout, so `PLAN-20260324-019` is now completed

## 2. Delivery Summary
- `PLAN-20260324-019` was transitioned from `draft` to `in_progress`.
- The pre-implementation authority matrix was frozen in the plan and kept aligned with the architecture docs.
- Backend-first contract closure was implemented in this order:
  - quick runtime contract
  - `/tasks/quick/current` single authoritative contract
  - gate decision response contract
  - project mode status/progress contract
  - websocket terminal semantics
- Frontend authority-routing was then removed for the corresponding quick/project/websocket consumers.
- A post-implementation review then found one remaining blocker in project-mode contract semantics, and a follow-up patch resolved it before re-review.
- The subsequent re-review found a separate backend escape hatch: `force_rerun` still bypasses editorial approval gating in project mode.
- A final follow-up patch has now fail-closed that `force_rerun` escape hatch on both the endpoint pre-mark path and the EpisodeOrchestrator execution path.

## 3. Delivered Contract Changes
### 3.1 Quick Runtime
- `GET /tasks/{task_id}/runtime` now bootstraps an authoritative quick runtime view for active quick tasks instead of exposing `Runtime session not found` as a normal frontend control-flow branch.
- `src/hooks/useTaskPolling.ts` no longer falls back to coarse `/status` for authority routing.

### 3.2 Quick Current / Resumability
- `GET /tasks/quick/current` now returns `null` or `{ task, runtime }`.
- Frontend no longer checks `task && workflow_status` to infer resumability.

### 3.3 Gate Decision Immediate State
- `POST /tasks/{task_id}/runtime/script/decision` now returns required `runtime`.
- Frontend no longer branches on optional runtime payload.

### 3.4 Project Mode Status / Progress
- Editorial/script lifecycle and execution/runtime lifecycle now use separate vocabularies.
- `episodes_runtime[*].status` is now the execution/runtime authority.
- Planning/reference progress moved to typed `progress` projection.
- Frontend no longer uses `runtime?.status || episode.status`.
- Frontend no longer routes business state from `global_settings.*status/*error`.

### 3.5 WebSocket Terminal Semantics
- Completion/failure events are now explicitly non-authoritative terminal summaries.
- Frontend WS handling no longer directly sets the mainline review/completed state from terminal event payloads.

## 4. Review Findings Addressed Before Re-review
- Backend contract leak fixed:
  - `runtime.approved_script` now updates only on the approve path and no longer carries unapproved draft content into downstream project-mode agent context.
- Residual frontend fallback fixed:
  - project mode backend serialization now materializes runtime for every episode, and the UI no longer maps missing runtime to `idle`.
  - if runtime were still absent unexpectedly, the UI now surfaces that as contract unavailability rather than inventing business state.
- Explicit compatibility debt annotated:
  - `/tasks/{task_id}/status` and `ApiClient.getTaskCoarseStatus()` remain non-authoritative compatibility surfaces.
  - they are now explicitly marked compatibility-only in both docs and code comments/docstrings.

## 5. Latest Follow-up Fix
- Backend contract gap fixed:
  - `force_rerun` no longer bypasses editorial approval gating.
  - endpoint pre-marking now only treats `force_rerun` as a rerun instruction for already-approved episodes.
  - EpisodeOrchestrator now unconditionally skips unapproved episodes, even when `force_rerun=true`.
- Regression coverage:
  - `test_orchestrate_project_force_rerun_does_not_pre_mark_unapproved_episode`
  - `test_episode_orchestrator_force_rerun_does_not_bypass_editorial_approval`

## 6. Explicit Non-Goals Preserved
- `PLAN-20260324-017` was not reopened.
- `PLAN-20260324-018` was not pulled back into `019`.
- `same-object presentation mapping` was not treated as deletion target.
- No new compat adapter / bridge was added to preserve the old authority-routing shape.

## 7. Validation Snapshot
- Validation record: [docs/plans/active/PLAN-20260324-019-validation.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260324-019-validation.md)
- Focused backend results recorded there include:
  - `backend/tests/unit/test_runtime_session_service.py`
  - `backend/tests/unit/test_tasks_endpoint.py`
  - `backend/tests/unit/test_project_contracts.py`
  - focused `backend/tests/unit/test_episode_orchestrator.py` cases
- Remaining repo-level TS/Jest/tooling noise is recorded there as non-`019` validation noise and must not be reclassified as contract incompleteness.

## 8. Review Checklist For Original Window
- Confirm the implemented contract changes still match the frozen authority matrix in [docs/plans/active/PLAN-20260324-019.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260324-019.md).
- Confirm the delivery still respects the explicit scope split: `017` closed, `018` blocked, `019` backend-first.
- Confirm the follow-up patch really resolves the earlier `approved_script` semantic leak and the project runtime absence fallback.
- Confirm the latest follow-up patch really fail-closes the `force_rerun` backend escape hatch.
- Confirm the remaining validation noise is correctly classified as repo/tooling/config debt rather than `019` contract debt.
- Original-window re-review has now passed with no new blocker, and the user has explicitly confirmed closeout.
