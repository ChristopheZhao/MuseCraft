Principles for Agents and Tools (Addendum)

This document clarifies state boundaries and terminology used by agents, in addition to existing design docs (see PHASE_2_MULTI_AGENT_SYSTEM_DESIGN.md).

Inner State vs WF vs Memory

- inner_react_state
  - Definition: The agent’s internal, multi‑turn ReAct lifecycle state. It is the single source of truth for planning, idempotency and completion within a sub‑task.
  - Content (examples): completed/failed scenes, prepared continuity materials, results ledger (per‑round outputs), iteration history (per‑round summaries), minimal metrics.
  - Usage: Drives next‑round observation and planning; persists across the agent’s lifecycle for the current task.

- WF (WorkflowState)
  - Definition: Cross‑agent, externally consumable state. Records final assets that downstream agents and the UI rely on.
  - Write timing: Only write on sub‑agent completion (or orchestrator aggregation). Do not write mid‑iteration to avoid mixing layers.

- Memory
  - Definition: Storage/knowledge backend for persistence, recovery and reuse (e.g., checkpoints, lightweight summaries). Not a control‑plane truth source.
  - Scope: Use namespaces (e.g., inner/task, wf/workflow, global/tenant) for isolation and retention policies. Store pointers/URLs for large artifacts.

Layering Rules

- Completion criteria: Only inner_react_state determines “done/skip/retry” inside an agent. WF and Memory must not be used as completion truth sources.
- Mid‑iteration writes: Avoid writing WF during iterations. Keep WF as the final, externally stable view of assets.
- Observations: May read WF/Memory for supplementary facts (e.g., continuity references), but do not let them override inner completion truth.
- Idempotency: Check inner_react_state before execution; skip if asset exists. Do not depend on WF for idempotency.

Function‑Calling and Tools

- Schema‑first: Expose clear input schemas with required fields (e.g., scene_number). Enforce validation at the tool layer; avoid prompt‑level parameter rules.
- Supplier‑agnostic: Keep tool interfaces neutral; inject provider capabilities via config/context.
- Safety & neutrality: Do not leak tool names/parameter ranges into prompts; let schemas and validation carry constraints.

Recovery & Observability

- Results ledger & iteration history: Record per‑round outputs and summaries in inner_react_state to enable replay, audits and front‑end progress.
- Checkpointing (optional): Use Memory to persist inner_react_state snapshots (thread/checkpoint model) for resume/replay without re‑execution.
- Streaming progress: Emit events (SSE/WS) from agent milestones (act/reflect/complete) using inner_react_state as the data source.

Rationale

- Clear separation of concerns reduces ambiguity, simplifies debugging, and prevents cross‑layer feedback loops.
- Single‑source truth (inner_react_state) ensures consistent idempotency and planning, while WF remains a stable external contract.

