# Runtime Control-Plane Store Boundary

- Date: `2026-07-19`
- Plan: `PLAN-20260718-068`
- Slice: D, runtime-store contract freeze
- Status: binding target contract; SQLAlchemy migration remains in progress

## Decision Ownership

`RuntimeSessionService` remains the single semantic owner for runtime session, node,
attempt, lease, gate, decision, continuation, and terminal-transition behavior. The
store does not decide whether an attempt may start, which gate action is valid, which
continuation anchor applies, or whether a run is complete. It persists facts already
selected and validated by the control plane.

```text
orchestrator / API command
          |
          v
RuntimeSessionService (policy, invariants, target facts)
          |
          v
RuntimeControlPlaneUnitOfWork
          |
          v
RuntimeControlPlaneStore (fresh load, lock/CAS, map, persist)
          |
          v
SQLAlchemy PostgreSQL adapter
```

ORM mappings, SQLAlchemy sessions, row locks, dialect behavior, and commit/rollback
mechanics must remain below the UoW boundary. Domain records or read models cross the
boundary; mapped rows and `Session` do not.

## Contract Surfaces

The executable value and port contracts are defined in
`backend/app/domain/runtime_store.py`.

| Contract family | Purpose | Owner of meaning |
| --- | --- | --- |
| Runtime records | Immutable session/node/attempt/gate/decision/deliverable snapshots with stable task identity | control plane/domain |
| Transition commands | Complete target facts plus expected state/lease preconditions | `RuntimeSessionService` |
| Runtime store | Fresh reads, mapping, lock/CAS enforcement, staged persistence | infrastructure adapter |
| Runtime UoW | One transaction and explicit commit/rollback | application/control plane selects boundary; adapter implements mechanics |
| Runtime read model/query | Explicit projection consumed outside command paths through a port separate from the command store | query/read-model layer |

`RuntimeStoreError.reason_code` reports persistence facts such as missing rows,
state/lease conflicts, integrity failures, or transaction failures. Store errors must
not return orchestration actions such as retry, resume, approve, or abort; the control
plane interprets the diagnostic and remains fail closed.

## Atomic Capability Matrix

| Capability | Required transaction content | Forbidden adapter decision |
| --- | --- | --- |
| Session create/transition | session plus explicit task transition when supplied | choosing mode, completion, or failure policy |
| Node transition | expected node state, target state, optional session/task facts | choosing next node |
| Attempt start | node/session attempt numbering and caller-provided input contract | choosing whether the attempt is eligible |
| Lease grant/heartbeat/release | token/owner/time preconditions and compare-and-set update | inventing tokens, retry policy, or lease duration |
| Continuation bind | exact validated checkpoint and expected attempt state | synthesizing or repairing missing continuation facts |
| Attempt complete/fail | attempt, node, lease, diagnostics, output facts in one transaction | accepting incomplete media or deciding retry |
| Gate open/decision | gate/decision plus caller-provided node/session/task transitions | choosing allowed action or invalidation scope |
| Deliverable publish/approve | payload reference and exact session/node/attempt binding | modifying payload meaning or approving implicitly |
| Fresh read model | one authoritative session projection from committed runtime rows | inferring state from Celery/Redis health |

Every operation that checks an expected status or lease must use a PostgreSQL-safe
locking/CAS strategy in the adapter and return a typed conflict. A generic repository
`save(entity)` operation is not sufficient evidence for these semantics.

## Migration Order

1. Implement SQLAlchemy mapping adapters from ORM rows to immutable domain records.
2. Move fresh-load and transaction mechanics behind `RuntimeControlPlaneUnitOfWork`.
3. Migrate attempt/lease/continuation operations first because they carry the highest
   concurrency risk.
4. Migrate gate open/decision and session terminal transitions without changing
   `RuntimeSessionService` policy.
5. Move published-deliverable persistence behind the same application boundary so
   `ContextContractAssembler` no longer accepts a database session.
6. Migrate API projections to `RuntimeReadModel`, then remove async/sync Session entry
   signatures from orchestration-facing facades and the control-plane service.
7. Reduce the executable transitional-debt baseline to zero before Gate D closes.

## Transitional Debt Ratchet

The Slice D architecture test records direct SQLAlchemy/ORM ownership in exactly five
control-plane-facing modules:

- `runtime_session_service.py`
- `published_deliverable_service.py`
- `context_assembler.py`
- `orchestration_runtime_transition_facade.py`
- `orchestration_runtime_resume_bootstrap_facade.py`

This baseline is not an exemption. New violations fail, moving Session/ORM imports to
another helper fails, and each migrated module must be removed from the baseline in
the same change. Gate D requires the baseline to be empty.

## Negative Cases

- Renaming `RuntimeSessionService` to `SqlAlchemyRuntimeStore` without separating
  policy from mapping is not a migration.
- Returning ORM rows from a protocol as `object`, `Any`, or an untyped dictionary is
  not domain separation.
- A store must not repair missing nodes, continuations, gates, or decisions on reads.
- Queue, MemoryWriter, Shared WM, events, and read-model code cannot become runtime
  truth owners.
- Context assembly may build deliverable payload facts but must not receive or manage
  a SQLAlchemy session.
- A passing SQLite unit test does not establish PostgreSQL lease/gate transaction
  semantics; that evidence belongs to Slice F.
