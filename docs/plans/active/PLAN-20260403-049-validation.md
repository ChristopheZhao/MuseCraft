# Validation Ledger: PLAN-20260403-049

## Scope
- Validate the governance/refactor follow-up after `PLAN-20260401-045`.
- Confirm runtime/control-plane ownership remains explicit while orchestrator-thickness and lease-surface cleanup are reviewed.
- Keep this plan separate from `PLAN-20260402-047`; image-composer diagnostics are already closed and remain out of scope here.

## Execution Order
- Stage A review-first governance freeze must complete before Stage B inventory or Stage C slice selection begins.
- Stage B inventory and boundary verdict must be reviewed before any implementation slice is approved.
- Stage C slice selection must record targeted validation before Stage D code changes or replay work begin.

## Acceptance Gates
### Stage A: review / boundary gate
- [x] Review confirms MySQL/runtime persistence is the runtime-control-plane SoT rather than a duplicate SoT
- [x] Review confirms queue/worker/broker remain transport-only and do not gain runtime authority
- [x] Review confirms MAS/business-fact stores remain distinct from runtime-control-plane authority
- [x] Review confirms `047` is already closed/reference-only and is not absorbed into this governance stream
- [x] A written Stage A governance-freeze note exists with the exact deliverables and verify gate
- [x] A written SoT owner matrix exists for runtime authority, business facts, queue transport, and frontend/read-model projection
- [x] A written orchestrator target-role note exists and is reviewed before Stage B begins
- [x] A written MySQL-authoritative vs SQLite-bounded runtime test-boundary note exists and is reviewed before Stage B begins

### Stage B: architecture gate
- [x] A written orchestrator/runtime responsibility inventory exists with explicit `keep`, `move-behind-facade`, and `diagnostics-only` decisions
- [x] A written verdict exists on which current lease/liveness surfaces are acceptable in tool/execution paths and which should be reduced
- [x] Stage B records the control-plane facade/service seam direction without weakening `RuntimeSessionService`
- [x] Stage B keeps `045` closed and `047` separate while inventorying current responsibilities

### Stage C / D: implementation gate
- [x] One first bounded slimming slice is recorded with explicit target files, non-targets, and targeted validation before any code changes begin
- [x] If a first bounded slimming slice is selected, it preserves `045` runtime correctness and does not weaken `RuntimeSessionService`
- [x] No artifact-based, queue-based, or websocket-based runtime authority shortcut is introduced
- [x] Any selected first slice is validated without reopening `047` image-composer scope

## Automated Checks
- [x] Targeted tests or audits exist for any first bounded slimming slice
- [x] Any new runtime-boundary tests explicitly state whether they depend on MySQL semantics or are SQLite-bounded only

## Manual Checks
- [x] Review one responsibility matrix and confirm each runtime concern has a single owner
- [x] Review one orchestrator responsibility inventory and confirm keep/move/reduce decisions are explicit
- [x] Review one test-boundary note and confirm SQLite limitations are not treated as production architecture evidence

## QC Rules
- `RuntimeSessionService` remains the sole runtime-control-plane authority.
- Queue, broker, and websocket state remain diagnostics/projection only.
- `047` remains separate.
- No new compatibility layer may preserve a known-bad authority split.

## Evidence Log
- 2026-04-03T05:18:46Z validation ledger created for the governance/refactor successor to `PLAN-20260401-045`.
- 2026-04-03T05:18:46Z initial validation scope frozen to runtime SoT clarity, orchestrator-thickness review, lease-surface review, and test-boundary governance; no implementation evidence recorded yet.
- 2026-04-03T09:17:25Z `047` is now closed/reference-only; `049` starts with a mandatory Stage A review-first governance freeze and must pass stage verification before implementation work begins.
- 2026-04-03T09:30:05Z Stage A review / boundary gate passed via `PLAN-20260403-049-stage-a-governance-freeze.md`: the runtime/business/queue/frontend owner matrix, orchestrator target-role note, and MySQL-authoritative vs SQLite-bounded test-boundary note were written and reviewed without changing runtime implementation code.
- 2026-04-03T09:30:05Z Stage B architecture gate passed via `PLAN-20260403-049-stage-b-responsibility-inventory.md`: current orchestrator/runtime responsibilities were classified as `keep`, `move-behind-facade`, or `diagnostics-only`, and the lease/liveness surface verdict explicitly preserved `RuntimeSessionService` authority while keeping `045` closed and `047` out of scope.
- 2026-04-03T09:46:37Z Stage C contract recorded in `PLAN-20260403-049-stage-c-bounded-slice.md`: the first implementation slice is limited to extracting orchestrator post-execution runtime control-plane transitions behind one dedicated facade/service, with `orchestrator.py` plus one new service file as the target surface and focused `test_orchestrator_runtime_mainline.py` validation named upfront.
- 2026-04-03T10:09:07Z Stage D targeted validation passed for `C1`: `python3 -m py_compile` succeeded for `orchestrator.py`, `orchestration_runtime_transition_facade.py`, and `test_orchestrator_runtime_mainline.py`; focused direct invocation of the affected runtime-mainline unit tests passed in the backend virtualenv; no runtime authority moved into queue, broker, websocket, or artifact shortcuts; and validation remained fully outside `047` scope.
- 2026-04-03T10:09:07Z The `C1` unit validation is explicitly SQLite-bounded only: it verifies fresh-session facade wiring and orchestrator/runtime contract shape, and does not claim MySQL transaction-isolation equivalence or replace any future MySQL-backed replay/integration evidence.
- 2026-04-03T13:54:27Z Lifecycle closeout accepted at the bounded `C1` seam: `049` ends after governance plus one implementation slice, and any further orchestrator/runtime slimming must proceed under the separate follow-on plan `PLAN-20260403-050` rather than widening this completed plan.
