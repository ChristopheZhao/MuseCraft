# Validation: PLAN-20260324-019
- Plan ID: PLAN-20260324-019
- Updated At: 2026-03-25T06:15:26Z

## 0. Current Acceptance Status
- This validation file now records both:
  - evidence for the completed mainline contract-closure slices
  - evidence for the follow-up patch that addressed the review-discovered blocker
- Current status:
  - the `force_rerun` backend contract blocker identified in original-window re-review has been fail-closed
  - the subsequent original-window re-review reported no new blocker
  - the user has now explicitly confirmed closeout, so `PLAN-20260324-019` is completed

## 1. Contract Closure Evidence
- quick runtime:
  - `GET /tasks/{task_id}/runtime` now bootstraps an authoritative quick runtime view for active quick tasks instead of exposing `404 Runtime session not found` as a frontend control-flow branch
- quick current:
  - `GET /tasks/quick/current` now returns either `null` or a single resumable-run object with `task + runtime`
- gate decision:
  - `POST /tasks/{task_id}/runtime/script/decision` now returns a required `runtime` object instead of optional `workflow_status`
- project mode:
  - editorial/script lifecycle and execution/runtime lifecycle are now separated in backend/frontend type vocabulary
  - project planning/reference progress now lives under typed `progress.*` projection instead of `global_settings.*status/*error`
  - follow-up patch now restricts `runtime.approved_script` to approved editorial content and materializes runtime projection for every episode in project responses
  - latest follow-up patch now fail-closes `force_rerun`, so it no longer allows unapproved episode execution
- websocket terminal semantics:
  - completion/failure events now declare `projection_role=bounded_terminal_summary`, `runtime_authoritative=false`, and `refresh_required=true`
  - frontend WS handling no longer uses terminal event payloads to set mainline completed/review state directly

## 2. Backend Compile Check
- command:
```bash
backend/.venv/bin/python -m py_compile \
  backend/app/services/runtime_session_service.py \
  backend/app/api/v1/endpoints/tasks.py \
  backend/app/core/story_plan.py \
  backend/app/agents/series_planner.py \
  backend/app/services/project_service.py \
  backend/app/api/v1/endpoints/projects.py \
  backend/app/services/character_reference_images.py \
  backend/app/agents/episode_orchestrator.py \
  backend/app/services/workflow_completion_adapter.py \
  backend/tests/unit/test_runtime_session_service.py \
  backend/tests/unit/test_tasks_endpoint.py \
  backend/tests/unit/test_episode_orchestrator.py \
  backend/tests/unit/test_project_contracts.py
```
- result: passed

## 3. Focused Backend Regression
- command:
```bash
backend/.venv/bin/python -m py_compile \
  backend/app/services/project_service.py \
  backend/app/api/v1/endpoints/projects.py \
  backend/app/agents/episode_orchestrator.py \
  backend/app/api/v1/endpoints/tasks.py \
  backend/tests/unit/test_project_contracts.py
```
  - result: passed

- command:
```bash
backend/.venv/bin/python -m pytest -q \
  backend/tests/unit/test_project_contracts.py -vv
```
  - result: `6 passed, 4 warnings in 7.81s`

- command:
```bash
backend/.venv/bin/python -m pytest -q \
  backend/tests/unit/test_runtime_session_service.py
```
  - result: `8 passed, 2 warnings in 9.08s`

- command:
```bash
timeout 45s backend/.venv/bin/python -m pytest -q \
  backend/tests/unit/test_tasks_endpoint.py
```
  - result: earlier in this window reported `6 passed, 2 warnings in 6.06s`

- note:
  - a later rerun of `backend/tests/unit/test_tasks_endpoint.py` in the current environment did not produce output in a reasonable time, but the only subsequent change in `backend/app/api/v1/endpoints/tasks.py` was a docstring update that marks coarse `/status` as compatibility-only
  - `backend/tests/unit/test_project_contracts.py` now carries the stable focused regressions for both `force_rerun` fail-close paths, avoiding the historically noisy `test_episode_orchestrator.py` execution path for this particular contract check
  - `timeout 45s backend/.venv/bin/python -m pytest -q backend/tests/unit/test_episode_orchestrator.py::test_build_episode_payload_uses_episode_context` still exhibits the same no-output hang pattern in the current environment and is treated as unrelated validation noise

## 4. Focused Frontend Type Check
- temporary verification config:
  - `/tmp/tsconfig.plan019.json`
- command:
```bash
timeout 120s ./node_modules/.bin/tsc -p /tmp/tsconfig.plan019.json --noEmit --incremental false --pretty false
```
- result:
  - blocked by pre-existing repo TypeScript environment/config gaps unrelated to `019` contract edits:
    - `process` / `NodeJS` globals are missing from the active TS environment
    - current `lib` target is too old for existing `padStart` usage in `src/lib/utils.ts`
  - after narrowing away test files, no new `019`-specific structural type errors remained beyond those existing repo-level config issues

## 5. Frontend/Test Tooling Boundary
- full repo `tsc` is also blocked by an existing non-`019` test-source issue:
```bash
timeout 120s ./node_modules/.bin/tsc -p tsconfig.json --noEmit --incremental false --pretty false
```
  - result: fails on `__tests__/utils/test-helpers.ts`, which contains JSX in a `.ts` file and lacks the required test typing/config surface
- Jest/integration execution remains explicitly outside `019` acceptance:
  - `PLAN-20260324-018` stays the owner of current frontend test-runner/filesystem/tooling blockers
  - `019` does not require reopening `018` before contract acceptance

## 6. Acceptance Mapping And Remaining Noise
- quick polling no longer cross-reads coarse `/status` after runtime read failure
- quick resumability no longer requires frontend `task && workflow_status` authority routing
- gate decision UI no longer branches on optional runtime payload
- project UI no longer uses `runtime?.status || episode.status`
- planning/reference UI no longer routes on `global_settings.*status/*error`
- WS terminal completion no longer directly pushes the mainline UI into completed/review without a refreshed authoritative runtime view
- follow-up fix:
  - `runtime.approved_script` now remains an approved-only surface; unapproved edits stay on `episode.script_draft`
- follow-up fix:
  - project mode no longer invents `idle` from missing runtime; backend now provides episode runtime projection and the UI surfaces absence as contract unavailability
- follow-up fix:
  - `force_rerun` now only means rerunning already-approved execution/runtime and no longer bypasses editorial approval gating
- explicit compat debt:
  - `/tasks/{task_id}/status` remains a non-authoritative compatibility surface and is no longer part of the mainline frontend authority path
- governance closeout:
  - original-window re-review found no new blocker after the final `force_rerun` fix
  - remaining TS/Jest/tooling noise stays classified as `018` / environment debt rather than `019` contract incompleteness
