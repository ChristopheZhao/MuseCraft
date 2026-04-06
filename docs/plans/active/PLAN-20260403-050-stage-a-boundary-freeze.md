# Stage A Boundary Freeze: PLAN-20260403-050

## Scope
- Freeze the bounded `050` follow-on before any runtime implementation starts.
- Confirm that `050` is limited to orchestrator resume/load/bootstrap slimming after `049/C1`, not a reopen of `049`, `045`, or `047`.
- Convert the current prose-only scope into an exact extraction contract with explicit targets, non-targets, and verification claims.

## Review Conclusion
- `PLAN-20260403-050` remains the correct active stream after `049` closed, and its intended seam is still narrow enough to stay bounded.
- The current code confirms the remaining orchestrator thickness is concentrated in three pre-execution helpers / call paths only:
  - `_resolve_runtime_script_state(...)`
  - `_load_authoritative_resume_task_specs(...)`
  - `_start_runtime_attempt(...)`
- The existing `OrchestrationRuntimeTransitionFacade` is explicitly a post-execution, fresh-session transition boundary. It should remain that boundary and should not absorb pre-execution resume/bootstrap ownership by default.
- The next safe step is therefore a dedicated resume/bootstrap facade/service extraction. Keepalive activation/deactivation, lease/liveness redesign, queue-host behavior, and post-execution transitions stay frozen out of scope for `050`.

## Exact Deliverables
- D1. A precise target helper / call-path inventory for the three frozen orchestrator seams and their direct downstream consumers.
- D2. A written owner-boundary decision for `dedicated new facade/service` vs `minimal adjustment to existing facade`.
- D3. A frozen target-file, non-target, and targeted-validation contract for Stage B and Stage C.

## Verify Gate
- [x] The exact target helper / call-path inventory exists and is limited to resume/load/bootstrap choreography only.
- [x] A written decision exists that selects a dedicated new resume/bootstrap facade/service and rejects widening `OrchestrationRuntimeTransitionFacade` by default.
- [x] The target-file list, non-target list, and targeted validation claims are written down before runtime implementation begins.
- [x] This round touched plan/governance artifacts only; no runtime implementation file was edited.

## Artifact D1: Exact Target Helper / Call-Path Inventory

| Seam | Current entrypoint | Direct calls / owned steps | Current downstream consumers | Frozen extraction boundary | Explicit non-target adjacency |
| --- | --- | --- | --- | --- | --- |
| Runtime script-state resolution | `_execute_impl(...)` pre-queue bootstrap branch | `_resolve_runtime_script_state(...)` -> `RuntimeSessionService.get_or_create_session_for_task_sync(...)` -> `RuntimeSessionService.get_latest_gate_for_node_sync(...)` -> `RuntimeSessionService.get_latest_decision_for_gate_sync(...)` | early `waiting_gate` return; `script_resume_action` branch selection; script review-contract injection | Move the full `runtime_session + script_gate + latest_decision + resume_action` resolution behind the new resume/bootstrap facade/service so orchestrator consumes a single reviewable result instead of direct gate/decision loading | Do not absorb gate submission, gate opening, queue scheduling, websocket status, or artifact presence checks |
| Authoritative script resume task-spec loading | `_execute_impl(...)` branch `if script_resume_action in {"approve", "revise"}` | `_load_authoritative_resume_task_specs(...)` -> `RuntimeSessionService.load_active_script_continuation_sync(...)` -> `RuntimeSessionService.load_active_continuation_sync(...)` -> `OrchestrationStateAdapter.checkpoint_to_task_specs(...)` plus local validation for missing task specs / candidate agents | `skip_agents` mutation; `execution_queue` build; `standby_agents` build; `consume_script_approval_continuation_sync(...)` call after approve | Move authoritative resume task-spec loading and validation behind the same new resume/bootstrap facade/service so orchestrator receives validated resume task-spec payloads rather than loading continuation state itself | Do not absorb approval-consumption mutation, planner/decompose logic, or any generic runtime decision evaluation beyond this continuation load |
| Attempt bootstrap / start sequencing | per-dispatch and retry path inside `_execute_impl(...)` | `_start_runtime_attempt(...)` -> `_runtime_node_key_for_agent(...)` -> `RuntimeSessionService.start_node_attempt_sync(...)` -> `OrchestrationStateAdapter.build_continuation_checkpoint(...)` -> `RuntimeSessionService.bind_attempt_continuation_checkpoint_sync(...)` -> `RuntimeSessionService.grant_attempt_lease_sync(...)` -> `RuntimeSessionService.clear_node_diagnostic_codes_sync(...)` | `_activate_runtime_attempt_keepalive_or_fail(...)`; later `complete_runtime_attempt(...)`, `open_script_review_gate(...)`, and `fail_runtime_attempt(...)` via existing post-execution facade | Move bootstrap/start sequencing behind the new resume/bootstrap facade/service so orchestrator receives `{node_key, attempt_id, trigger_reason, lease_token}` from one call instead of owning control-plane bootstrap choreography inline | Do not absorb keepalive activation/deactivation, keepalive-diagnostic shaping, retry policy, post-execution completion/failure/gate-opening, or lease/liveness redesign |

## Artifact D2: Boundary Owner Decision
- Verdict:
  - `050` gets one dedicated new orchestration-facing facade/service for pre-execution resume/load/bootstrap choreography.
  - Recommended target file and class seam:
    - file: `backend/app/services/orchestration_runtime_resume_bootstrap_facade.py`
    - class: `OrchestrationRuntimeResumeBootstrapFacade`
- Decision rationale:
  - The existing `OrchestrationRuntimeTransitionFacade` is already coherent around post-execution transitions and uses a fresh-session control-plane pattern. Pre-execution resume/bootstrap uses different lifecycle semantics and should not be layered into that class.
  - The target seam mixes continuation loading plus attempt bootstrap. That is still single-purpose if framed as `resume/bootstrap orchestration boundary`, but it becomes mixed-responsibility if combined with post-execution completion/failure/gate-opening in the same facade.
  - Keeping the pre-execution seam separate preserves the `049/C1` post-execution boundary and avoids building a new orchestration god-object.
  - The new facade/service may delegate to `RuntimeSessionService` and `OrchestrationStateAdapter`, but runtime/session/node/attempt/gate/decision truth must remain solely in `RuntimeSessionService`.
  - SQL/session ownership is also split explicitly:
    - pre-execution resume/bootstrap facade consumes the caller-owned current sync session only
    - it must not open, replace, or own fresh runtime DB sessions
    - post-execution fresh-session control-plane transitions remain owned by `OrchestrationRuntimeTransitionFacade`
- Rejected option:
  - `Minimal adjustment to existing facade` is rejected for Stage B by default because it would merge:
    - post-execution fresh-session transition ownership
    - pre-execution continuation loading
    - attempt bootstrap sequencing
  - That merge would widen the facade across two lifecycle phases and re-open the exact mixed-boundary problem `050` is supposed to reduce.

## Artifact D3: Target Files, Non-Targets, and Targeted Validation

### Frozen implementation targets for later stages
- `backend/app/agents/orchestrator.py`
- `backend/app/services/orchestration_runtime_resume_bootstrap_facade.py`
- `backend/tests/unit/test_orchestrator_runtime_mainline.py`

### Current round documentation targets
- `docs/plans/active/PLAN-20260403-050.md`
- `docs/plans/active/PLAN-20260403-050-validation.md`
- `docs/plans/active/PLAN-20260403-050-stage-a-boundary-freeze.md`
- `docs/plans/PLAN_INDEX.json`

### Frozen non-targets
- `backend/app/services/runtime_session_service.py`
- `backend/app/services/orchestration_runtime_transition_facade.py`
- `backend/app/services/execution_host_lease.py`
- `backend/app/services/queued_task_execution_host.py`
- keepalive / liveness redesign, lease policy redesign, queue-host bootstrap redesign, or post-execution runtime transition rewiring
- queue / broker / websocket / artifact existence as runtime authority
- any `045` reopen, any `047` image scope, and any attempt to reopen `049`

### Targeted validation contract for later stages
- Static / compile checks:
  - `python3 -m py_compile backend/app/agents/orchestrator.py backend/app/services/orchestration_runtime_resume_bootstrap_facade.py`
- Focused runtime-mainline tests in `backend/tests/unit/test_orchestrator_runtime_mainline.py` must cover:
  - script-approve resume loads authoritative task specs through the new resume/bootstrap facade/service and does not re-run planner/decompose
  - generic runtime resume from a persisted runtime checkpoint dispatches from the persisted anchor agent through the new facade/service
  - attempt bootstrap/start sequencing routes through the new facade/service and still returns the lease token consumed by keepalive activation plus the existing post-execution transition facade
  - resume/bootstrap facade uses the caller-owned current SQLAlchemy session instead of opening a fresh control-plane session
  - keepalive-unavailable failure remains a bounded failure path and does not pull keepalive redesign into the new facade/service
- Evidence labeling:
  - unit evidence from these tests is SQLite-bounded only
  - MySQL-backed evidence is required only if the actual implementation change extends into transaction-freshness or isolation-sensitive behavior, which Stage A does not authorize by default

## Evidence Refs
- `docs/session-handoff/SHO-20260403-0025.md`
- `docs/plans/active/PLAN-20260403-050.md`
- `docs/plans/active/PLAN-20260403-050-validation.md`
- `docs/plans/active/PLAN-20260403-049-stage-b-responsibility-inventory.md`
- `docs/plans/active/PLAN-20260403-049-stage-c-bounded-slice.md`
- `backend/app/agents/orchestrator.py`
- `backend/app/services/orchestration_runtime_transition_facade.py`
- `backend/app/services/runtime_session_service.py`
- `backend/app/services/execution_host_lease.py`
- `backend/app/services/queued_task_execution_host.py`
