# PLAN-20260404-051 Stage B Claim Inventory

## Purpose
- Inventory the remaining SQL-adjacent conclusions after Stage A boundary freeze.
- Separate current closed claims from claims that still require a future plan or future evidence.
- Decide whether the next move is:
  - no action
  - a runtime-specific MySQL-authoritative verification slice
  - a runtime SQL remediation plan
  - a separate memory-backend/config plan

## Claim Inventory
| Claim ID | Claim Family | Claim Statement | Current Evidence | Evidence Class Required | Current Verdict | Follow-On Decision | Reopen Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RSQL-001 | Runtime SQL owner-path | `RuntimeSessionService` remains the sole authority for runtime/session/node/attempt/gate/decision truth | `AGENTS.md`, `PLAN-20260403-049`, `PLAN-20260403-050`, `runtime_session_service.py` service surface review | SQLite-bounded owner-path evidence is sufficient | Closed on current baseline | No further action | Reopen only if runtime authority is proposed to move outside `RuntimeSessionService` |
| RSQL-002 | Runtime SQL owner-path | Pre-exec resume/bootstrap uses the caller-owned current session while post-exec transition logic owns fresh control-plane reopening | `PLAN-20260403-050-validation.md`, `PLAN-20260403-050.md`, runtime facade/service review | SQLite-bounded owner-path evidence is sufficient | Closed on current baseline | No further action | Reopen only if future runtime refactors change session ownership at these seams |
| RSQL-003 | Runtime SQL transaction-semantic | The `045` stale repeatable-read completion/failure validation defect is fixed for the current runtime path | `PLAN-20260401-045-validation.md` live replay and MySQL isolation probe | MySQL-authoritative | Closed for current `fc824ca` baseline | No new plan opened now | Reopen only if a new reproducible runtime fault appears or a future change touches completion/failure fresh-read paths |
| RSQL-004 | Runtime SQL transaction-semantic | Any future runtime change that touches cross-session freshness, lease visibility, gate/decision freshness, or continuation freshness must prove correctness on the production DB family | Stage A freeze plus `045` historical RCA | MySQL-authoritative | Open as a governance rule, not as an active defect | Require a separate runtime-specific successor plan when such a change is proposed | Triggered by any future code change on runtime session/transaction freshness paths |
| MBC-001 | Memory backend interface | `ContextContractAssembler` consumes runtime-controlled carriers without requiring shared-WM projection as runtime authority | `test_execution_boundary_assembler_contexts.py`, `context_assembler.py` review | SQLite-bounded interface evidence is sufficient | Closed on current baseline | No further action | Reopen only if assembler starts reading shared WM or long-term memory as runtime authority fallback |
| MBC-002 | Memory backend interface | `MemoryWriter` persists only derivative fact snapshots / metadata and ignores runtime/planning authority fields | `test_memory_writer_boundary.py`, `memory_writer.py` review | SQLite-bounded interface evidence is sufficient | Closed on current baseline | No further action | Reopen only if writer begins accepting runtime status, gate, queue, or task-spec authority fields |
| MBC-003 | Memory backend config | Memory backend selection/config naming is split across `MEMORY_WORKFLOW_BACKEND`, `MEMORY_FACTS_BACKEND`, and `MEMORY_BACKEND`, which can confuse backend intent but does not alter runtime authority | `core/config.py`, `memory_provider.py`, `memory/managers/management.py` review | Code/config review; backend-contract tests only if cleanup is attempted | Open, low-priority governance/config claim | Optional separate memory-backend config cleanup plan only if the user wants to normalize backend selection semantics | Triggered by backend-selection confusion, operator friction, or a deliberate memory-backend cleanup effort |
| MBC-004 | Memory backend contract | `SQLiteMemoryStore` is an optional long-term backend whose CRUD/search/serialization semantics should be validated as a backend contract, not as runtime proof | `sqlite_store.py` review plus existing generic memory tests | SQLite-bounded backend-contract evidence | Open, backend-local claim | Optional separate memory-backend contract plan if SQLite remains a supported backend requiring stronger guarantees | Triggered by backend failures, portability work, or a user request to harden memory backend guarantees |
| SUB-001 | SQL physical substrate | The repo uses SQL in more than one context: runtime app DB, SQLite test DB, and SQLite memory store | Stage A freeze, config/code review | Code/config review | Closed | No further action | Reopen only if a new SQL-bearing subsystem is added |
| SUB-002 | SQL physical substrate | SQLite unit/test media and SQLite memory-store behavior do not prove MySQL runtime semantics | Stage A freeze plus `045` validation | Governance rule only | Closed as policy | No further action | Reopen only if a future plan attempts to over-claim SQLite evidence |

## Stage C Follow-On Decision
- No immediate runtime SQL remediation plan is opened from the current `fc824ca` baseline.
- No immediate MySQL-authoritative verification-only slice is opened from the current `fc824ca` baseline.
- Reason:
  - the active runtime transaction-semantic defect class was already closed under `PLAN-20260401-045`
  - `PLAN-20260403-050` changed owner-path seams, not transaction semantics, and is already bounded/awaiting user confirmation
  - the remaining open items are memory-backend/config claims, not runtime SQL authority claims
- Required future routing:
  - any new runtime change that touches cross-session freshness or transaction visibility must open a runtime-specific successor plan with a MySQL-authoritative gate
  - any cleanup of memory backend configuration or backend contract coverage must open a separate memory-backend plan and must not be phrased as a runtime SQL fix

## Residual Risks
- The repo still carries memory-backend configuration naming drift that can confuse operators or future maintainers even though it does not currently threaten runtime authority.
- Backend-contract hardening for `SQLiteMemoryStore` is not yet formalized as its own plan.
- Repo-wide plan governance drift remains outside the scope of this plan and therefore does not change the layer/evidence verdicts above.
