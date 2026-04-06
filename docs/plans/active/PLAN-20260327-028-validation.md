# PLAN-20260327-028 Validation

- Plan ID: PLAN-20260327-028
- Recorded At: 2026-03-27T02:25:06Z
- Status: completed

## Purpose
- Record phase-by-phase verification for [PLAN-20260327-028](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-028.md).
- Keep the concrete project-level implementation work separate from the governance/decomposition work already completed in [PLAN-20260326-027.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260326-027.md).

## Validation Matrix
### Phase A
- Status: completed
- Planned checks:
  - project authority store / projection contract review against current project read-model consumers
  - boundary review confirming the authority surface remains limited to the four project wrapper fact groups frozen by `027` Phase A and does not absorb single-episode runtime/gate/decision authority
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`
- Evidence:
  - Added shared durable backing through `backend/app/models/project_workspace.py`, `backend/app/services/project_authority_store.py`, and `backend/alembic/versions/3a7d9f1b2c4e_add_project_workspaces_table.py`
  - Kept active-path API stable by retaining `ProjectStateRepository` as the facade and preserving `/projects/{id}` projection serialization
  - Added focused unit coverage for durable roundtrip, placeholder immediate-read, and project foundation/character-reference active-path consistency
- Results:
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/core/story_plan.py app/services/project_authority_store.py app/models/project_workspace.py app/api/v1/endpoints/projects.py app/agents/episode_orchestrator.py app/agents/series_planner.py app/services/project_service.py`
  - `timeout 180s .venv/bin/pytest -q tests/unit/test_project_contracts.py -x -vv -s`
  - `timeout 240s .venv/bin/pytest -q tests/unit/test_episode_orchestrator.py::test_build_episode_payload_uses_episode_context tests/unit/test_episode_orchestrator.py::test_project_character_reference_images_generated_and_idempotent tests/unit/test_episode_orchestrator_style.py::test_sync_project_foundation_reuses_story_plan_foundation -x -vv -s`
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`

### Phase B
- Status: completed
- Planned checks:
  - reader/writer migration review across planning, orchestration, project services, and `/projects/{id}` consumers
  - focused backend validation for shared project facts visibility
- Evidence:
  - `SeriesPlannerAgent` now persists and returns canonical shared-store state instead of stopping at the transient in-memory object
  - project-service writers now return the canonical saved state from the shared authority source
  - `EpisodeOrchestratorAgent` keeps its working copy refreshed after character-reference writes so active-path project facts stay aligned with the shared source
  - grep review confirms `ProjectStateRepository` no longer carries the old host-local `_states` implementation
- Results:
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/services/project_service.py app/agents/series_planner.py`
  - `timeout 240s .venv/bin/pytest -q tests/unit/test_project_contracts.py tests/unit/test_series_planner_project_store.py -x -vv -s`
  - `rg -n "_states|In-memory repository for project states|class ProjectStateRepository" backend/app/core/story_plan.py backend/app -g '*.py'`

### Phase C
- Status: completed
- Planned checks:
  - project-job adapter / planning-host migration validation
  - boundary review confirming `GenerationMode` / `TaskType` are not reused as planning dispatch authority and the new project-job host does not read runtime session or call `run_generation_in_host(...)`
  - evidence review confirming existing generation mainline remains untouched
- Evidence:
  - Added explicit project-job dispatch contract plus sibling queue/host execution path through `backend/app/services/project_job_contract.py`, `backend/app/services/project_job_queue.py`, `backend/app/services/project_job_execution_host.py`, and `backend/app/services/celery_app.py`
  - `create_project()` now attaches explicit `job_kind` / `handler_key` for planning while keeping `TaskType.SCRIPT_WRITING` as coarse metadata only
  - `_schedule_project_plan(...)` no longer spins an endpoint-local thread; it queues the sibling `process_project_job` worker entry instead
  - boundary grep confirms the new `project_job_*` path does not reference `GenerationMode`, `RuntimeSessionService`, `prepare_dispatch_payload_for_task_sync`, or `run_generation_in_host(...)`
- Results:
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile backend/app/api/v1/endpoints/projects.py backend/app/services/project_job_contract.py backend/app/services/project_job_execution_host.py backend/app/services/project_job_queue.py backend/app/services/celery_app.py backend/tests/unit/test_project_job_queue.py backend/tests/unit/test_project_job_execution_host.py backend/tests/unit/test_project_contracts.py`
  - `cd backend && timeout 300s .venv/bin/pytest -q tests/unit/test_project_contracts.py tests/unit/test_project_job_queue.py tests/unit/test_project_job_execution_host.py tests/unit/test_task_queue.py -x -vv -s`
  - `rg -n "GenerationMode|RuntimeSessionService|run_generation_in_host|prepare_dispatch_payload_for_task_sync" backend/app/services/project_job_* -g '*.py'`
  - `rg -n "threading\.Thread|asyncio\.new_event_loop|run_until_complete\(_run_project_plan|def _run_project_plan" backend/app/api/v1/endpoints/projects.py -g '*.py'`
  - `git status --short -- backend/app/api/v1/endpoints/projects.py backend/app/services/celery_app.py backend/app/services/project_job_contract.py backend/app/services/project_job_execution_host.py backend/app/services/project_job_queue.py backend/tests/unit/test_project_contracts.py backend/tests/unit/test_project_job_queue.py backend/tests/unit/test_project_job_execution_host.py docs/plans/active/PLAN-20260327-028.md docs/plans/active/PLAN-20260327-028-validation.md docs/plans/PLAN_INDEX.json`
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`

### Phase D
- Status: completed
- Planned checks:
  - final governance consistency review
  - exit-criteria review confirming `028` is sufficient to return to MAS-level frontend/backend integration and does not leave new project-level expansion scope inside the same stream
  - focused frontend authority-consumer smoke + backend contract evidence review covering create project -> poll planning -> read workspace projection -> orchestrate project, without overstating it as a full FE/BE end-to-end proof
  - user confirmation gate before lifecycle closeout
- Evidence:
  - Added a minimal frontend authority-projection smoke in `__tests__/integration/project-mode-store-smoke.test.tsx` covering `createProject -> startPollingProject -> getProject projection -> orchestrateProject`
  - Re-ran the bounded backend regression slice after Phase C and confirmed the sibling project-job host path still coexists cleanly with the generation mainline
  - Refreshed [mas_architecture_deviation_inventory_20260323.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_deviation_inventory_20260323.md) so it no longer describes project planning as an endpoint-local retained host and now points follow-up work back to MAS-mainline FE/BE integration
  - Exit-gate review confirms `028` now meets the bounded-unblocker goal: shared authority backing, stable `/projects/{id}` projection, unified project readers/writers, sibling planning host, and one minimal frontend authority-consumer smoke plus backend contract slice are all in place
- Results:
  - `cd backend && timeout 300s .venv/bin/pytest -q tests/unit/test_project_contracts.py tests/unit/test_project_job_queue.py tests/unit/test_project_job_execution_host.py tests/unit/test_task_queue.py -x -q`
  - `./node_modules/.bin/jest --config jest.config.js --selectProjects integration --runTestsByPath __tests__/integration/project-mode-store-smoke.test.tsx --runInBand`
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`
- Closeout:
  - Phase D is complete. At the end of the phase, `028` satisfied its bounded return-to-mainline exit gate and moved to `awaiting_user_confirmation` instead of auto-closing; the final lifecycle transition to `completed` happened only after the later explicit user acceptance recorded below.

## Notes
- Lifecycle status remains owned by the plan header and [PLAN_INDEX.json](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/PLAN_INDEX.json).
- 2026-03-27T02:25:06Z created this implementation successor after `027` Phase C concluded that direct in-plan migration would be too cross-cutting; the implementation stream is now narrowed to project authority store/projection, project reader-writer migration, and sibling project-job host entry only.
- 2026-03-27T02:59:52Z tightened the draft boundary before execution after architecture/product/queue review: the authority surface is explicitly limited to the four project wrapper fact groups frozen in `027` Phase A, `GenerationMode` and `TaskType` are explicitly excluded from project planning dispatch authority, and the future sibling project-job host is explicitly forbidden from reading runtime session state or calling `run_generation_in_host(...)`.
- 2026-03-27T03:17:48Z added a return-to-mainline exit gate before execution: `028` is now explicitly bounded to unblock stable project-mode FE/BE integration and must hand back to the `single-episode MAS mainline` once shared authority backing, stable projection, unified readers/writers, sibling planning host, and one minimal frontend authority-consumer smoke plus backend contract slice are in place.
- 2026-03-27T03:27:10Z opened Phase A execution only: validation scope is narrowed to the authority backing / projection substrate slice; no Phase B reader-writer migration or Phase C host migration is allowed before Phase A evidence is reported and user-confirmed.
- 2026-03-27T04:10:09Z completed Phase A implementation and focused validation: durable project backing now exists behind the existing repository facade, placeholder project creation and `/projects/{id}` projection remained stable, and focused project/orchestrator unit tests passed without entering Phase B reader-writer migration.
- 2026-03-27T05:42:29Z completed Phase B migration and focused validation: planning and project-service writers now land on the canonical shared authority source, the active project/orchestrator contract suite plus planner persistence test passed on shared backing, and the old host-local `_states` implementation is no longer part of `ProjectStateRepository`.
- 2026-03-27T05:58:15Z completed Phase C migration and focused validation: project planning now queues through an explicit `project_workflow / plan_project` sibling worker entry, endpoint-local thread hosting is removed, focused project contract + project job + generation-mainline regression tests all passed (`23 passed`), and boundary grep confirms the new project-job path remains decoupled from `GenerationMode`, `RuntimeSessionService`, and `run_generation_in_host(...)`.
- 2026-03-27T06:20:14Z completed Phase D closeout. The bounded backend regression slice still passes, the new frontend store smoke proves project-mode consumers can create, poll, read workspace projection, and orchestrate without adding a second state machine, the deviation inventory now matches the implemented planning-host migration facts, and `028` is reduced to awaiting-user-confirmation rather than auto-closing.
- 2026-03-27T06:36:03Z tightened the Phase D wording after acceptance review: the existing frontend proof is now recorded as a store/authority-consumer smoke paired with backend contract validation, not as a full FE/BE end-to-end smoke; integrated request-chain validation is deferred to the follow-up MAS-mainline integration stream.
- 2026-03-27T06:43:17Z user confirmed the Phase D closeout after the wording-tightening pass; lifecycle ownership now advances from `awaiting_user_confirmation` to `completed`, with no further project-level expansion work retained inside `028`.
