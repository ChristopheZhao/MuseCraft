# Slice D Runtime Bootstrap/Caller Checkpoint

- Timestamp: `2026-07-19T04:46:17+08:00`
- Status: partial pass; Gate D remains open
- Scope: runtime-session bootstrap, API create/retry, queued dispatch/failure, and keepalive diagnostics

## Expected Outcomes Checked

- [x] Runtime-session creation uses a database-independent control plane and a narrow store capability.
- [x] Session creation carries expected task status and expected latest-session ID, so concurrent or stale creates fail closed.
- [x] Task creation and its initial quick runtime graph commit in one API transaction.
- [x] Retry requires an existing authoritative runtime and creates the next session against an explicit latest-session precondition.
- [x] Quick queued dispatch never creates runtime state and refuses transport dispatch when the authoritative runtime is missing.
- [x] Queued quick failures transition through `RuntimeSessionControlPlane`; transport/application code does not select ORM runtime mutations.
- [x] Keepalive diagnostics persist through the typed attempt store and surface missing/stale attempt errors instead of silently returning.
- [x] No production API/service caller outside the legacy file references `RuntimeSessionService`.
- [ ] The residual `runtime_session_service.py` persistence surface and its legacy tests are removed.
- [ ] The Slice D architecture ratchet reaches zero.

## Evidence

- Combined runtime-store, API, queue, keepalive, resume/orchestrator, and transport regression: `95 passed, 2 warnings`.
- Focused mypy: success for five domain, SQL adapter, bootstrap, keepalive, and queued-execution files.
- Standalone `tasks.py` mypy still reports 49 pre-existing SQLAlchemy declarative-stub errors across the endpoint's ORM response mapping and original `Task(...)` construction. The new bootstrap helper did not add a distinct error, and this debt is not counted as passing evidence.
- Black check covers the 11 new or substantively normalized Python files. The historically non-Black `tasks.py` endpoint is excluded to avoid unrelated whole-file churn.
- Isort covers all 12 modified Python files.
- `git diff --check`: pass.
- Warnings are the existing SQLAlchemy `as_declarative` and Pydantic class-config deprecations.

## Expectation Check

This subtask achieved its intended result. Runtime creation decisions are control-plane policy, persistence is guarded by explicit expected facts, the scheduler path cannot create or infer runtime truth, and keepalive diagnostics use a typed persistence capability. Gate D remains open because the unused production legacy service still exists under `app/services` and the architecture ratchet intentionally remains at one until that surface and its tests are removed.

## Remaining Boundary

`runtime_session_service.py` has no production callers but still contains the former SQL/ORM implementation and is heavily used by legacy tests as a fixture and compatibility surface. The next subtask must migrate those tests to capability stores/control planes, remove the file rather than archive or wrap it, and change the exact ratchet expectation from one to zero.
