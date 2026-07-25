# PLAN-20260403-050 Runtime / Memory / SQL Boundary Freeze

## 2026-07-24 Supersession Note
- The ownership principle in this document remains binding: runtime truth, MAS memory,
  queue transport, and physical storage are separate concerns.
- PLAN-20260718-068 supersedes the old implementation-owner and provider assumptions.
  `RuntimeSessionService` has been removed. Database-independent MAS control-plane
  services select runtime transitions through narrow store contracts, while
  SQLAlchemy adapters persist them.
- PostgreSQL is the only verified public runtime database. SQLite remains bounded
  test evidence, and historical MySQL databases are not release-compatible unless a
  separate migration and transaction contract is reviewed.

## Purpose
- Freeze the architecture split between:
  - runtime/control-plane persistence
  - MAS/agent memory application
  - SQL as a physical storage substrate
- Prevent follow-on SQL work from conflating:
  - runtime truth ownership
  - memory backend replaceability
  - transaction-semantic verification

## Boundary Verdict
- MAS runtime control-plane services remain the sole semantic owners of
  runtime/session/node/attempt/gate/decision truth.
- MAS/agent memory remains a separate application layer accessed through `ContextContractAssembler`, `MemoryWriter`, `MemoryServices`, and the memory interfaces.
- SQL is not a single architecture layer in this repo; it is a storage technology used by more than one subsystem.
- Any association between runtime facts and MAS memory must flow through the memory application layer interfaces, never by promoting memory state into runtime authority.

## Layer Map
| Layer | Purpose | Owner / Entry Point | Current Carriers | Must Not Own |
| --- | --- | --- | --- | --- |
| Runtime control-plane persistence | Select and persist authoritative execution truth for runtime/session/node/attempt/gate/decision state | MAS runtime control-plane services through capability-oriented runtime store contracts | Immutable runtime records plus `WorkflowSession`, `WorkflowNodeState`, `WorkflowNodeAttempt`, `WorkflowGate`, `WorkflowGateDecision`, published deliverables, and continuation checkpoints | Shared WM truth, queue truth, agent memory truth, artifact-existence truth |
| Runtime-to-agent contract layer | Convert authoritative runtime facts into stable downstream-readable contracts | `PublishedDeliverableService`, `script_review_contract`, `OrchestrationStateAdapter`, `ContextContractAssembler` | published deliverable refs, payload refs, script review contract, continuation checkpoints, runtime input payload | Runtime state machine ownership, lease/gate authority, MAS memory ownership |
| MAS/agent memory application layer | Build and persist agent-oriented working/episodic memory through explicit interfaces | `MemoryServices`, `WorkingMemoryService`, `MemoryWriter`, memory interfaces | working memory scopes, long-term memory entries, generation metadata, agent-facing fact snapshots | Runtime attempt status, gate decisions, continuation authority, queue transport state |
| Physical storage layer | Store bytes/rows/files for the above layers | SQLAlchemy adapters, SQLite memory store, JSON payload files, in-memory backends | PostgreSQL release DB, SQLite test DB, SQLite memory DB, payload JSON files | Architecture ownership by itself |

## Runtime Persistence Boundary
- Runtime persistence is a control-plane concern, not a generic memory concern.
- Authoritative runtime facts include:
  - session lifecycle
  - current node / current attempt
  - gate status and latest decision
  - attempt lease / heartbeat timestamps
  - continuation checkpoints required for resume/bootstrap
- These facts stay behind database-independent runtime control-plane services and
  capability-oriented store/read-model ports.
- Queue/worker only transport execution; they must not become runtime truth owners.

## MAS Memory Boundary
- MAS memory exists to support agent context assembly, working memory, and long-term memory snapshots.
- MAS memory may store:
  - explicit scene/script/reference facts
  - generation metadata
  - agent-facing episodic or working-memory entries
- MAS memory must not become the authoritative source for:
  - resume continuity
  - gate decisions
  - runtime node/attempt status
  - lease liveness
- The current `MemoryWriter` contract already states this explicitly: it must not become a sink for runtime status, gate decisions, queue state, task specs, or other control-plane authority.

## Allowed Runtime <-> Memory Association
- Allowed:
  - runtime persists a stable fact/contract carrier
  - `ContextContractAssembler` reads that carrier and assembles agent context
  - `MemoryWriter` persists derivative, agent-oriented memory snapshots if needed
- Examples of allowed carriers:
  - published deliverable refs
  - script review contract
  - continuation checkpoints
  - runtime input payload facts intentionally exposed for downstream assembly
- Forbidden:
  - resume/gate/bootstrap logic loading from shared working memory as an authority fallback
  - runtime state machine mutating or validating from MAS memory rows
  - direct coupling between runtime owner logic and memory backend implementation details

## Why SQLite-Bounded vs PostgreSQL-Authoritative Exists
- The repo currently uses SQL in more than one context:
  - PostgreSQL app/runtime DB via `DATABASE_URL`
  - SQLite-backed test harnesses
  - SQLite-backed memory store as one optional memory backend
- Therefore "uses SQL" is not specific enough to define verification strength.
- `SQLite-bounded` means:
  - evidence is valid for bounded local behavior such as owner split, call path, or facade/session contract
  - evidence does not prove PostgreSQL row-locking, transaction visibility, or isolation semantics
- `PostgreSQL-authoritative` means:
  - evidence is taken on the verified release adapter and migration chain
  - evidence is admissible for claims about cross-session freshness, lease visibility, and control-plane validation under production-like semantics

## Root Cause of the Earlier SQL Confusion
- The confusion came from mixing three statements that are all true, but belong to different layers:
  - runtime truth is persisted in SQL-backed control-plane tables
  - memory can also use SQLite as a physical backend
  - fast tests may also use SQLite
- Those statements do not imply that one SQLite pass proves production runtime SQL semantics.
- Historical MySQL-specific evidence from PLAN-20260401-045 is not admissible for
  current release claims. Transaction semantics must be validated on PostgreSQL at
  the runtime store/control-plane boundary, not inferred from SQLite or legacy
  provider behavior.

## SQL Solution Design Order
1. Freeze architecture ownership first.
   - runtime truth owner: MAS runtime control-plane services
   - persistence implementation: injected runtime store/read-model adapters
   - memory owner: memory application interfaces
   - physical storage: replaceable backend detail
2. Freeze allowed cross-layer interfaces.
   - runtime exports stable facts/contracts
   - assembler/writer/provider consume those facts
   - no Shared WM authority fallback for resume/gate/runtime state
3. Classify every SQL-related claim by semantic class.
   - owner split / call path / facade contract
   - runtime transaction freshness / isolation
   - memory backend contract / durability
4. Bind each semantic class to admissible evidence.
   - owner split / facade contract: SQLite-bounded unit evidence acceptable
   - runtime transaction freshness / lease visibility: PostgreSQL-authoritative evidence required
   - memory backend behavior: memory-backend contract tests acceptable on the selected backend
5. Only after the above is frozen, design any SQL remediation or verification follow-on.

## Verification Matrix
| Claim Type | Minimum Admissible Evidence | Not Admissible As Final Proof |
| --- | --- | --- |
| Pre-exec control plane selects explicit transition facts | SQLite-bounded focused unit tests | PostgreSQL connectivity alone |
| Post-exec transition reopens fresh control-plane session | SQLite-bounded focused unit tests | Queue diagnostics or websocket state |
| Runtime lease freshness across concurrent sessions | PostgreSQL-backed focused integration | SQLite unit tests or migration success alone |
| Resume continuation ownership stays out of Shared WM | Focused control-plane tests and boundary review | Shared-WM content snapshots |
| Memory backend stores/retrieves agent facts correctly | Memory contract tests on chosen backend | Runtime DB tests alone |

## Design Constraints for Any Follow-On SQL Work
- Do not redesign runtime SQL and memory SQL as one combined subsystem.
- Do not move runtime truth into memory tables/stores for the sake of "unification".
- Do not claim architectural proof from a storage backend that does not match the semantics being asserted.
- Do not use queue/broker/websocket/artifact existence as a substitute for runtime DB authority.
- Do not introduce compatibility shims that let control-plane recovery fall back to MAS memory authority.

## Immediate Design Outcome
- `050` remains a historical boundary-freeze record; PLAN-20260718-068 owns the
  implemented control-plane/store separation and current release evidence.
- PostgreSQL transaction evidence validates the selected adapter without coupling
  Agents, MAS memory, or queue transport to SQL.
- Any future database provider requires its own reviewed migration and transaction
  contract. Provider expansion is not implied by architectural decoupling.
