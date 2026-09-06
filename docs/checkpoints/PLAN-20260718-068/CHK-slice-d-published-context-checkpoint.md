# Slice D Published-Deliverable/Context Checkpoint

- Timestamp: `2026-07-19T03:36:26+08:00`
- Status: partial pass; Gate D remains open
- Scope: published-deliverable contracts and persistence, script-review context assembly, transition-facade runtime access, and payload-file compensation

## Expected Outcomes Checked

- [x] Published-deliverable publication and approval use immutable records, capability ports, explicit preconditions, and typed store conflicts.
- [x] `ContextContractAssembler` only assembles the script-review draft and performs no SQL/ORM mutation.
- [x] Script-review publication is owned by a control-plane service and is committed with attempt/gate transitions in one database transaction.
- [x] The transition facade consumes immutable runtime records and public task identity rather than ORM session/task rows.
- [x] Published payload loads return a strict JSON object contract with typed reason codes.
- [x] Published references reject unknown/missing keys and malformed collections instead of treating invalid state as absent.
- [x] Payload files use unique atomic writes and are explicitly discarded when publication or the enclosing runtime transition fails.
- [x] The architecture ratchet dropped from five transitional SQL/ORM owners to two.
- [ ] Resume/bootstrap reads and continuation consumption use immutable store/control-plane capabilities only.
- [ ] Remaining runtime creation/node helpers are removed from the legacy `RuntimeSessionService` persistence surface.
- [ ] Slice D architecture ratchet reaches zero.

## Evidence

- Focused runtime/store/orchestrator/context/deliverable/architecture regression: `168 passed, 2 warnings`.
- Focused mypy: success for eight domain, SQL adapter, context, resume/transition facade, payload, and control-plane files with third-party missing-import stubs ignored.
- Black check: 17 edited Python files unchanged after formatting.
- Isort check: edited Python imports sorted after one bounded remediation.
- `git diff --check`: pass.
- Warnings are the existing SQLAlchemy `as_declarative` and Pydantic class-config deprecations.

## Expectation Check

The completed subtask matches its intended boundary: Agents and ContextAssembler do not receive a database session; store adapters validate facts but do not select orchestration actions; malformed published state fails closed; and external file side effects have explicit compensation. This check does not close Gate D because resume/bootstrap and legacy runtime creation/node persistence remain on the executable debt ratchet.

## Remaining Boundary

`orchestration_runtime_resume_bootstrap_facade.py` still loads ORM rows and delegates continuation consumption/diagnostic mutation to `RuntimeSessionService`. `runtime_session_service.py` remains the second ratchet item for runtime creation and node helpers. Those two owners must migrate before P0-F or Gate D can be marked complete.
