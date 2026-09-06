# Slice D Resume/Bootstrap Checkpoint

- Timestamp: `2026-07-19T04:11:37+08:00`
- Status: partial pass; Gate D remains open
- Scope: continuation validation, script-approval consumption, attempt bootstrap, lease establishment, and node-diagnostic cleanup

## Expected Outcomes Checked

- [x] Resume reads consume immutable runtime records through a capability-oriented store.
- [x] Continuation checkpoints are validated at the control-plane boundary and stale attempt, gate, or decision bindings fail closed with typed reason codes.
- [x] Script approval consumption applies session, node, task, and anchor transitions atomically through one explicit command.
- [x] Attempt bootstrap establishes the attempt, continuation checkpoint, lease, and diagnostic cleanup in one transaction.
- [x] Diagnostic cleanup uses an expected status and expected diagnostics snapshot so concurrent writes cannot be silently overwritten.
- [x] A scheduled Agent without a runtime-node mapping, or an attempt without a lease token, fails explicitly instead of executing outside Runtime SoT.
- [x] The resume/bootstrap facade no longer imports runtime ORM models or delegates semantics to `RuntimeSessionService`.
- [x] The architecture ratchet dropped from two transitional SQL/ORM owners to one.
- [ ] API runtime-session creation uses the capability store/control-plane boundary.
- [ ] Queued dispatch preparation/failure and keepalive diagnostics no longer call `RuntimeSessionService`.
- [ ] The legacy runtime persistence surface is removed and the Slice D architecture ratchet reaches zero.

## Evidence

- Focused resume/bootstrap, store, orchestrator, context, and architecture regression: `61 passed, 2 warnings`.
- Focused mypy: success for five domain, SQL adapter, resume control-plane/facade, and orchestrator files.
- Black check: nine substantively edited Python files unchanged; the historical `orchestrator.py` file was intentionally excluded because this slice changes one call-site line only.
- Isort check: the same nine substantively edited Python files passed.
- `git diff --check`: pass.
- Warnings are the existing SQLAlchemy `as_declarative` and Pydantic class-config deprecations.

## Expectation Check

This subtask achieved its intended result. Resume semantics are database-independent policy, the SQL adapter only persists explicit commands, malformed or stale continuation state fails closed, and bootstrap cannot silently proceed without a complete authoritative lease scope. This is not a Gate D completion claim: runtime-session creation, queued dispatch/failure, and keepalive diagnostics still enter the legacy persistence service.

## Remaining Boundary

`tasks.py`, `queued_execution_use_case.py`, and `runtime_attempt_keepalive_adapter.py` remain production callers of `RuntimeSessionService`. `runtime_session_service.py` is the sole item left on the architecture ratchet and still combines runtime creation/node persistence with legacy helpers. These callers and the residual service surface must migrate before P0-F or Gate D can close.
