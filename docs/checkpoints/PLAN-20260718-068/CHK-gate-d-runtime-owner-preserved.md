# Gate D Runtime Owner Preserved

- Timestamp: `2026-07-19T05:20:57+08:00`
- Status: pass
- Scope: Slice D runtime store separation, legacy aggregate removal, and cross-path runtime ownership

## Expected Outcomes Checked

- [x] MAS runtime/session/node/attempt/gate/decision semantics remain in database-independent control-plane services.
- [x] SQLAlchemy is isolated behind capability-oriented stores that execute typed commands with explicit expected and target facts.
- [x] Runtime bootstrap, attempt lease, gate decision, continuation, terminal transition, reconciliation, and deliverable publication fail closed on missing or stale facts.
- [x] API runtime projections consume immutable read models and do not mutate or repair runtime state.
- [x] Queue, execution-host, and maintenance-script paths do not infer, create, or advance runtime truth outside application/control-plane boundaries.
- [x] Lease expiry and stale state surface typed `RuntimeStoreError` reason codes; tests no longer depend on string-only `ValueError` behavior.
- [x] Published payload and continuation boundaries retain strict normalization and explicit diagnostics.
- [x] `RuntimeSessionService` and its compatibility-only tests are removed; no production or test caller imports the deleted service.
- [x] The exact transitional runtime SQL/ORM persistence debt is empty.
- [x] The store protocol advertises only implemented capabilities; the unused `transition_node` contract is removed.

## Evidence

- Expanded architecture/runtime/API/queue regression: `215 passed, 2 warnings`.
- Core Gate D runtime/architecture regression: `99 passed, 2 warnings`.
- Direct replacement tests cover cancellation lease invalidation and same-attempt keepalive diagnostic replacement.
- Migrated focused suites: execution boundary `13 passed`; published deliverable `10 passed`; threaded lease RCA `3 passed`.
- Focused mypy: no issues in `runtime_store.py`, domain exports, and the stale-runtime maintenance entrypoint.
- Black and isort checks: pass for all changed Python files.
- `git diff --check`: pass.
- Full backend search found no import or call reference to `runtime_session_service`, `RuntimeSessionService`, `RuntimeNodeTransitionCommand`, or `.transition_node(...)`; architecture-only forbidden-name assertions remain intentionally.
- Existing warnings are SQLAlchemy `as_declarative` and Pydantic class-config deprecations.

## Expectation Check

The completed work matches the intended Slice D boundary. Decision ownership did not move into SQLAlchemy adapters, schedulers, read models, memory, or maintenance scripts. Removing the aggregate service reduced the surface instead of adding a compatibility shim, and the zero-debt ratchet prevents its reintroduction.

This verdict closes P0-F and Gate D only. It does not claim database composition/profile cleanup, PostgreSQL concurrency evidence, uv startup acceptance, or full-repository test health; those remain assigned to Slice E/F and P0-G/P0-H/P1-C.

## Recorded Follow-up

- `backend/scripts/extract_video_last_frame.py` contains a pre-existing syntax error discovered when an initial guard attempted to parse every maintenance script as Python. Gate D uses exact source checks for the scripts tree and AST checks for API/services, so this unrelated script debt is visible but does not weaken the runtime ownership assertion.
