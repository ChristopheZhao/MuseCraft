# PLAN-20260404-052 Stage A Memory Governance Freeze

## Purpose
- Freeze the reviewed memory backend/config/contract surface before any cleanup or backend hardening work starts.
- Keep memory governance separate from runtime SQL governance.
- Record which backend knobs currently own active code paths, which ones are only defaults/fallbacks, and which ones require later clarification.

## Reference Baseline
- `PLAN-20260404-051` is completed and reference-only.
- Runtime authority remains owned by `RuntimeSessionService` and is out of scope here.
- Current reviewed memory construction anchors:
  - `backend/app/core/config.py`
  - `backend/app/services/memory_provider.py`
  - `backend/app/agents/memory/managers/management.py`
  - `backend/app/agents/memory/storage/in_memory/factory.py`
  - `backend/app/agents/memory/long_term/stores/sqlite_store.py`

## Memory Owner Map
| Layer | Current Owner / Entry Point | Current Backend Selection Path | Current Effective Backend Claim | Out of Scope |
| --- | --- | --- | --- | --- |
| Workflow memory backend | `build_memory_services()` -> `build_memory_management(storage_backend=settings.MEMORY_WORKFLOW_BACKEND)` | `MEMORY_WORKFLOW_BACKEND` with fallback inside `build_memory_management()` to `MEMORY_STORAGE_BACKEND` or `"dict"` | reviewed as an active config owner path | runtime authority, runtime DB semantics |
| Long-term memory store backend | `build_memory_management()` default store-map creation | `MEMORY_BACKEND` chooses `SQLiteMemoryStore` or `DictMemoryStore` fallback | reviewed as an active config owner path | runtime authority, runtime SQL proofs |
| Short-term working-memory backend | `build_memory_services()` -> `create_short_term_store(kind="memory")` | fixed reviewed factory path, currently in-memory only in this owner path | reviewed as active but effectively fixed support path | runtime authority, long-term durability claims |
| Facts backend knob | config declaration only in current evidence set | `MEMORY_FACTS_BACKEND` declared in config | no active reviewed consumer path established in this stage | implicit assumptions about active behavior |

## Config / Env Map
| Knob | Where Declared / Read | Reviewed Meaning In Current Baseline | Current Governance Verdict |
| --- | --- | --- | --- |
| `MEMORY_WORKFLOW_BACKEND` | declared in `config.py`, consumed by `memory_provider.py` | selects the workflow backend passed into `build_memory_management()` | active knob, meaning must stay explicit |
| `MEMORY_STORAGE_BACKEND` | env fallback inside `build_memory_management()` | secondary fallback for workflow backend selection when the explicit argument is absent | active fallback input, but not the primary entrypoint in the reviewed construction path |
| `MEMORY_BACKEND` | env read inside `build_memory_management()` | selects default long-term store backend (`sqlite` vs `dict`) | active knob, separate from workflow backend selection |
| `MEMORY_FACTS_BACKEND` | declared in `config.py` only in the reviewed evidence set | no active consumer path was demonstrated in this Stage A review | unresolved knob; must not be assumed active without later proof |

## Fallback / Support Matrix
| Surface | Current Reviewed Fallback | Current Support-Level Statement | Must Not Be Claimed |
| --- | --- | --- | --- |
| Workflow backend | unavailable backend falls back to `dict` workflow backend in `build_memory_management()` | fallback exists and is code-real | that fallback preserves the same operability or durability guarantees as the requested backend |
| Long-term store backend | `MEMORY_BACKEND=sqlite` may fall back to `DictMemoryStore` if sqlite backend is unavailable | fallback exists and is code-real | fallback equals sqlite persistence guarantees |
| Short-term working memory | current reviewed path creates `InMemoryShortTermMemoryStore` through fixed factory input | current reviewed support path is effectively in-memory | that short-term backend is user-configurable in the reviewed path |
| Facts backend | no reviewed active owner path | no support claim allowed yet | that `MEMORY_FACTS_BACKEND` already influences running behavior |

## Non-Goals
- Any runtime/session/node/attempt/gate/decision redesign
- Any runtime SQL freshness or isolation validation
- Any attempt to unify runtime persistence and memory persistence into one layer
- Any claim that memory backend fallback is acceptable as runtime fallback

## Stage B Entrance Conditions
- The next stage must classify every remaining issue as memory-only:
  - config semantics
  - fallback/operability
  - backend-contract
  - dead/unused knob
- If a proposed next step requires changing runtime authority paths, this plan must stop and split.
