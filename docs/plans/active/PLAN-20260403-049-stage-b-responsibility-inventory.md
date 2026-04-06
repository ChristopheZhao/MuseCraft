# Stage B Responsibility Inventory: PLAN-20260403-049

## Scope
- Inventory the current orchestrator/runtime responsibilities after the `045` repair.
- Classify each concern as `keep`, `move-behind-facade`, or `diagnostics-only`.
- Record a lease/liveness surface verdict before any Stage C bounded slice is proposed.

## Inventory Verdict Summary
- `keep`: workflow coordination, agent selection/order, context preparation, explicit runtime-boundary decision evaluation, and workflow completion publication.
- `move-behind-facade`: multi-step runtime attempt/gate/continuation/lease transition choreography that currently lives inline in `OrchestratorAgent`.
- `diagnostics-only`: queue/worker/bootstrap receipts, keepalive diagnostics, queue statistics, and other transport health signals.

## Responsibility Inventory

| Concern | Current surface | Current owner | Verdict | Rationale |
| --- | --- | --- | --- | --- |
| Candidate-agent selection, task decomposition, execution-queue ordering | `OrchestratorAgent._llm_select_candidate_agents`, `_llm_decompose_tasks`, `_build_execution_queue` | Orchestrator | keep | This is workflow coordination and should remain above runtime authority surfaces |
| Context assembly, runtime input preparation, and pre-dispatch policy checks | `OrchestratorAgent._prepare_scheduled_agent_input`, `_ensure_dispatch_prerequisites`, queue policy helpers | Orchestrator plus policy/helper services | keep | These are coordination and boundary-policy concerns, not runtime truth mutations |
| Runtime resume checkpoint loading and script-state resolution | `OrchestratorAgent._resolve_runtime_script_state`, `_load_authoritative_resume_task_specs`, direct `RuntimeSessionService.load_active_*_continuation_sync` calls | Orchestrator currently | move-behind-facade | The orchestrator should consume an explicit resume decision/result, not own low-level continuation/gate retrieval choreography |
| Attempt bootstrap sequence | `_start_runtime_attempt` calling `start_node_attempt_sync`, `bind_attempt_continuation_checkpoint_sync`, `grant_attempt_lease_sync`, `clear_node_diagnostic_codes_sync` | Orchestrator currently | move-behind-facade | This is a control-plane transition bundle and should be one dedicated facade/service call |
| Attempt completion and failure transitions on fresh sessions | `_complete_runtime_attempt_with_fresh_session`, `_fail_runtime_attempt_with_fresh_session` | Orchestrator currently | move-behind-facade | Fresh-session runtime transitions are control-plane semantics, not orchestrator semantic ownership |
| Script attempt completion plus review-gate opening | `_open_script_review_gate` and `RuntimeSessionService.complete_script_attempt_and_open_review_gate_sync` | Orchestrator currently coordinates both boundary publication and gate transition | move-behind-facade | A later facade should own the control-plane transaction sequence while the orchestrator only reacts to the returned gate outcome |
| Whole-session completion / failure mutation | direct `RuntimeSessionService.mark_session_completed_sync` and `mark_session_failed_sync` from `_execute_impl` | Orchestrator currently | move-behind-facade | Runtime session closure remains control-plane truth and should be requested through a narrower runtime facade |
| Runtime-boundary decision evaluation after agent output | `_evaluate_runtime_boundary_cycle`, `OrchestrationControlPlane`, `OrchestrationProtocol`, `OrchestrationRuntimeController` | Orchestrator plus orchestration services | keep | This is bridge coordination, provided it stays policy/event driven and does not become the owner of runtime state persistence |
| Worker bootstrap and event-loop setup | `prepare_queued_execution_host`, `run_generation_in_host` | Queued execution host | keep | Worker-local host bootstrap is execution-container responsibility and belongs outside the queue adapter itself |
| Host-side keepalive loop and heartbeat publication | `AttemptLeaseKeepaliveController`, `execution_host_lease.py` | Execution host / keepalive controller | keep | The host is the liveness event-source only; it must not own lease truth, but it should keep producing heartbeat events and generic health signals |
| Keepalive diagnostics persisted into runtime node diagnostics | `_publish_keepalive_diagnostic` in `queued_task_execution_host.py`, `RuntimeSessionService.upsert_attempt_node_diagnostic_sync` | Worker host writing into control-plane diagnostics | diagnostics-only | These receipts are useful evidence but are not themselves runtime authority |
| Frontend runtime projection and gate-decision ingress | `tasks.py` runtime endpoints and `RuntimeSessionService.build_runtime_view_for_task_sync` | API projection layer | keep | Frontend should consume explicit projections and write only through explicit API actions, not infer authority from queue or artifact signals |

## Lease / Liveness Surface Verdict

### Acceptable surfaces
- `RuntimeSessionService` remains the only authority for lease issuance, heartbeat validation, expiry, release, attempt completion/failure validation, gate state, and session status.
- `AttemptLeaseKeepaliveController` may continue to own host-side heartbeat production and worker-local unhealthy-state memory.
- Runtime node diagnostics such as `execution_host_keepalive_*` receipts are acceptable as diagnostics and RCA evidence only.
- A generic host-liveness probe is acceptable only if it stays generic to execution health and does not expose lease tokens or lease-owner semantics to tools/sub-agents.

### Surfaces that should be reduced
- Orchestrator direct ownership of keepalive activation/deactivation and activation-failure choreography.
- Orchestrator inline sequencing of attempt start + continuation bind + lease grant + diagnostic clearing.
- Orchestrator direct fresh-session completion/failure/gate-opening helpers.

### Diagnostics-only surfaces
- Queue task IDs, Celery worker status, event-bus reset, route selection, and queue statistics.
- `execution_host_keepalive_activation_requested`, `first_heartbeat_ack`, `heartbeat_begin`, `heartbeat_end`, `deactivated`, and `completion_validation_failed` receipts.

### Explicit non-authority surfaces
- Broker state, worker liveness, websocket progress, artifact existence, published-deliverable presence, and frontend polling state are not runtime authority.
- SQLite behavior is not production architecture evidence for lease ownership or completion authority.

### Current repo fact that matters for Stage C planning
- `assert_current_execution_host_keepalive_healthy()` is defined in `execution_host_lease.py` and covered in tests, but the current application code search did not find a product-code caller outside the keepalive module itself.
- That means the repo already has a generic liveness-probe shape available, but it is not yet a live product-path contract in the current mainline.
- If a future slice chooses to wire this probe into long-running tool/provider loops, that slice must remain generic to cancellation/liveness and must not leak lease tokens, lease owners, or queue semantics into tool code.

## Stage B Verify Gate
- [x] A written responsibility inventory exists and each listed concern has an explicit `keep` / `move-behind-facade` / `diagnostics-only` verdict.
- [x] A written lease/liveness surface verdict exists for execution/tool paths.
- [x] The inventory preserves `045` as closed and does not reopen the runtime defect repair itself.
- [x] The inventory keeps `047` separate and does not absorb image-composer scope.
- [x] The inventory does not move runtime truth into queue, broker, websocket, artifact status, or frontend state.

## Current Worktree Boundary
- In-scope for `049` right now:
  - `docs/plans/active/PLAN-20260403-049.md`
  - `docs/plans/active/PLAN-20260403-049-validation.md`
  - `docs/plans/active/PLAN-20260403-049-stage-a-governance-freeze.md`
  - `docs/plans/active/PLAN-20260403-049-stage-b-responsibility-inventory.md`
- Explicitly out-of-scope dirty changes that must be left untouched by `049` execution:
  - `backend/app/agents/tools/image_prompt_composer_tool.py`
  - `backend/tests/unit/test_consistency_asset_contract_v2.py`
  - `backend/tests/unit/test_image_prompt_normalization.py`
  - `docs/plans/active/PLAN-20260402-047-validation.md`
  - `docs/plans/active/PLAN-20260402-047.md` deletion and the matching archive / handoff artifacts
  - `docs/plans/PLAN_INDEX.json` unless a later governance action explicitly requires lifecycle synchronization
- Operational rule for the next slice:
  - Stage C must target runtime/control-plane slimming only and must avoid the image-prompt / `047` closure diff set entirely.
  - If a future `049` step needs `PLAN_INDEX.json`, that should be a deliberate governance action rather than incidental plan churn during implementation.

## Evidence Refs
- `docs/plans/active/PLAN-20260403-049-stage-a-governance-freeze.md`
- `backend/app/agents/orchestrator.py`
- `backend/app/services/runtime_session_service.py`
- `backend/app/services/execution_host_lease.py`
- `backend/app/services/queued_task_execution_host.py`
- `backend/app/services/task_queue.py`
- `backend/app/api/v1/endpoints/tasks.py`
