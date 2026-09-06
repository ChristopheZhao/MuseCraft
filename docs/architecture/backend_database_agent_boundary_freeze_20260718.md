# Backend Database / Agent Boundary Freeze

- Date: `2026-07-18`
- Plan: `PLAN-20260718-068`
- Status: target architecture contract; implementation is staged through Slices B-F
- Release database adapter: PostgreSQL only, until another adapter has migration and transaction-semantic evidence

## Purpose

This contract separates Agent reasoning, MAS control-plane decisions, application
coordination, physical persistence, transport, and read models. It does not promise
generic multi-database compatibility. It makes database replacement a bounded
infrastructure concern instead of an Agent or algorithm change.

## Required Dependency Direction

```text
uv / Docker / API / Celery
          |
          v
application use cases / MAS control plane
          |
          v
capability-oriented persistence ports + unit of work
          |
          v
SQLAlchemy adapters and database composition
          |
          v
configured local or production database
```

```text
AgentExecutionRequest + ContextAssembler output + Memory services + registered tools
                                      |
                                      v
                                    Agent
                                      |
                                      v
            AgentExecutionResult + explicit report + typed boundary events
```

No dependency arrow may point from an Agent, algorithm, memory abstraction, or
transport adapter to SQLAlchemy, an ORM mapping, an engine/session factory, or a
database-provider policy.

## Ownership Matrix

| Layer | Owns | Must not own |
| --- | --- | --- |
| Agent / algorithm | ReAct strategy, tool selection, evidence interpretation, reflection, explicit boundary facts | ORM entities, sessions, commits, task/runtime state transitions, database-provider policy |
| MAS control plane | session/node/attempt/gate/decision semantics and fail-closed runtime transitions | SQLAlchemy mappings, queue-state inference, provider selection |
| Application use case | task lifecycle coordination, command ordering, transaction boundary selection | Agent inner-loop strategy, queue health as business truth |
| Persistence port | named atomic capabilities required by the application or control plane | generic CRUD semantics, routing decisions, invented domain facts |
| SQLAlchemy adapter | mapping, query/locking implementation, engine/session lifecycle, dialect adaptation | Agent decisions, runtime policy, read-model inference |
| Queue / worker | delivery, retry transport, bounded transport diagnostics | ORM bootstrap, MAS eligibility, runtime advancement, completion truth |
| Read-model adapter | explicit API/runtime projections from authoritative state | commands, runtime transitions, queue-derived business state |
| Process entrypoint | process lifecycle and rendering typed bootstrap diagnostics | provider policy, database dialect parsing, migration semantics |

## Agent Execution Contract

The target execution boundary is implemented in
`backend/app/domain/agent_execution.py`.

- `AgentTaskReference` contains stable domain identifiers and correlation values. It
  never contains an ORM primary-key object or mapped entity.
- `AgentExecutionRequest` contains the task reference, logical Agent type, optional
  workflow correlation ID, execution order, and a strict JSON input snapshot.
- `AgentExecutionResult` separates output data, the Agent-owned orchestration report,
  and typed boundary events. A consumer that requires a report fails closed when it
  is absent; the base class or adapter must not synthesize one.
- `JsonObjectPayload` rejects runtime objects, tuples, non-string map keys, and
  non-finite numbers. It does not use `default=str`, `__dict__`, or catch-all
  conversion because those paths hide an invalid boundary.
- `AgentBoundaryEvent` requires a stable event kind and reason code. Persistence and
  routing of that fact remain outside the Agent.

Semantic validation of an orchestration report remains owned by the orchestration
protocol. The JSON contract validates representation only and must not invent status,
artifacts, gate triggers, reflection, or completion meaning.

## Persistence Port Responsibilities

Ports introduced in later slices must be capability-oriented:

| Port family | Required capability shape | Semantic owner |
| --- | --- | --- |
| Task command store / unit of work | load task command input, apply explicit progress/result/failure/quality commands atomically | application use case |
| Runtime state store | atomic attempt lease, heartbeat/release, gate open/decision, continuation bind, completion/failure, fresh reads | MAS control plane |
| Published deliverable store | publish and load strict typed payloads with explicit contract errors | control plane / boundary service |
| Read-model query adapter | task/runtime/project projections for API consumers | query/read-model layer |

A port must not return ORM entities under `Any`, accept a live Session from its caller,
or choose orchestration actions. Runtime state operations are explicit because a
generic repository would erase the transaction semantics that must be proven on
PostgreSQL.

## Configuration Profiles

The composition root receives an explicit logical profile and database connection
configuration. Entrypoints may load configuration but must delegate interpretation to
that composition boundary. The concrete environment variable mapping is implemented
once in Slice E; it is not independently invented by each launcher.

| Profile | Selection | Connection requirement | Failure behavior |
| --- | --- | --- | --- |
| Local development | Default when no deployment profile is selected | Local PostgreSQL address from root project configuration; contributor overrides are allowed | Typed preflight/migration diagnostic; no Agent invocation |
| Production | Must be selected explicitly | Explicit production URL and credentials; example credentials and implicit loopback are invalid | Fail closed; never fall back to the local profile |
| Legacy database adoption | Explicit migration-review operation, not an application profile | Reviewed source and target plus backup/migration plan | No silent stamp, conversion, or release-support claim |

Docker and uv are equivalent process entrypoints over the same application and
database composition contracts. Docker is optional for contributors. Neither path may
contain its own PostgreSQL/MySQL policy.

## Verified Provider Matrix

| Provider | Local profile | Production profile | Release claim | Required evidence |
| --- | --- | --- | --- | --- |
| PostgreSQL | Target default | Supported when explicitly configured | Verified release adapter after Slice F | clean migration chain plus lease/gate/continuation/fresh-session transaction tests |
| MySQL | Legacy data may exist; not the default target | Not currently supported | No support claim | explicit schema/data migration design and equivalent transaction evidence |
| SQLite | Out of scope for multi-process MAS runtime | Not supported | No support claim | separate bounded single-process profile and documented capability limits |

## Executable Guard and Transitional Debt

`backend/tests/architecture/test_agent_persistence_boundary.py` scans every production
module under `app/agents`, including helpers. Archived examples are excluded because
they are production-disabled by repository policy.

The guard classifies imports as:

- persistence framework (`sqlalchemy`),
- database composition (`app.core.database`),
- ORM mapping imported from `app.models`, or
- domain enum/contract still misplaced in the ORM package.

The current debt is an exact ratchet: new violations fail, moving an import to an
Agent helper fails, and resolved entries require the baseline to be reduced. Slice B
must reduce the ratchet to an empty set while moving domain enums/contracts to the
domain layer. The transitional baseline is evidence of known debt, not an exemption
from the final zero-import rule.

## Stage Acceptance

Slice A is accepted only when the domain contract tests and architecture guard pass,
the current debt matches the explicit ratchet, and the observed behavior matches this
contract. Passing Slice A does not claim that Agents are already database-independent;
that claim requires Slice B and a zero-debt guard.
