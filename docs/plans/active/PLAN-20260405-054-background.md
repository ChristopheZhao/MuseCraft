# Background Note: PLAN-20260405-054

## Purpose
- Preserve the evidence and governance reasoning behind the `054` successor.
- Explain why [PLAN-20260404-053.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260404-053.md) is useful history but not a safe execution baseline.
- Freeze the architecture and boundary interpretation before any repair work resumes.

## Why 053 Is Not Executable As-Is
- `053` correctly identified the original runtime-vs-persistence split, but it stopped before freezing the authoritative final-video contract.
- `053` did not yet classify the current worktree strongly enough:
  - some changes are on the original state-sync path
  - some changes are architecture-aligned but incomplete
  - some changes are clearly off-path for the original symptom
- Later verification added a second proven issue that `053` did not contain:
  - if `video_composer` fails once and succeeds on retry, `quality_checker` can still fail because `project.final_video` was never written

## Confirmed Evidence
- Historical completed task `fab71508-3a2b-4c8f-a67c-4c63855c2b01` still shows:
  - `GET /api/v1/tasks/{id}` returns `output_metadata` without `final_video_url/final_video_path`
  - `GET /api/v1/tasks/{id}/resources` returns `[]`
  - `GET /api/v1/tasks/{id}/runtime` returns `summary_output.final_video_url=/files/outputs/videos/凡人修仙传2预告片_final.mp4`
- `GET /api/v1/tasks/{id}/result` returns `404`, proving the old frontend read path is stale.
- Current-worktree helper and offline mainline checks still pass:
  - `uv run pytest tests/unit/test_orchestrator_store_composer_outputs.py tests/unit/test_media_runtime_utils.py tests/unit/test_quality_checker_metadata.py -q`
  - `uv run pytest tests/integration/test_video_composer_react_flow.py::test_video_composer_react_flow -q`
- Current-worktree retry-path regression is also proven by a minimal orchestrator reproduction:
  - `video_composer` attempts: `2`
  - `quality_checker` attempts: `0`
  - `project.final_video` absent after retry success
  - terminal failure: `Cannot run quality_checker: project.final_video missing in MAS WM`
- Real acceptance run on new task `66191a8e-d73b-4512-a136-5ccfb9cd9868` adds a second same-stream proof:
  - `script` gate was approved through the supported API
  - `video_generator` completed all 3 scenes successfully
  - `video_composer` completed successfully and produced `/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/storage/outputs/videos/final_5s_blue_theme.mp4`
  - runtime then failed at `quality_checker` with `Cannot run quality_checker: project.final_video missing in MAS WM`
  - this proves the remaining gap is no longer the retry branch only; the real compose-success handoff is still incomplete
- Additional code evidence after architecture re-review:
  - ReAct tool execution already stores normalized media outputs into agent-memory `iteration_artifacts`
  - `image_generator` and `video_generator` both override `_finalize_success_results(...)` to aggregate stable deliverables from memory/SoT before returning to orchestrator
  - `video_composer` does not override `_finalize_success_results(...)`; it only returns candidate deliverable fields from the ACT round itself
  - this makes `video_composer` the current primary suspect for the lossy handoff seam, ahead of a generic `react_agent.py` rewrite

## Root-Cause Layering
- `contract` root cause:
  - the final-video authoritative source was not frozen as a single explicit contract across runtime summary, completion payload, persistence projection, and frontend consumption
- `owner` root cause:
  - runtime completion could succeed from `workflow_results.video_composer.final_video_url`
  - persistence projection consumed MAS `project.final_video`
  - this created two owners for one user-visible fact
- `implementation` deviation:
  - runtime summary and persisted read model drifted because they derived from different sources
- `current-window` regression:
  - ownership moved toward an orchestration-layer handoff path, which is directionally aligned with architecture
  - but the handoff implementation covers initial success only, not retry success
- `acceptance amendment`
  - in real `video_composer` runs, the remaining break is not a second deliverable SoT inside the agent
  - the failing seam is the `subagent completion receipt -> orchestrator handoff` envelope:
    - `video_composer` completes on a later no-tool PLAN round (`plan_contract_task_complete`)
    - [react_agent.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/react_agent.py) emits only a minimal subtask-complete receipt in that branch
    - orchestrator currently still promotes `project.final_video` from transient handoff fields such as `final_video_path/final_video_url`
    - those candidate refs are therefore lost before the authoritative shared fact is written
  - current bounded-repair hypothesis:
    - prefer a `video_composer`-local finalize / handoff fix that rebuilds its completion receipt from agent-memory iteration artifacts and boundary inputs
    - only touch `react_agent.py` if a narrower composer-local repair proves impossible

## Current Worktree Classification
- On-path:
  - [backend/app/agents/orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py)
  - [backend/app/services/data_persistence.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/data_persistence.py)
  - [src/hooks/useTaskPolling.ts](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/hooks/useTaskPolling.ts)
  - [src/lib/api.ts](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/lib/api.ts)
- Conditionally on-path:
  - [backend/app/agents/video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py)
  - [backend/app/agents/utils/media_runtime.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/utils/media_runtime.py)
- Off-path for the original state-sync symptom:
  - [backend/app/agents/quality_checker.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/quality_checker.py)
  - [backend/tests/unit/test_quality_checker_metadata.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/tests/unit/test_quality_checker_metadata.py)

## Frozen Worktree Disposition
- `keep in 054 repair stream`
  - [backend/app/agents/orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py)
    - keep the orchestration-owned final-video handoff direction
    - rework is still required because retry success does not yet flow through the same handoff path
  - [backend/app/services/data_persistence.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/data_persistence.py)
    - keep in scope because it belongs to the persisted read-model projection
  - [src/hooks/useTaskPolling.ts](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/hooks/useTaskPolling.ts)
  - [src/lib/api.ts](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/lib/api.ts)
    - keep in scope because they remove the stale `/result` dependency and stay inside read-model consumption
  - [backend/tests/unit/test_orchestrator_store_composer_outputs.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/tests/unit/test_orchestrator_store_composer_outputs.py)
    - keep as an on-path unit test for final-video fact write behavior
- `split before execution`
  - [backend/app/agents/video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py)
    - the owner-shift away from direct MAS writes is architecture-aligned and may stay
    - the ffmpeg metadata probe is not required to close `054` and should not be treated as part of the authority-convergence repair unless later evidence proves otherwise
  - [backend/app/agents/utils/media_runtime.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/utils/media_runtime.py)
    - `build_local_public_url(...)` may stay only if the orchestrator-owned handoff needs a shared path helper
    - `resolve_public_media_path(...)` and `normalize_video_probe_metadata(...)` belong with QC/metadata work, not with `054`
  - [backend/tests/unit/test_media_runtime_utils.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/tests/unit/test_media_runtime_utils.py)
    - split alongside `media_runtime.py`; keep only helper coverage that remains inside `054`
- `move out of 054`
  - [backend/app/agents/quality_checker.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/quality_checker.py)
  - [backend/tests/unit/test_quality_checker_metadata.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/tests/unit/test_quality_checker_metadata.py)
    - these widen QC technical/compliance semantics and path handling; they are not required to close the final-video authority contract
  - [backend/tests/integration/test_video_composer_react_flow.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/tests/integration/test_video_composer_react_flow.py)
    - the new metadata assertions lock in the ffmpeg metadata probe, which is outside the frozen `054` repair stream
  - API startup tool auto-load warnings
    - record as a separate follow-on rather than mixing them into the final-video repair

## Architecture and Boundary Interpretation
- `single authority`
  - the user-visible final-video fact must converge on one authoritative runtime fact, not separate runtime-summary and persistence fallbacks
- `single owner`
  - committing that authoritative fact should use one orchestration-owned handoff path
  - leaf-agent return payloads may carry candidate deliverable refs, but they must not become a second authority
- `subtask completion vs workflow completion`
  - `task_complete` or `plan_contract_task_complete` only means the subagent has finished its local ReAct objective
  - whether the whole workflow is complete is still an orchestrator decision
- `handoff receipt vs shared fact`
  - shared WM `project.final_video` is the deliverable SoT
  - the subagent return payload is only a transient handoff receipt consumed by orchestrator
- `handoff owner split`
  - [react_agent.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/react_agent.py) only owns the generic completion-envelope shape for ReAct subagents
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) owns promotion into MAS shared facts such as `project.final_video`
  - `quality_checker` is only a consumer-side gate and must stay out of the fix owner path
- `runtime SoT vs read-model separation`
  - runtime facts belong to the MAS/control-plane side
  - task detail, resources, and frontend review consume projections only
- `contract-first`
  - downstream consumers must not hide authority drift with extra silent fallbacks
- `no scope bleed`
  - this repair stream stays inside final-video authority convergence and retry-handoff repair
  - after the acceptance run, the bounded amendment is:
    - first localize the exact handoff-contract owner before changing code
    - only then decide whether [react_agent.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/react_agent.py), [video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py), or orchestrator handoff consumption is the bounded repair point
    - still out of scope: `quality_checker`, unrelated runtime/controller changes, and any second-authority fallback design

## Current Remaining Amendment Scope
- The broad 054 baseline already kept in worktree is not the same thing as the current open amendment touch set.
- Current first repair point:
  - [backend/app/agents/video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py)
  - focused composer finalize / handoff regression coverage
- Contract interpretation for the remaining seam:
  - the completion receipt should be rebuilt from the same-run bounded execution evidence available to the composer
  - that means agent-local execution evidence such as `iteration_artifacts` and current execution-boundary inputs
  - it does not mean introducing a new MAS shared-WM receipt surface or a second deliverable authority
- Therefore:
  - prefer a `video_composer`-local finalize / handoff synthesis repair first
  - keep orchestrator as the only owner that promotes the accepted receipt into `project.final_video`
  - widen to [backend/app/agents/react_agent.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/react_agent.py) or [backend/app/agents/orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) only if the composer-local repair is disproved

## Separate Follow-On Candidates
- `quality_checker` widening review:
  - current QC diff changes technical/compliance semantics and path handling
  - keep it outside `054` unless a later review proves it is required by the same authority contract
- Tool auto-load warnings at API startup:
  - `jimeng_image`
  - `minimax_video`
  - `video_composer_tool`
  - these are operator/tool-registry issues, not part of the final-video authority repair stream

## Use Order
- Read this note first.
- Then read [PLAN-20260405-054.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260405-054.md).
- Treat [PLAN-20260404-053.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260404-053.md) as reference-only history.
