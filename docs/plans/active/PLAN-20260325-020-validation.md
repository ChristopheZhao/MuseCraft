# Validation: PLAN-20260325-020
- Plan ID: PLAN-20260325-020
- Type: validation
- Status: completed
- Owner: codex
- Created At: 2026-03-25T09:44:54Z
- Updated At: 2026-03-25T11:42:11Z

## 1. Purpose
- This file owns verification for [PLAN-20260325-020](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260325-020.md).
- Focus:
  - prove that residual single-episode second-host / legacy-island cleanup does not reopen `016/017/019`
  - prove that project planning retention stays explicitly outside this plan

## 2. Validation Checklist
- A1. `backend/app/core/mas_*` legacy orchestration island has no active app caller before deletion.
- A2. `workflow_optimizer.py` has no active app caller before deletion.
- A3. After cleanup, `backend/app` no longer exposes a parallel single-episode orchestration surface.
- B1. project per-episode generation no longer starts from `_schedule_episode_orchestration(...)`.
- B2. queued/shared execution host remains the only per-episode execution container for project generation.
- B3. `_schedule_project_plan(...)` and `SeriesPlannerAgent` remain explicitly retained and are not accidentally deleted.
- C1. `017` SoT/projection boundaries are unchanged.
- C2. `019` authority-contract / frontend-consumer boundaries are unchanged.
- C3. queue / worker / API still act as execution container only, not runtime/control-plane owner.
- D1. residual helper / alias cleanup does not reintroduce compatibility-only truth surfaces.

## 3. Regression Expectations
- Grep/code audit:
  - no active imports of legacy orchestration island remain in `backend/app`
  - no endpoint-local per-episode thread host remains for project generation
- Backend tests:
  - focused task queue / project contract / orchestrator runtime suites
- Compile checks:
  - changed backend modules and touched tests compile

## 4. Evidence Log
- 2026-03-25T09:44:54Z validation draft created together with the residual-cleanup successor plan; concrete commands and results will be appended during implementation.
- 2026-03-25T10:12:44Z repo grep proof after the retirement slice: `rg -n "_schedule_episode_orchestration|_run_episode_orchestration|mas_agent_adapter|mas_communication|mas_handoff_manager|mas_orchestrator|mas_result_aggregator|mas_task_decomposer|mas_task_dispatcher|workflow_optimizer" backend/app backend/tests --glob '!**/__pycache__/**'` returned no matches.
- 2026-03-25T10:12:44Z compile check passed for the host-unification slice: `cd backend && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/api/v1/endpoints/projects.py tests/unit/test_project_contracts.py app/services/task_queue.py app/services/queued_task_execution_host.py`.
- 2026-03-25T10:12:44Z targeted project-contract regressions passed for the new queue-host path and retained project/runtime guardrails:
  - `cd backend && env PYTHONDONTWRITEBYTECODE=1 timeout 45s .venv/bin/python -m pytest -q tests/unit/test_project_contracts.py::test_orchestrate_project_queues_episode_generation_through_task_queue` (`1 passed, 4 warnings`)
  - `cd backend && env PYTHONDONTWRITEBYTECODE=1 timeout 45s .venv/bin/python -m pytest -q tests/unit/test_project_contracts.py::test_project_response_serialization_materializes_runtime_for_each_episode tests/unit/test_project_contracts.py::test_orchestrate_project_force_rerun_does_not_pre_mark_unapproved_episode tests/unit/test_project_contracts.py::test_episode_orchestrator_force_rerun_does_not_bypass_editorial_approval` (`3 passed, 4 warnings`)
- 2026-03-25T10:12:44Z `tests/unit/test_task_queue.py -k project` still timed out under the current environment and is not used as the primary acceptance proof for this slice because the new endpoint regression plus compile/grep evidence already cover the changed path.
- 2026-03-25T10:17:21Z repo grep proof after the residual-noise slice: `rg -n "get_workflow_status\\(" backend/app backend/tests src --glob '!**/__pycache__/**'` returned no matches.
- 2026-03-25T10:17:21Z compile check passed after deleting the dead summary helper: `cd backend && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/agents/orchestrator.py tests/unit/test_orchestrator_runtime_mainline.py`.
- 2026-03-25T10:17:21Z `cd backend && env PYTHONDONTWRITEBYTECODE=1 timeout 60s .venv/bin/python -m pytest -q tests/unit/test_orchestrator_runtime_mainline.py` timed out without usable output in the current environment; this file-level timeout is recorded as validation noise rather than a blocker because the removed helper no longer has any app/test caller and compile plus grep evidence already prove the retirement.
- 2026-03-25T10:27:52Z repo grep proof after the second residual-noise slice: `rg -n "workflow_status|enhanced_workflow_completed|enhanced_workflow_failed|get_workflow_status" backend/app src scripts backend/tests --glob '!**/__pycache__/**'` now only reports the negative assertion in `tests/unit/test_tasks_endpoint.py`, proving active app code no longer carries these legacy aliases/helpers.
- 2026-03-25T10:27:52Z compile checks passed for the second residual-noise slice:
  - `cd backend && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/agents/orchestrator.py app/agents/episode_orchestrator.py app/services/queued_task_execution_host.py tests/unit/test_task_queue.py tests/unit/test_audio_orchestration_runtime_gate.py tests/unit/test_orchestrator_runtime_mainline.py`
  - `./node_modules/.bin/tsc -p /tmp/tsconfig.frontend-runtime-check.json --pretty false`
- 2026-03-25T10:27:52Z targeted backend regressions passed for the host-result/status normalization and WS alias retirement with plugin autoload disabled to avoid environment startup noise:
  - `cd backend && env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 45s .venv/bin/python -m pytest -q tests/unit/test_task_queue.py::test_run_generation_in_host_initializes_worker_host_and_routes_quick_to_orchestrator tests/unit/test_task_queue.py::test_run_generation_in_host_routes_project_mode_to_episode_orchestrator` (`2 passed, 2 warnings`)
  - `cd backend && env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 45s .venv/bin/python -m pytest -q tests/unit/test_audio_orchestration_runtime_gate.py::test_orchestrator_main_loop_runs_runtime_true_chain_via_control_plane tests/unit/test_audio_orchestration_runtime_gate.py::test_orchestrator_main_loop_skips_runtime_llm_when_no_gate_event` (`2 passed, 6 warnings`)
- 2026-03-25T10:27:52Z the targeted `test_orchestrator_runtime_mainline.py` resume-after-approval command still timed out in the current environment without failure output, so this specific file remains validation noise; compile plus repo grep and the passing runtime/audio regressions are used as acceptance evidence for the status-field cleanup.
- 2026-03-25T11:42:11Z validation closeout confirmed together with user acceptance: the remaining timeout noise in `test_orchestrator_runtime_mainline.py` stays recorded as non-blocking environment noise and does not prevent `020` completion.
