# PLAN-20260328-032 Validation

- Plan ID: PLAN-20260328-032
- Recorded At: 2026-03-28T02:54:28Z
- Status: in_progress

## Purpose
- Record phase-by-phase verification for [PLAN-20260328-032](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260328-032.md).
- Keep this successor stream separate from the already accepted [PLAN-20260327-031.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-031.md); this plan exists because the latest live run proved the old “persisted task specs” path still depended on Shared WM rather than true control-plane continuation state.

## Validation Matrix
### Phase 0
- Status: completed
- Planned checks:
  - confirm the latest approve failure happens after requeue into a fresh queued execution host
  - confirm `Missing persisted workflow.task_specs for resume action: approve` is raised from orchestrator resume path
  - confirm [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) still persists and loads `workflow.task_specs` through Shared WM
  - confirm current control-plane persisted surfaces only cover decision/deliverable/review-contract facts, not the full continuation authority
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`
- Evidence:
  - [mas_workflow.log](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/logs/mas/mas_workflow.log) shows the sequence `queued execution host bootstrap -> orchestrator start -> WM_CREATE -> Missing persisted workflow.task_specs for resume action: approve`, which confirms the failure occurs in a fresh worker run rather than inside the previous host
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) raises the failure in `_load_authoritative_resume_task_specs(...)` before any further resume execution can happen
  - [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) `persist_task_specs(...)` / `load_task_specs(...)` use `write_shared_fact(...)` / `read_shared_fact(...)` against the injected short-term memory service, so the current authority is still WM-backed
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) persists `decision.action`, `decision.invalidation_scope`, `script_review_contract`, and `published_deliverables` refs, but no minimal continuation snapshot yet exists
  - [workflow_runtime.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/models/workflow_runtime.py) shows the existing control-plane SoT surfaces available for reuse: `WorkflowSession.input_payload`, `WorkflowGateDecision`, `WorkflowGate`, `WorkflowNodeAttempt`, and `WorkflowPublishedDeliverable`
- Results:
  - source review of the files listed above

### Phase 1
- Status: completed
- Planned checks:
  - freeze the minimal continuation snapshot field table for `approve` / `revise` / `replan`
  - classify each field as authoritative persisted state vs derived-on-recovery state
  - confirm banned content does not include full WM or diagnostics-only projections
- Evidence:
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) already persists the existing authoritative control-plane facts that should be reused directly rather than duplicated: `decision.action`, `decision.invalidation_scope`, `session.status/current_node_key/current_attempt_id`, `published_deliverables["script"]`, and `script_review_contract`
  - [orchestration_queue_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_queue_policy.py) proves `execution_queue` and `standby_agents` are deterministic derived artifacts from `candidate_agents` plus `task_specs`, so they must not become persisted snapshot fields
  - [orchestration_runtime_controller.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_runtime_controller.py) shows runtime activation already persists updated `task_specs` back through the orchestration-state adapter, which means the missing durable projection is the normalized plan assignment surface itself, not a second queue model
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) and [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) consume only a narrow subset of task-spec fields for resume, execution-contract building, and runtime hints; `fallback_used` is not part of the execution contract and is therefore excluded from the frozen minimal snapshot
- Results:
  - frozen contract:
    - existing SoT reused directly: decision/session/gate anchor + published deliverable ref + script review contract
    - new minimal projection only: `version`, `decision_id`, ordered `candidate_agents`, normalized `task_specs`, normalized `conditional_task_specs`
    - `continuation.decision_id` is binding metadata only; authoritative decision SoT remains `WorkflowGateDecision.id`
    - explicitly derived, not persisted: `execution_queue`, `standby_agents`, `skip_agents`
    - explicitly banned: diagnostics snapshots and full WM persistence

### Phase 2
- Status: completed
- Planned checks:
  - freeze the single-path recovery chain and owner split
  - define fail-fast diagnostics for missing snapshot fields
  - confirm queue/worker remains transport-only
- Evidence:
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) already owns both gate-open and decision-submit lifecycle transitions, which makes it the correct control-plane boundary for persisting a pending continuation checkpoint before `waiting_gate` and binding the latest decision when resume is requested
  - [task_queue.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py) and [queued_task_execution_host.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/queued_task_execution_host.py) only requeue tasks, prepare dispatch payloads, and bootstrap worker-local execution state; no continuation semantics are needed or allowed there
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) currently creates fresh WM at run start and then consumes runtime session plus review-contract state, which matches the frozen chain direction `fresh WM -> load active continuation -> hydrate working projections -> continue`
  - [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) resolves content facts from published deliverable refs in `runtime_input_payload`, so it can remain strictly content-fact-only and does not need continuation ownership
- Results:
  - frozen chain:
    - write moment 1: gate-open persists pending normalized continuation plan under control-plane anchor before worker exits
    - write moment 2: decision-submit binds latest decision to that checkpoint and marks session `RESUMING`
    - read moment: resume bootstrap loads active continuation by session/node/attempt/decision anchor, then hydrates WM projections
  - frozen owner split:
    - control plane owns pending/active continuation lifecycle
    - orchestrator produces and consumes normalized continuation data but does not durably persist it
    - state adapter hydrates WM only
    - context assembler resolves content facts only
    - queue/worker remains transport-only
  - frozen fail-fast rules:
    - missing or stale checkpoint, missing script review contract for revise/replan, or malformed continuation plan all fail explicitly with no WM fallback

### Phase 3
- Status: completed
- Planned checks:
  - decide the implementation cut and focused validation bundle
  - sync governance assets after the design freeze
- Evidence:
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) serializes `active_gate.facts` into the runtime read-model, and frontend consumers already read `active_gate.facts.script_preview_text` / `trigger_reason`, so `WorkflowGate.facts` cannot safely carry internal continuation plan data
  - [task_queue.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py) forwards `runtime_session.input_payload` as dispatch payload for quick-mode resume, which makes `WorkflowSession.input_payload` the wrong place for execution-authority state
  - [workflow_runtime.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/models/workflow_runtime.py) already gives an internal, attempt-scoped control-plane entity (`WorkflowNodeAttempt`) whose rows are naturally anchored by `gate.attempt_id` and are not exposed in the runtime read-model
  - [8b1f0c2d4e5f_add_workflow_runtime_tables.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/alembic/versions/8b1f0c2d4e5f_add_workflow_runtime_tables.py) confirms a minimal migration on `workflow_node_attempts` is straightforward and does not require a new table or index
- Results:
  - chosen implementation cut:
    - add `workflow_node_attempts.continuation_checkpoint` JSON column
    - write pending checkpoint during gate-open transaction
    - bind only `decision_id` during decision submit, strictly as metadata mirror rather than independent decision authority
    - read active continuation via new control-plane loader
    - hydrate WM from checkpoint only after control-plane read succeeds
  - rejected carriers:
    - `gate.facts` because it leaks into read-model/frontends
    - `session.input_payload` because it is already the content/dispatch surface
    - `session.gate_policy` because it would become opaque session-level shadow state
    - `attempt.input_contract` because it would conflate attempt input with post-gate continuation lifecycle

### Phase 4
- Status: completed
- Planned checks:
  - implement the attempt-scoped checkpoint column and control-plane loader without introducing a second runtime state owner
  - verify gate-open writes a pending checkpoint, decision-submit binds only `decision_id`, and resume reads through control-plane before WM hydration
  - prove mainline approve/revise/replan resume still works after clearing Shared WM
- Evidence:
  - [workflow_runtime.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/models/workflow_runtime.py) now adds `WorkflowNodeAttempt.continuation_checkpoint` as the dedicated internal control-plane storage surface
  - [9e4b7c1a2d3f_add_workflow_attempt_continuation_checkpoint.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/alembic/versions/9e4b7c1a2d3f_add_workflow_attempt_continuation_checkpoint.py) adds the nullable JSON column without new tables or indexes
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) now validates pending checkpoints on gate-open and decision-submit, binds only `decision_id`, and loads active continuation by session/gate/attempt/latest-decision anchor
  - [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) now owns checkpoint normalization/validation plus WM hydration, while keeping WM as a reconstructible projection surface
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) now writes the pending checkpoint before opening the script gate and reloads continuation from control plane during resume
  - [test_runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_runtime_session_service.py) covers pending checkpoint persistence, missing-checkpoint rejection, decision binding, and stale binding detection
  - [test_orchestrator_runtime_mainline.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_orchestrator_runtime_mainline.py) now clears the fake Shared WM before approve/revise/replan resume, proving the new resume path does not rely on `workflow.task_specs`
  - `uv run pytest -q tests/unit/test_runtime_session_service.py -vv`
  - `uv run pytest -q tests/unit/test_orchestrator_runtime_mainline.py -q`
  - `uv run pytest -q tests/unit/test_published_deliverable_service.py -q`
  - `uv run python -m py_compile app/services/orchestration_state_adapter.py app/services/runtime_session_service.py app/agents/orchestrator.py`
- Results:
  - control-plane checkpoint implementation completed on the frozen single path
  - targeted runtime/session/orchestrator/deliverable validations passed under `uv`

### Phase 5
- Status: completed
- Planned checks:
  - confirm Alembic points at the intended dev MySQL database
  - apply the new continuation checkpoint migration to the live dev schema
  - verify both current revision and physical column presence after rollout
- Evidence:
  - [alembic.ini](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/alembic.ini) targets `mysql://videouser:videopass123@localhost:3306/short_video_maker`
  - `.venv/bin/alembic current` reported live revision `5d2e7a9c4f1b` before rollout and `9e4b7c1a2d3f (head)` after rollout
  - `.venv/bin/alembic heads` reported `9e4b7c1a2d3f (head)` as the only pending head
  - `.venv/bin/alembic upgrade head` successfully applied `5d2e7a9c4f1b -> 9e4b7c1a2d3f`
  - `uv run python -c ... inspect(engine).get_columns('workflow_node_attempts') ...` returned `continuation_checkpoint` in the real MySQL schema
- Results:
  - real dev DB migration completed successfully
  - `workflow_node_attempts.continuation_checkpoint` exists on the live dev schema
  - real approve/resume smoke remains intentionally deferred to the next stage

### Phase 6
- Status: completed
- Planned checks:
  - create or reuse a real quick task against the current-code API process rather than the stale `8005` dev server
  - verify the task reaches `script_review` gate with a live pending checkpoint on the migrated schema
  - submit a real `approve` decision and confirm runtime progresses past `script`
  - query dev MySQL to confirm the attempt checkpoint persisted the bound `decision_id`
- Evidence:
  - `curl -sS http://127.0.0.1:8006/api/v1/tasks/834776b8-268c-453b-b191-6de14ced1325/runtime` returned session `18` in `waiting_gate` on node `script` with attempt `14` and gate `11`, proving the current-code API reached the review checkpoint on the migrated schema
  - `curl -sS -X POST http://127.0.0.1:8006/api/v1/tasks/834776b8-268c-453b-b191-6de14ced1325/runtime/script/decision -H 'Content-Type: application/json' -d '{"action":"approve","actor_id":"codex-phase6-smoke"}'` returned `latest_decision.id = 8` and runtime `status = "resuming"`
  - `bash -lc "sleep 5; curl -sS http://127.0.0.1:8006/api/v1/tasks/834776b8-268c-453b-b191-6de14ced1325/runtime"` returned `status = "running"` and `current_node_key = "image"`, proving resume moved past the script gate into downstream execution
  - `.venv/bin/python -c "import json, pymysql; ... SELECT ... FROM workflow_node_attempts a JOIN workflow_node_states n ... WHERE a.id = 14"` returned a live row with `attempt_status = "succeeded"`, `node_key = "script"`, `gate_id = 11`, `gate_status = "decided"`, `latest_decision_id = 8`, and `continuation_checkpoint` containing `"decision_id": 8`
  - `ps -ef | rg 'uvicorn app.main:app|celery|8006|8005'` confirmed `8006` is a separate current-code uvicorn process from the long-lived `8005` dev server that previously produced stale behavior
- Results:
  - real approve/resume smoke succeeded on the current-code control-plane path
  - the live control-plane checkpoint now proves both pending persistence and decision binding on a real run, not just in unit tests
  - the earlier `8005` failure is attributable to stale dev process state rather than a surviving architecture defect in the new implementation

## Notes
- 2026-03-28T02:54:28Z completed Phase 0 successor audit only. The new evidence changes the accepted baseline from 031 in one precise way: the code path named “persisted task specs” is still a short-term WM projection, so resume authority is not actually durable across worker boundaries. The next phase is therefore narrowed to minimal control-plane continuation snapshot design plus single-path recovery-chain definition, not to queue refactors, artifact-owner promotion, or WM persistence.
- 2026-03-28T02:59:16Z completed Phase 1 field freeze only. The design is now materially narrower than the handoff sketch: `resume_action`, `invalidation_scope`, resume anchor, deliverable refs, and review contract are all existing control-plane facts and must not be recopied into a new snapshot body; the only missing durable projection is the normalized continuation plan itself, consisting of `version`, `decision_id`, ordered `candidate_agents`, `task_specs`, and `conditional_task_specs`, with execution queues, standby lists, diagnostics snapshots, and full WM content explicitly rejected as non-authoritative derived state.
- 2026-03-28T03:04:25Z completed Phase 2 recovery-chain freeze only. The crucial architectural refinement is that the active continuation snapshot cannot be first materialized at decision-submit time, because the authoritative task plan exists only inside the still-running worker before the gate is opened. The frozen single path therefore requires control-plane persistence at gate-open, decision binding at submit time, and read-side hydration back into fresh WM during resume bootstrap. This keeps control-plane ownership intact without promoting queue, artifact payloads, or WM into recovery owners.
- 2026-03-28T03:12:40Z completed Phase 3 implementation-cut design only. The chosen cut deliberately prefers one explicit attempt-scoped control-plane field over reusing any existing generic JSON surface. That keeps the architecture honest: gate facts stay human-facing, session input payload stays content/request-facing, queue stays transport-only, and WM remains reconstructible workspace rather than recovery truth.
- 2026-03-28T03:20:00Z added a post-review clarification to prevent dual-SoT drift. `continuation_checkpoint.decision_id` is now explicitly treated as binding metadata only, and any future resume reader must load the latest `WorkflowGateDecision.id` first and use checkpoint `decision_id` solely for stale/integrity validation.
- 2026-03-28T03:32:27Z completed Phase 4 implementation verification. The accepted implementation preserves the handoff boundaries: queue/worker remain transport-only, `WorkflowNodeAttempt.continuation_checkpoint` becomes the only new control-plane carrier, `WorkflowGateDecision.id` remains decision authority, and fresh-WM resume is now verified by clearing the fake Shared WM in orchestrator mainline tests before approve/revise/replan continuation runs.
- 2026-03-28T03:41:44Z completed Phase 5 live schema rollout. The migration was applied to the actual MySQL dev database configured in `backend/alembic.ini`, current revision now matches `9e4b7c1a2d3f (head)`, and the new `workflow_node_attempts.continuation_checkpoint` column was verified via SQLAlchemy inspection rather than inferred from Alembic state alone.
- 2026-03-28T04:05:39Z completed Phase 6 live approve/resume smoke. The acceptance bar is now higher than unit coverage: a real task on the current-code `8006` API reached `script_review`, accepted `approve`, resumed through control-plane checkpoint loading, advanced into `image`, and persisted `decision_id = 8` back onto the attempt checkpoint in dev MySQL. This closes the original `missing persisted workflow.task_specs` regression on the intended single recovery path while also isolating the earlier `8005` failure as stale process drift.
