# Validation Ledger: PLAN-20260404-051

## Scope
- Open an independent SQL governance/design plan after `PLAN-20260403-050` completed its bounded seam and moved to `awaiting_user_confirmation`.
- Freeze the boundary between:
  - runtime control-plane persistence
  - MAS-agent memory application
  - SQL physical substrate
- Keep runtime implementation code unchanged until the new plan's boundary and claim-classification gates are passed.

## Execution Order
- Stage A boundary/evidence freeze must complete before any runtime SQL verification or implementation follow-on is proposed.
- Stage B claim inventory must classify unresolved conclusions before any MySQL-authoritative probe or successor plan is opened.
- Stage C may decide to close governance only, or to split narrower successor plans by layer and evidence class.

## Acceptance Gates
### Stage A: boundary gate
- [x] `PLAN-20260403-050` is confirmed as `awaiting_user_confirmation` and reference-only
- [x] checkpoint commit `fc824ca` is confirmed as the `050` code baseline
- [x] a new managed plan exists separately from `050`
- [x] a written three-layer authority map exists
- [x] a written taxonomy exists for runtime SQL claim vs memory backend claim vs substrate claim
- [x] a written admissible-evidence matrix exists for MySQL-authoritative vs SQLite-bounded evidence
- [x] a written allowed-interface and forbidden-fallback list exists for runtime facts and memory association
- [x] no runtime implementation files were changed in this stage

### Stage B: unresolved-claim inventory gate
- [x] every unresolved SQL-adjacent conclusion is classified as runtime SQL claim, memory backend claim, or substrate claim
- [x] every unresolved runtime SQL claim states whether it is owner-path only or transaction-semantic
- [x] every unresolved memory backend claim states the backend and contract under test
- [x] each proposed verification slice states whether it is MySQL-authoritative or SQLite-bounded
- [x] no open question remains phrased as generic "SQL issue" without a layer classification

### Stage C: follow-on decision gate
- [x] either no implementation follow-on is needed, or successor plans are split by layer and evidence class
- [x] no successor plan mixes runtime authority redesign with memory backend redesign
- [x] `050` remains unopened and reference-only
- [x] any MySQL-authoritative runtime claim is assigned to a runtime-specific successor slice instead of being left as an implicit TODO

## Automated Checks
- [x] plan artifact created under `docs/plans/active/`
- [x] validation ledger created under `docs/plans/active/`
- [x] Stage B claim-inventory artifact created under `docs/plans/active/`
- [x] `docs/plans/PLAN_INDEX.json` updated for the new plan
- [x] no runtime implementation file was edited in this stage

## Manual Checks
- [x] Review the frozen docs and current code entry points against `RuntimeSessionService`, `ContextContractAssembler`, `MemoryWriter`, `MemoryServices`, and `SQLiteMemoryStore`
- [x] Review `PLAN_INDEX.json` status for `045`, `047`, `049`, and `050` to keep old streams reference-only
- [x] Review the new Stage A freeze note to ensure runtime SQL claims and memory backend claims are not conflated
- [x] Review `PLAN-20260401-045-validation.md` to separate already-closed MySQL-authoritative runtime claims from new follow-on obligations
- [x] Review memory backend configuration entry points to keep config/backend questions out of runtime SQL scope

## QC Rules
- `RuntimeSessionService` remains the sole authority for runtime/session/node/attempt/gate/decision truth.
- Runtime truth must not move into queue, broker, websocket, artifact existence, or MAS memory.
- MAS memory backend behavior is not a runtime control-plane fallback.
- SQLite-bounded test or memory-store results do not prove MySQL runtime semantics.
- No compatibility shim may preserve a known-wrong mixed boundary just to accelerate follow-on work.

## Evidence Log
- 2026-04-04T02:21:13Z independent managed SQL governance/design plan created as the post-`050` follow-on.
- 2026-04-04T02:22:25Z Stage A boundary gate passed: `050` status/baseline were confirmed, the three-layer authority map and claim/evidence policy were written down, and this turn made no runtime implementation changes.
- 2026-04-04T02:35:50Z Stage B claim inventory passed via `PLAN-20260404-051-stage-b-claim-inventory.md`: closed runtime SQL owner-path claims, closed current `045`-class MySQL runtime defect claims, and open memory-backend/config claims are now separated explicitly.
- 2026-04-04T02:35:50Z Stage C follow-on decision passed: no immediate runtime SQL remediation plan and no immediate MySQL verification-only slice are required on the current baseline; future runtime transaction-semantic changes must open a runtime-specific successor, while memory backend cleanup remains optional and separate.
