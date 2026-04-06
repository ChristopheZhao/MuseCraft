# PLAN-20260404-052 Stage B Claim Inventory

## Purpose
- Inventory unresolved memory-only claims after the Stage A freeze.
- Separate already-guarded or already-understood memory boundaries from genuinely open governance/config/support questions.
- Decide whether the next move should be an implementation successor or simply recorded reopen triggers.

## Closed or Narrowed Claims
| Claim ID | Claim Family | Current Evidence | Current Verdict |
| --- | --- | --- | --- |
| MCL-001 | Memory boundary guard | `test_memory_writer_boundary.py` shows runtime/planning authority fields are ignored by `MemoryWriter` | Closed on current baseline |
| MCL-002 | Memory boundary guard | `test_execution_boundary_assembler_contexts.py` shows assembler consumes explicit carriers rather than using shared WM as runtime authority | Closed on current baseline |
| MCL-003 | Memory exposure guard | `test_static_memory_guards.py` blocks app-layer singleton reintroduction and direct `LongTermMemoryManager` exposure outside allowed layers | Closed on current baseline |

## Unresolved Memory-Only Claims
| Claim ID | Claim Class | Claim Statement | Current Evidence | Current Verdict | Recommended Evidence Before Any Change | Reopen Trigger |
| --- | --- | --- | --- | --- | --- | --- |
| MOPEN-001 | Config semantics | `MEMORY_WORKFLOW_BACKEND`, `MEMORY_STORAGE_BACKEND`, and `MEMORY_BACKEND` currently govern different construction points but the split is not documented in product-facing or operator-facing terms | config + construction-path review | Open governance/config claim | explicit config contract and backend-selection tests if normalization is proposed | operator confusion or deliberate backend-normalization work |
| MOPEN-002 | Dead/unused knob | `MEMORY_FACTS_BACKEND` is declared in config but no active reviewed consumer path was found in the current code or test scan | config review + repo-wide search | Open dead/unused knob claim | explicit consumer-path proof or explicit deprecation/removal plan | discovery of a hidden consumer path or decision to prune dead knobs |
| MOPEN-003 | Dead/stale adapter path | `create_global_memory_service()` passes `slots_path` into `build_memory_management()`, but the reviewed `build_memory_management()` signature does not accept that parameter; no active callsite was found in the repo scan | static code review + repo-wide search | Open stale-adapter-path claim | direct usage proof or targeted test before any fix | adapter becomes used, imported by new code, or triggers a real exception |
| MOPEN-004 | Fallback / operability | unavailable workflow backend falls back to `dict`, but the operational meaning of that downgrade is not frozen as a support statement | code review only | Open fallback-governance claim | targeted fallback test and operator-facing support statement before changing behavior | observed fallback in dev/prod or explicit request to harden fallback diagnostics |
| MOPEN-005 | Fallback / operability | long-term store may fall back from sqlite to `DictMemoryStore`, but persistence/durability downgrade is not frozen as an explicit support contract | code review only | Open fallback-governance claim | targeted fallback test and support-level statement before changing behavior | observed sqlite-unavailable downgrade or request to guarantee persistence |
| MOPEN-006 | Backend contract | short-term working memory is effectively fixed to in-memory in the reviewed path, but that support level is not frozen as an explicit contract | `memory_provider.py` + in-memory factory review | Open support-scope claim | explicit support statement and, if configurability is desired, tests for new backend plumbing | request to make short-term backend configurable |
| MOPEN-007 | Backend contract | no targeted `SQLiteMemoryStore` test coverage was found in the reviewed test suite; existing standalone memory integration test uses `DictMemoryStore` instead | repo-wide test scan | Open backend-contract claim | backend-local CRUD/search/serialization tests for `SQLiteMemoryStore` before hardening or support upgrades | backend failure report, portability work, or explicit request to support sqlite as a stronger backend |

## Stage C Follow-On Decision
- No immediate memory-only implementation successor is opened from the current evidence set.
- Reason:
  - reviewed issues are governance/config/support questions, not confirmed functional failures in the running mainline
  - no targeted failing test or reproduced operator/runtime failure currently justifies code churn
  - the boundary guards that protect runtime authority and memory-layer isolation are already present
- Required future routing:
  - if the goal is operator clarity or config normalization, open a memory-only config cleanup successor
  - if the goal is stronger backend guarantees for sqlite, open a backend-contract successor with backend-local tests first
  - if a real fallback or adapter-path failure is reproduced, open a memory-only fix plan tied to that evidence

## Residual Risks
- Backend-selection semantics remain harder to reason about than necessary.
- `MEMORY_FACTS_BACKEND` may remain misleading until it is either proven active or formally retired.
- The stale `create_global_memory_service()` adapter signature mismatch is low-risk while unused, but it remains a trap if new code starts using it without tests.
