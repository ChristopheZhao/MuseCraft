# Validation Ledger: PLAN-20260403-050

## Scope
- Validate the bounded `C2` follow-on after `PLAN-20260403-049` closeout.
- Keep runtime/control-plane authority in `RuntimeSessionService` while reducing orchestrator ownership of runtime resume/load/bootstrap choreography.
- Keep keepalive/liveness redesign, queue transport, and post-execution transition work outside this plan unless a later amendment says otherwise.

## Execution Order
- Stage A boundary review must freeze target files, non-goals, and validation claims before code changes begin.
- Stage B implementation may start only after the dedicated-facade vs widened-facade decision is written down.
- Stage C validation must label evidence as SQLite-bounded or MySQL-authoritative explicitly; no silent upgrade of evidence strength is allowed.

## Acceptance Gates
### Stage A: boundary gate
- [x] A written target-file list exists and is limited to `orchestrator.py`, one dedicated service/facade file, and focused runtime-mainline tests
- [x] A written non-goal list exists for `runtime_session_service.py`, lease/queued-host modules, keepalive/liveness redesign, post-execution transition rewiring, and `045`/`047` reopen
- [x] A written decision exists on whether `C2` gets a dedicated facade/service instead of widening the existing `C1` transition facade

### Stage B: implementation gate
- [x] The selected resume/load/bootstrap choreography no longer lives inline in orchestrator
- [x] `RuntimeSessionService` remains the sole authority for runtime/session/node/attempt/gate/decision truth
- [x] No queue/broker/websocket/artifact shortcut is introduced as runtime authority
- [x] No keepalive/lease redesign is absorbed accidentally

### Stage C: targeted validation gate
- [x] `python3 -m py_compile` or equivalent passes for every touched target file
- [x] Focused runtime-mainline tests cover the extracted resume/load/bootstrap seam
- [x] Every recorded result states whether it is SQLite-bounded only or MySQL-authoritative

## Automated Checks
- [x] Targeted compile checks exist for touched files
- [x] Focused unit tests exist for the extracted orchestration seam

## Manual Checks
- [x] Review the resulting owner split and confirm resume/load/bootstrap choreography has one orchestration-facing owner
- [x] Review the changed facade/service and confirm it did not absorb keepalive/liveness or post-execution transition responsibilities by accident

## QC Rules
- `RuntimeSessionService` remains the sole runtime-control-plane authority.
- Queue, broker, websocket, and artifact state remain diagnostics/projection only.
- Keepalive/liveness redesign is out of scope unless an amendment reopens it explicitly.
- No new compatibility layer may preserve a known-bad authority split.
- Runtime persistence and MAS/agent memory are separate owner layers even when both use SQL-backed storage.
- Memory backend evidence does not substitute for runtime transaction-semantic evidence.

## Evidence Log
- 2026-04-03T13:55:22Z validation ledger created for the dedicated `C2` follow-on after `049` closeout.
- 2026-04-03T13:55:22Z initial acceptance boundary frozen to orchestrator runtime resume/load/bootstrap slimming only; post-execution transitions, keepalive/liveness redesign, and queue-host semantics remain outside this plan by default.
- 2026-04-03T14:24:41Z Stage A boundary gate passed via `PLAN-20260403-050-stage-a-boundary-freeze.md`; the exact helper/call-path inventory, dedicated new resume/bootstrap facade decision, and frozen target/non-target/validation set are now recorded before any runtime implementation.
- 2026-04-03T14:53:04Z Stage B implementation gate passed: the pre-execution seam moved into `backend/app/services/orchestration_runtime_resume_bootstrap_facade.py`, `backend/app/agents/orchestrator.py` no longer owns inline helper methods for runtime script-state resolution, authoritative script continuation load, or attempt bootstrap/start sequencing, and `RuntimeSessionService` remains the sole runtime authority.
- 2026-04-03T14:53:04Z Stage C targeted validation passed with SQLite-bounded unit evidence only: `python3 -m py_compile backend/app/agents/orchestrator.py backend/app/services/orchestration_runtime_resume_bootstrap_facade.py backend/tests/unit/test_orchestrator_runtime_mainline.py` succeeded, and focused runtime-mainline unit functions were executed directly under `backend/.venv/bin/python` for the extracted seam plus adjacent transition regressions because repo-local pytest startup was not reliable in the current shell context.
- 2026-04-03T14:58:44Z Owner-boundary follow-up passed with SQLite-bounded unit evidence: `test_runtime_resume_bootstrap_facade_uses_caller_owned_session` confirmed the new pre-execution facade uses the caller-owned current SQLAlchemy session, while `test_runtime_transition_facade_opens_fresh_session` continued to prove fresh-session reopening remains owned by the post-execution transition facade.
- 2026-04-04T02:00:23Z Architecture freeze follow-up recorded in `PLAN-20260403-050-runtime-memory-sql-boundary-freeze.md`: runtime control-plane persistence, MAS/agent memory application, and SQL physical substrate are now explicitly separated, and the admissible-evidence matrix now distinguishes runtime SQL proofs from memory-backend proofs before any follow-on SQL design proceeds.
