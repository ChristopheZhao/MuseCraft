# Slice D Terminal/Read-Model Checkpoint

- Timestamp: `2026-07-19T02:49:09+08:00`
- Status: partial pass; Gate D remains open
- Scope: runtime session terminal transitions, resume, runtime projection, queue eligibility, and stale-runtime reconciliation

## Expected Outcomes Checked

- [x] Session transitions carry explicit expected and target session/node/attempt/task facts.
- [x] Completion cannot silently leave a running attempt or active lease.
- [x] Failure and cancellation explicitly invalidate the current attempt lease.
- [x] Resume eligibility is computed from committed immutable records and is revalidated before mutation.
- [x] Runtime API projections expose public task identity and no ORM row or database task identity.
- [x] Queue eligibility reads authoritative runtime status without owning or inferring runtime transitions.
- [x] Reconciliation is an explicit maintenance entrypoint; read paths never repair runtime state.
- [x] Production callers do not use legacy runtime projection or terminal mutation methods.
- [ ] Published-deliverable persistence uses the runtime store boundary.
- [ ] Context assembly no longer owns runtime SQL/ORM transitions.
- [ ] Legacy `RuntimeSessionService` projection/terminal methods are removed after remaining callers/tests migrate.
- [ ] Slice D architecture ratchet reaches zero.

## Evidence

- Focused runtime/API/queue/orchestrator/architecture regression: `138 passed, 2 warnings`.
- Focused mypy: success for eight domain, infrastructure, control-plane, queue, and policy files with third-party missing-import stubs ignored; the only unignored failure was the existing untyped `celery.result` package.
- Black check: 12 new or fully refactored files unchanged.
- `git diff --check`: pass.
- Warnings are the existing SQLAlchemy `as_declarative` and Pydantic class-config deprecations.

## Remaining Boundary

The checkpoint does not close P0-F or Gate D. `published_deliverable_service.py`, `context_assembler.py`, and transitional runtime creation/node helpers in `runtime_session_service.py` still own SQL/ORM behavior. `orchestration_runtime_transition_facade.py` and `orchestration_runtime_resume_bootstrap_facade.py` also remain on the architecture debt ratchet until those persistence calls are moved behind complete store capabilities.
