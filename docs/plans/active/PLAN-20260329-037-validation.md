# Validation Ledger: PLAN-20260329-037

## Scope
- Validate that generic stale-run resume is owned by control-plane continuation checkpoints rather than guarded re-dispatch.

## Automated Checks
- [x] Backend tests for continuation checkpoint schema/validation
- [x] Backend tests for generic resume consumer and fail-fast rejection
- [x] Backend tests for `resume_control` reason precedence
- [x] Frontend/API contract checks if projection shape changes

## Manual Checks
- [x] API restart only reattaches `quick/current` view and subscriptions
- [x] Live transport returns view-only state and no resume CTA
- [x] Stale run without checkpoint returns `resume_blocked`
- [x] Stale run with valid checkpoint returns `resume_available`
- [x] Explicit resume on valid checkpoint produces new runtime progression evidence
- [x] `waiting_gate` remains gate-owned and rejects generic resume

## Evidence Log
- 2026-03-29T07:14:08Z `backend/.venv/bin/pytest backend/tests/unit/test_runtime_session_service.py backend/tests/unit/test_tasks_endpoint.py -q` => `29 passed, 2 warnings in 18.06s`
- 2026-03-29T07:14:08Z `npm run build` => exit `0`; Next.js production build completed successfully. Existing repo noise remains: ESLint could not load `@typescript-eslint/recommended`, and static export emitted pre-existing MIME warnings for `.pdf/.doc/.docx`.
- 2026-03-29T07:32:27Z Escalated fixture seeding created four controlled quick-mode runtimes in the local dev DB: `stale_valid` task `8203e4b5-8994-43cb-935a-767766a35237` / db `1029`, `stale_blocked` task `da248945-64c7-4560-a570-62e8a3b3c887` / db `1030`, `live_transport` task `e780c5fb-6824-4662-994e-0a0ca8053e6b` / db `1031`, and `waiting_gate` task `d3aa0e47-cf61-4475-b9ca-408a3a75172a` / db `1032`. The live-transport fixture was bound to scheduled Celery task `56a0193c-33d7-4bb2-9332-4d7c5d8941c0` to force `transport_active`.
- 2026-03-29T07:32:27Z A fresh `uv run uvicorn app.main:app --host 0.0.0.0 --port 8006 --log-level info` instance served the restart-path checks. `GET /api/v1/tasks/quick/current?session_id=phase3-037-20260329T072328Z-reattach` returned the stale-checkpoint task in `resume_available`, and a WebSocket client connected to `ws://127.0.0.1:8006/api/v1/ws/connect`, then sent `{\"type\":\"subscribe_task\",\"task_id\":\"8203e4b5-8994-43cb-935a-767766a35237\"}`; the log only recorded `WebSocket subscribed to task 8203e4b5-8994-43cb-935a-767766a35237` and disconnect, with no queue dispatch or worker receive for db task `1029` before explicit resume.
- 2026-03-29T07:32:27Z Read-model checks on `8006` matched the frozen contract: `GET /api/v1/tasks/e780c5fb-6824-4662-994e-0a0ca8053e6b/runtime` returned `resume_control.state=view_only_running` / `reason_code=transport_active`; `GET /api/v1/tasks/da248945-64c7-4560-a570-62e8a3b3c887/runtime` returned `resume_blocked` / `missing_continuation_checkpoint`; `GET /api/v1/tasks/8203e4b5-8994-43cb-935a-767766a35237/runtime` returned `resume_available` / `stalled_runtime_with_checkpoint`; and `GET /api/v1/tasks/d3aa0e47-cf61-4475-b9ca-408a3a75172a/runtime` returned `waiting_gate` / `awaiting_gate_decision`.
- 2026-03-29T07:32:27Z Resume endpoint checks also matched the contract. `POST /runtime/resume` returned `409` for live transport (`state=view_only_running reason=transport_active`), stale-without-checkpoint (`state=resume_blocked reason=missing_continuation_checkpoint`), and waiting gate (`state=waiting_gate reason=awaiting_gate_decision`). The resumable stale fixture returned `200` with `message="Runtime resume accepted"` and runtime status `resuming`.
- 2026-03-29T07:32:27Z Explicit resume produced new execution evidence for the stale-checkpoint fixture: the API logged `Task 1029 queued through background worker`, the queue logged `Queued task 1029 for processing. Celery task ID: 710fd1d9-4504-4b06-a5fb-c19b0eb79844`, and the worker logged `sync_process_video_task called for task_id: 1029`, `Loaded runtime session 23 for task 1029`, and `Routing task 1029 directly through quick orchestrator mainline`. The run later failed with an unrelated `[Errno 5] Input/output error`, but the resume semantics were already proven by the new dispatch and control-plane progression.
- 2026-03-29T07:32:27Z Cleanup completed after validation: the temporary `8006` API was shut down, scheduled transport probe task `56a0193c-33d7-4bb2-9332-4d7c5d8941c0` was revoked, `stale_blocked`/`live_transport`/`waiting_gate` were cancelled, and the resumed `stale_valid` fixture was left in its terminal failed state.
- 2026-03-29T08:38:41Z Post-validation regression repair stayed within the orchestrator slice only: [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) restored the missing `WorkflowNodeStatus` import and updated `_open_script_review_gate(...)` to build a `gate_decision` checkpoint with explicit `node_key=script` and `attempt_id=script_attempt_id`, preserving `attempt.continuation_checkpoint` as the only continuation carrier.
- 2026-03-29T08:38:41Z `cd backend && PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/unit/test_orchestrator_runtime_mainline.py` => `8 passed, 2 warnings in 13.73s`
- 2026-03-29T08:38:41Z `cd backend && PYTHONDONTWRITEBYTECODE=1 uv run pytest -q tests/unit/test_runtime_session_service.py tests/unit/test_tasks_endpoint.py tests/unit/test_orchestrator_runtime_mainline.py` => `37 passed, 2 warnings in 36.83s`
