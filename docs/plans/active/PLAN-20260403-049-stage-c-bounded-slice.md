# Stage C Bounded Slice Contract: PLAN-20260403-049

## Slice
- `C1`: Extract orchestrator post-execution runtime control-plane transitions behind one dedicated facade/service.

## Why This Boundary Exists
- Stage B confirmed the largest low-risk thickness inside `OrchestratorAgent` is not runtime truth ownership itself, but the inline choreography around fresh-session completion/failure/gate-opening/session-close transitions.
- This slice is narrow enough to reduce orchestrator thickness without touching the lease authority model, queue transport, or keepalive controller semantics established by `045`.
- A smaller slice than this would leave the main post-execution bridge split across ad hoc orchestrator helpers, while a larger slice would start mixing in bootstrap, keepalive, or queue-host concerns and would no longer be bounded.

## What This Slice Closes
- Replace direct orchestrator-owned post-execution runtime transition helpers with one explicit orchestration-facing facade boundary.
- Keep `RuntimeSessionService` as the single runtime authority while making orchestrator consume a narrower control-plane interface.
- Make the remaining Stage D implementation target evaluable without reopening `045` or absorbing `047`.

## Target Files
- [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py)
- One new dedicated orchestration/runtime facade service under [backend/app/services](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services)
- [test_orchestrator_runtime_mainline.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_orchestrator_runtime_mainline.py)

## Non-Targets
- [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) authority semantics, lease rules, transaction-freshness rules, or DB contract
- [execution_host_lease.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/execution_host_lease.py) keepalive loop, probe semantics, or diagnostics model
- [queued_task_execution_host.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/queued_task_execution_host.py) host bootstrap, keepalive controller setup, or worker event loop
- attempt bootstrap sequencing in orchestrator (`start_node_attempt_sync`, continuation bind, lease grant, diagnostic clearing)
- queue / broker / websocket / artifact / frontend read-model behavior
- any `047` / image-prompt files or `PLAN_INDEX.json`

## Proposed Facade Scope
- The new facade/service may own only post-execution control-plane choreography that orchestrator currently performs inline:
  - complete one runtime attempt through a fresh control-plane session
  - fail one runtime attempt through a fresh control-plane session
  - complete script attempt and open review gate through a fresh control-plane session
  - mark runtime session completed or failed through the same explicit boundary if needed to keep the slice coherent
- The facade/service must not:
  - reimplement runtime truth
  - duplicate lease validation logic
  - infer authority from queue, worker, websocket, or artifacts
  - expose lease tokens, lease owners, or DB transaction details to sub-agents or tools

## Done Signals
- `OrchestratorAgent` no longer owns bespoke helper methods for post-execution fresh-session completion/failure/gate-opening transitions.
- Those transitions are invoked through one dedicated facade/service with explicit method names and a narrow orchestrator-facing contract.
- Existing runtime behavior remains unchanged:
  - successful non-script attempts still end in normal runtime completion
  - script attempts still open the human review gate
  - failure paths still persist runtime diagnostics and session failure correctly
- `RuntimeSessionService` remains the only writer of runtime/session/node/attempt/gate/decision truth.

## Evidence Checklist
- Static diff shows `orchestrator.py` lost inline post-execution control-plane transition helpers rather than gaining new bridge logic elsewhere.
- New facade/service code delegates to `RuntimeSessionService` instead of recreating runtime semantics.
- Focused unit coverage proves orchestrator mainline still:
  - completes a normal runtime attempt
  - opens the script review gate on script completion
  - persists runtime failure via the narrowed facade
- No target-file diff touches `execution_host_lease.py`, `queued_task_execution_host.py`, or `RuntimeSessionService` authority rules.

## Negative Cases
- Invalid:
  - using this slice to also move attempt bootstrap, keepalive activation, or queue-host setup behind the same facade
  - adding compatibility shims that preserve both old orchestrator helpers and the new facade path in parallel
  - moving runtime truth or decision logic into the new facade instead of delegating to `RuntimeSessionService`
  - wiring tool/provider loops to lease semantics as part of this slice
- Stop condition:
  - if the facade cannot stay limited to post-execution transitions and starts needing runtime bootstrap or keepalive semantics, this slice is too wide and must be split before implementation

## Targeted Validation
- Focused unit tests:
  - `backend/tests/unit/test_orchestrator_runtime_mainline.py`
  - these tests are SQLite-bounded only and validate fresh-session facade wiring plus orchestrator/runtime contract behavior; they are not evidence for MySQL isolation semantics
- Optional spot checks only if implementation changes touch them indirectly:
  - `backend/tests/unit/test_runtime_session_service.py`
- Explicitly not part of this slice:
  - broad queue-host replay
  - MySQL live replay
  - any `047` image-prompt validation

## Next Owner Surface
- Stage D implementation may start only against this bounded slice contract.
- If implementation pressure expands beyond this contract, stop and write a new follow-on slice instead of widening `C1` in place.
