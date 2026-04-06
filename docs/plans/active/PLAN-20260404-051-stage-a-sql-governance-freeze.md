# PLAN-20260404-051 Stage A SQL Governance Freeze

## Purpose
- Re-confirm the frozen split between runtime control-plane persistence, MAS-agent memory application, and SQL physical substrate.
- Convert the post-`050` boundary freeze into an independent SQL governance/design entrypoint.
- Decide which future SQL conclusions require MySQL-authoritative proof, which are only SQLite-bounded, and which interfaces are allowed between runtime facts and memory association.

## Reference Baseline
- `PLAN-20260403-050` is `awaiting_user_confirmation`; it is reference-only here and must not be reopened for SQL follow-on design.
- checkpoint commit `fc824ca` is the current `050` code baseline.
- `PLAN-20260403-049` is completed and reference-only.
- `PLAN-20260401-045` is completed and reference-only unless a new reproducible runtime fault appears.
- `PLAN-20260402-047` is archived and reference-only.

## Three-Layer Authority Map
| Layer | Owner / Entry Points | Current Code Anchors | Allowed Outward Interface | Must Not Own / Must Not Read As Fallback |
| --- | --- | --- | --- | --- |
| Runtime control-plane persistence | `RuntimeSessionService` | `create_session_for_task`, `get_or_create_session_for_task_sync`, `start_node_attempt_sync`, `complete_node_attempt_sync`, `fail_node_attempt_sync`, `open_human_gate_sync`, `submit_gate_decision_sync`, `get_resume_control_sync` | runtime input payload facts intentionally exposed downstream, continuation checkpoints, gate/decision records, published-deliverable refs and review-contract bindings, runtime/read-model projections | shared WM truth, long-term memory truth, queue/broker/websocket truth, artifact-existence truth, memory-backend rows as runtime authority |
| MAS-agent memory application | `ContextContractAssembler`, `MemoryWriter`, `MemoryServices`, working/long-term memory interfaces | `ContextContractAssembler.resolve_published_stage_payload`, `ContextContractAssembler.assemble_agent_context`, `ContextContractAssembler.publish_script_review_boundary_sync`, `MemoryWriter.write`, `build_memory_services` | agent-facing context assembly, explicit fact snapshots, generation metadata, backend-configured memory CRUD | runtime/session/node/attempt/gate/decision truth, continuation authority, lease liveness, runtime recovery truth |
| SQL physical substrate | app DB, SQLite test DB, SQLite memory store, other configured persistence backends | runtime app DB via runtime services, `settings.MEMORY_WORKFLOW_BACKEND`, `SQLiteMemoryStore` | backend capability only; storage medium for higher-level owners | semantic owner layer by itself; proof that runtime and memory semantics are interchangeable |

## Claim Taxonomy
| Claim Family | Claim Subtype | Example Conclusions | Minimum Admissible Evidence | Not Admissible As Final Proof |
| --- | --- | --- | --- | --- |
| Runtime SQL claim | owner-path / boundary claim | `RuntimeSessionService` remains the sole owner of session/node/attempt/gate/decision truth; runtime exports facts only through explicit carriers; pre/post-exec seams use the intended runtime-session boundaries | boundary review plus focused SQLite-bounded unit evidence | memory-store tests, queue diagnostics, websocket projections, artifact presence |
| Runtime SQL claim | transaction-semantic claim | completion/failure sees the latest lease heartbeat; gate/decision/continuation state is fresh across sessions; runtime reads are correct under production-like isolation | MySQL-authoritative evidence on the production DB family / isolation semantics | SQLite unit tests, SQLite memory-store tests, static code review alone |
| Memory backend claim | interface claim | assembler/writer/provider consume runtime carriers without becoming runtime authority; memory backend remains replaceable behind service interfaces | boundary review plus interface-focused unit tests; SQLite-bounded acceptable when the selected backend scope is SQLite | runtime DB tests alone, queue/runtime projections |
| Memory backend claim | backend-contract claim | selected backend stores/retrieves agent facts, metadata, and tags correctly; serialization/durability behaves as expected for that backend | backend-contract tests on the selected backend; SQLite-bounded if SQLite is the selected backend | MySQL runtime tests alone, generic runtime authority tests |
| SQL physical substrate claim | topology/config claim | repo uses SQL in more than one context; SQLite appears both in tests and as one optional memory backend; backend selection is configuration-driven | code/config review | any inference about runtime authority or memory semantics without the higher-level owner contract |

## Conclusions That Must Be MySQL-Authoritative
- Any claim about runtime transaction freshness, isolation, or visibility under the production DB family.
- Any claim about lease heartbeat visibility or completion/failure validation across different sessions or transactions.
- Any claim about gate, decision, or continuation-checkpoint freshness when readers and writers do not share one session/transaction.
- Any claim that a `045`-class stale-snapshot runtime defect is fixed or absent in production-like semantics.

## Conclusions That Are Only SQLite-Bounded
- Owner-split and call-path conclusions such as:
  - runtime truth remains in `RuntimeSessionService`
  - runtime-to-agent facts travel through explicit carriers and adapters
  - `ContextContractAssembler` and `MemoryWriter` stay in the memory application layer
- Focused interface proofs that the current bounded seam uses the intended sessions/facades without asserting production isolation semantics.
- Memory-backend contract checks when the backend under test is explicitly SQLite-scoped.

## Allowed Runtime Facts and Memory Association Interface
- Allowed runtime-controlled carriers:
  - published deliverable refs and payload refs
  - script review contract
  - continuation checkpoint
  - runtime input payload facts intentionally exposed for downstream assembly
  - runtime/read-model projections built from runtime authority
- Allowed consumers:
  - `ContextContractAssembler` may resolve runtime-controlled carriers into agent-facing context
  - `MemoryWriter` may persist derivative fact snapshots and generation metadata only
  - `MemoryServices` and the selected backend may store memory items behind the memory interfaces
- Forbidden:
  - runtime bootstrap, resume, gate, or recovery logic reading shared WM or long-term memory as an authority fallback
  - runtime state-machine truth inferred from memory rows, queue state, websocket state, or artifact existence
  - memory backend results upgraded into runtime SQL correctness proof
  - backend unification work that treats memory persistence as interchangeable with runtime control-plane persistence

## Stage B Entrance Conditions
- No runtime implementation code changes until unresolved SQL-adjacent claims are inventoried and classified.
- If an open question is transaction-semantic, it must be routed to a MySQL-authoritative verification slice or successor runtime plan.
- If an open question is memory-backend-only, it must stay out of runtime implementation and be handled as a memory contract/backend concern.
- If a proposed follow-on mixes runtime authority and memory backend redesign, it fails the boundary gate and must be split.
