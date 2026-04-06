# Stage A Governance Freeze: PLAN-20260403-049

## Scope
- Freeze the governance boundary for the `049` successor stream before any refactor slice is proposed.
- Confirm that `049` is a review-first control-plane governance pass after `045`, not a reopen of the `execution lease expired` repair itself.
- Keep `047` closed/reference-only and out of this stream.

## Review Conclusion
- `PLAN-20260403-049` remains valid as the active follow-up after `045`.
- Current code confirms that runtime/session/node/attempt/gate/decision truth still belongs to `RuntimeSessionService`, but `OrchestratorAgent` still carries a thick bridge layer around attempt bootstrap, lease activation, fresh-session completion/failure transitions, and script-gate opening.
- `queued_task_execution_host` and `execution_host_lease` are currently worker/bootstrap and host-liveness surfaces only; they do not own runtime truth.
- The next safe step is therefore boundary clarification and bridge slimming, not another runtime defect patch or queue-centric redesign.

## Exact Deliverables
- D1. A runtime/business/queue/frontend SoT owner matrix with explicit authority owner, write surface, consumer surface, and prohibited authority shortcuts.
- D2. An orchestrator target-role note that states the intended steady-state role after `045`: coordinator / bridge only, not runtime-truth owner, not queue-authority owner, and not business-fact owner.
- D3. A MySQL-authoritative vs SQLite-bounded runtime test-boundary note that states which runtime claims require MySQL transaction semantics and which checks may remain SQLite-bounded only.

## Verify Gate
- [x] Review confirms MySQL/runtime persistence remains the runtime-control-plane SoT rather than a duplicate SoT.
- [x] Review confirms queue/worker/broker remain transport-only and do not gain runtime authority.
- [x] Review confirms MAS/business-fact stores remain distinct from runtime-control-plane authority.
- [x] Review confirms `047` remains closed/reference-only and is not absorbed into this stream.
- [x] The three Stage A artifacts exist in this note before any Stage B inventory or Stage C slice selection.

## Artifact D1: SoT Owner Matrix

| Surface | Authority owner | Primary write surface | Primary consumers | Prohibited shortcuts |
| --- | --- | --- | --- | --- |
| Runtime / control plane | `RuntimeSessionService` over `WorkflowSession`, `WorkflowNodeState`, `WorkflowNodeAttempt`, `WorkflowGate`, and `WorkflowGateDecision` | Control-plane mutations such as `start_node_attempt_sync`, `grant_attempt_lease_sync`, `heartbeat_attempt_lease_sync`, `complete_node_attempt_sync`, `fail_node_attempt_sync`, `complete_script_attempt_and_open_review_gate_sync`, `submit_gate_decision_sync`, `mark_session_completed_sync`, and `mark_session_failed_sync` | `OrchestratorAgent`, task API runtime endpoints, runtime read-model builders, queue execution-eligibility checks | Queue status, worker liveness, broker state, websocket progress, artifact existence, or MAS working memory must not be treated as runtime authority |
| Business facts / deliverable facts | MAS working-memory facts plus approved deliverable carriers in the business layer; runtime may reference them but does not own them | Agent/business writes through MAS memory services, published-deliverable helpers, and boundary-specific business adapters | Downstream agents, review surfaces, delivery/publishing flows, context assembly | Business facts must not be promoted into runtime/session/node/attempt/gate/decision truth; artifact or deliverable presence is not a runtime completion substitute |
| Queue / worker / execution host transport | Queue adapter and worker host bootstrap own dispatch transport and host-local lifecycle only | `TaskQueueService.queue_task`, `sync_process_video_task`, `prepare_queued_execution_host`, `run_generation_in_host`, worker-local keepalive controller setup | Queue stats, worker logs, route selection, execution host bootstrap | Queue or worker state must not become the source of truth for runtime node status, attempt ownership, gate state, or resume eligibility |
| Frontend / read-model projection | API projection layer that reads authoritative runtime/business facts; frontend has no direct authority ownership | `RuntimeSessionService.build_runtime_view_for_task_sync` and task runtime endpoints return projection payloads; frontend writes only through explicit API actions such as gate decisions | UI polling, human-review actions, status display, operator diagnostics | Frontend must not infer runtime truth from queue lag, websocket silence, or artifact presence, and it must not invent a second runtime state machine |

## Artifact D2: Orchestrator Target Role Note
- Intended role:
  - select / order agents, prepare agent context, and coordinate workflow progress
  - invoke control-plane and boundary services as a coordinator
  - react to explicit runtime boundary outcomes, human-review outcomes, and business-agent results
  - publish workflow-completion events and task-facing progress
- Explicit non-ownership:
  - does not own attempt lease truth, lease expiry truth, or heartbeat truth
  - does not own queue / worker authority or infer runtime truth from transport health
  - does not own business-fact truth outside the existing MAS memory / deliverable write surfaces
  - must not expose lease tokens, lease owners, or queue semantics to sub-agents or tools as business decisions
- Current gap confirmed in code:
  - orchestrator still directly sequences runtime attempt bootstrap, continuation checkpoint binding, lease grant, keepalive activation/deactivation, fresh-session attempt completion/failure, and script review gate opening
  - those responsibilities are bridge choreography, not semantic authority, and should become the primary slimming target in later stages

## Artifact D3: MySQL-Authoritative vs SQLite-Bounded Test Boundary
- MySQL-authoritative checks:
  - any claim about completion/failure validation observing the latest lease state across multiple DB sessions
  - any claim about stale-read prevention under long-lived vs short-lived control-plane sessions
  - any claim about heartbeat visibility, lease expiry, or gate/attempt transition correctness that depends on production transaction isolation semantics
  - replay evidence used to justify runtime architecture or lease-authority changes
- SQLite-bounded checks:
  - single-session node / attempt / gate / decision state transitions that do not depend on MySQL isolation
  - diagnostic upsert semantics, receipt shaping, queue bootstrap wiring, and basic controller-loop behavior
  - unit tests that prove orchestration flow, failure surfacing, or helper behavior without claiming production-equivalent concurrency semantics
- Invalid evidence patterns:
  - using SQLite locking, writer serialization, or thread-local behavior as proof that queue/worker should own runtime truth
  - using SQLite-only observations to justify changes to runtime lease authority, session freshness, or completion semantics
  - treating a passing SQLite unit harness as sufficient proof for MySQL control-plane freshness questions

## Evidence Refs
- `docs/plans/active/PLAN-20260403-049.md`
- `docs/plans/active/PLAN-20260403-049-validation.md`
- `docs/plans/active/PLAN-20260401-045.md`
- `docs/plans/active/PLAN-20260401-045-validation.md`
- `backend/app/agents/orchestrator.py`
- `backend/app/services/runtime_session_service.py`
- `backend/app/services/execution_host_lease.py`
- `backend/app/services/queued_task_execution_host.py`
- `backend/app/services/task_queue.py`
- `backend/app/api/v1/endpoints/tasks.py`
