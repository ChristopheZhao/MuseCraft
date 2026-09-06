# Project and MAS Runtime Authority Boundary

- Plan: `PLAN-20260718-068`, Amendment A2
- Status: frozen before implementation
- Date: 2026-07-19

## Authority Matrix

| Fact | Command owner | Persistence owner | Read projection owner |
| --- | --- | --- | --- |
| Project prompt, mode, global settings, style, character bible, story plan, episode editorial state, configured cost budget | Project application use case | Versioned project-definition store/UoW | Project query service |
| Planning and character-reference job status | Task application use case | Task store | Project execution read model |
| Episode/workflow execution status, node, attempt, lease, retry, gate and terminal decision | MAS runtime control plane | Runtime capability store/UoW | Runtime read-model query |
| Accepted generated output | Published-deliverable control plane | Published-deliverable store | Project execution read model |
| Observed token/cost usage | Explicit usage/accounting owner | Usage record store | Project execution read model |
| Project progress and completed counts | No command owner; derived only | Not persisted as authority | Project execution read model |

The project-definition aggregate must not contain `episodes_runtime`, runtime status,
workflow/session/task identity, generated output assets, observed token/cost totals,
or derived progress/completed counts. A query projection may expose those values but
must never provide a save/update path.

## Identity Matrix

| Component | Identity | Allowed ownership |
| --- | --- | --- |
| ReAct specialist generators/composer | Native Agent | Observe, plan, tool action, reflection, typed boundary report |
| Script writer | Deterministic MAS stage | Fixed script-generation stage with explicit execution-mode receipt |
| Series planner | Bounded reasoning Agent | Return a typed project-plan draft; no project load/save |
| MAS orchestrator | Control-plane coordinator | Select semantic orchestration/runtime actions through injected ports |
| Episode coordinator | Application/control-plane service | Select approved episodes and invoke child workflows; no Agent registration |
| API, Celery, in-process scheduler | Entrypoint/transport | Stable identifiers and application use-case invocation only |
| SQLAlchemy adapter | Infrastructure | ORM mapping, session/UoW and atomic persistence only |

The current `OrchestratorAgent` name is transitional. Its control-plane identity does
not permit construction of SQLAlchemy facades. The current
`EpisodeOrchestratorAgent` identity is invalid and must be replaced, not relabeled.

## Command and Transaction Rules

1. A project-definition command loads a versioned record and saves with
   `expected_version` in one unit of work.
2. A stale expected version returns `project_version_conflict`; there is no blind
   last-write-wins retry.
3. Runtime transitions are selected by the MAS control plane and persisted through
   narrow runtime ports. The composition root wires stores but cannot choose a
   transition.
4. Project commands and runtime commands cannot dual-write the same fact. A
   cross-authority operation uses one UoW when the stores share a database, or an
   explicit receipt/compensation contract when it cannot be atomic.
5. Read models are immutable and side-effect free.

## Executable Guard Contract

- Static: walk the transitive internal import graph from every production Agent and
  MAS control-plane entrypoint. Any path reaching SQLAlchemy, `app.core.database`,
  ORM mappings, `SessionLocal`, or a concrete SQLAlchemy store is a violation.
- Dynamic: import and construct the same entrypoints with engine/session/store
  sentinels that raise on composition or connection. Construction must remain clean.
- Identity: application coordinators cannot appear in the production Agent exports,
  tool allocation, or Agent factory branches.
- Authority: project write-domain types cannot contain runtime/read-model fields.
- Expectation check: after each A2 subtask, compare observed ownership and failure
  behavior with this matrix. The check informs reopening/follow-up and is not a
  standalone hard gate unrelated to the subtask.

## Explicit Non-Goals

- Authentication and public endpoint hardening remain in `PLAN-20260711-067`.
- Redis is not mandated for WorkingMemory/EventBus; a provider-neutral store contract
  requires separate evidence.
- File-size-driven module splitting is deferred until the ownership moves are stable.
