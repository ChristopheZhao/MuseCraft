# Slice D Attempt/Gate Checkpoint

- Timestamp: `2026-07-19T02:00:47+08:00`
- Status: partial pass; Gate D remains open
- Scope: runtime attempt, lease, continuation, completion/failure, diagnostics, gate open, and gate decision persistence boundaries

## Expected Outcomes Checked

- [x] Persistence adapter receives control-plane-selected preconditions and target facts.
- [x] Lease mismatch, expiry, stale heartbeat, and state races fail closed with typed reason codes.
- [x] Bootstrap start + continuation + lease is one transaction.
- [x] Script completion + candidate deliverable + review gate is one database transaction.
- [x] Gate decision create/apply binds the generated decision ID before commit.
- [x] Production code has no callers of legacy `RuntimeSessionService` attempt/gate mutation APIs.
- [x] Continuation execution order is independent of JSON object key order.
- [ ] Terminal session transitions use the store boundary.
- [ ] Runtime read models use an explicit query adapter.
- [ ] Published deliverable and context assembly SQL ownership is extracted.
- [ ] Slice D architecture ratchet reaches zero.

## Evidence

- Focused runtime/architecture regression: `103 passed, 2 warnings`.
- Focused mypy: success for nine domain, infrastructure, and control-plane files.
- `git diff --check`: pass.
- Remaining legacy full-suite failures are not claimed resolved by this partial checkpoint.
