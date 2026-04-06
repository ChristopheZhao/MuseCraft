# Planner / Execution / Output / Progress Boundary Freeze (2026-04-02)

## Scope
- Freeze the owner and authority boundaries for the four surfaces that were conflated in the current `video_generator` incident:
  - planner priors
  - execution contract
  - output contract
  - progress read-model
- This document is architectural and normative. It does not define a new runtime carrier by itself.

## Root Problem
- The current implementation mixed semantic planning input, execution-only binding, delivery validation, and progress projection into the same decision chain.
- That drift produced two failure modes:
  - `workflow_state_id` became an LLM-facing function-call burden instead of an execution-context binding.
  - `progress_read_model` started treating helper-call success as delivery success and then leaked into completion semantics.

## Boundary Matrix
| Surface | Owner | Input Surface | Output Surface | Allowed responsibilities | Forbidden responsibilities |
| --- | --- | --- | --- | --- | --- |
| `planner priors` | prompt/template design + context assembly | task goal, static context, source-mapped read-model, tool business schema | planner reasoning and tool selection only | provide semantic priors, dependencies, scene membership, concise progress hints | execution binding, storage scope, lease/route ids, planner-owned completion truth |
| `execution contract` | MAS control plane / orchestrator / execution dispatcher | workflow runtime identity, execution policy, host/attempt metadata, timeout/storage constraints | tool execution envelope / pre-execution validation | bind runtime scope, inject execution-only context, fail closed on illegal execution envelope | require LLM to echo runtime ids, become planner-visible semantic input, own delivery truth |
| `output contract` | delivery acceptance boundary | raw tool results, normalized artifacts, publish requirements | `delivery_receipt` / `publish_acceptance` | validate that outputs are structurally complete and publishable, emit delivery acceptance facts consumable by completion logic | rewrite planner semantics, infer execution scope, let raw helper/tool success act as completion truth |
| `progress read-model` | context-editing / planner-input adapter | authoritative execution receipts and/or published artifact facts | planner-visible derived progress projection | summarize planned/completed/remaining work, stabilize long-horizon planning | derive delivery truth from helper calls, own completion authority, write back planner-owned truth |

## Required Rules Per Surface

### 1. Planner Priors
- Planner priors are semantic hints, not execution contracts.
- Planner priors may shape model choices through:
  - prompt templates
  - static context
  - planner-visible derived read-models
  - tool business schemas
- Planner priors must not force the model to carry execution bookkeeping such as:
  - `workflow_state_id`
  - storage scope refs
  - lease ids
  - attempt ids
- No separate planner-side runtime contract object is required. If a planner needs a fact, it must be a semantic fact, not a transport or storage binding.

### 2. Execution Contract
- Execution contract is execution-only.
- `workflow_state_id` is a workflow-scoped runtime binding and belongs here.
- `workflow_state_id` must be injected through the execution envelope or tool context, not through LLM-facing function-call business parameters.
- Execution contract may validate:
  - scope identity
  - attempt/host liveness binding
  - timeout/storage policy
  - execution-only flags explicitly owned by control plane
- Execution contract must not be used as a semantic planning surface.
- Execution contract must not rely on the model to retype or remember execution-only bindings.

### 3. Output Contract
- Output contract is distinct from execution contract.
- Output contract validates whether a tool result is sufficient to count as a publishable or committable delivery.
- Output contract is the only boundary that may emit delivery-acceptance facts such as:
  - `delivery_receipt`
  - `publish_acceptance`
- Typical output-contract concerns include:
  - required artifact presence
  - scene-to-artifact mapping completeness
  - publishable path/url availability
  - normalization completeness
- Completion logic must consume delivery-acceptance facts from this boundary, not raw helper/tool success.
- Output contract must not decide how the planner should reason.
- Output contract must not be overloaded with execution-envelope validation.

### 4. Progress Read-Model
- Progress read-model is a derived, rebuildable, non-authoritative planner aid.
- It may summarize:
  - planned membership
  - successful deliveries
  - remaining work
  - short execution notes
- Progress read-model must be source-mapped to authoritative facts only.
- Progress read-model must not promote helper or preparation success into delivery success.
- Progress read-model must not become an independent completion authority.

## Progress Projection Provenance Rule
- Every stable progress projection must carry explicit provenance metadata.
- Minimum provenance fields:
  - `derived_from`
  - `last_receipt_watermark`
  - `projection_time`
  - `max_staleness_seconds`
- `derived_from` must identify the authoritative fact surfaces used to build the projection.
- `last_receipt_watermark` must identify the latest accepted execution/delivery fact included in the projection.
- `projection_time` must identify when the projection was built.
- `max_staleness_seconds` must identify the tolerated freshness budget for planner consumption.
- Any progress projection without explicit provenance is incomplete and must not be treated as a stable planner-visible surface.
- Queue/broker/worker health, helper-call success, and other non-authoritative transport signals must not appear in `derived_from` for delivery progress.

## Authority and Completion Rules
- Completion authority remains single-owned.
- For media generation agents, completion truth belongs to MAS runtime SoT plus accepted delivery facts, not planner prose.
- Planner text such as `task_complete=true` may request loop termination, but it must not override missing delivery facts.
- Helper/preparation success is not equivalent to delivery success.
- A planner-visible progress projection may inform the model that work appears complete, but final completion must still align with authoritative execution and delivery facts.

## Runtime Identity Rule
- `workflow_state_id` is a workflow-scoped runtime identity, not a semantic business parameter.
- It may exist in:
  - orchestrator runtime state
  - execution contract
  - tool execution context
  - audit/telemetry metadata
- It must not exist as a required LLM-facing business argument for normal tool planning.
- If a tool internally needs `workflow_state_id` for DAG lookup, continuity registration, or storage policy, the execution layer must provide it implicitly.

## Progress Projection Rule
- `planned_scene_numbers` may derive from authoritative scene membership surfaces such as `scene_info_ref`.
- `successful_scene_numbers` may derive only from authoritative execution receipts and/or accepted delivery facts.
- Any projection path that marks a scene successful from helper-only calls is invalid.
- Any projection path that can by itself cause final completion is invalid.

## Explicit Non-Goals
- No new planner-owned runtime contract object.
- No second completion authority surface.
- No compatibility shim that preserves LLM-facing `workflow_state_id` as a long-term mainline.
- No helper-call heuristics promoted into stable delivery truth.

## Diagnostic Implications
- Missing execution binding is an execution-boundary failure, not a semantic planning failure.
- Missing publishable artifacts is an output-boundary failure, not an execution-scope failure.
- Repeated or false-complete planning under long histories is a progress-read-model or planner-quality issue, not evidence that execution or output contracts should move into planner space.

## Code Anchors
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py)
- [react_agent.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/react_agent.py)
- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py)
- [plan_context.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/utils/plan_context.py)
- [base.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/base.py)
- [base_tool.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/tools/base_tool.py)
- [video_generation_tool_v2.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/video_generation_tool_v2.py)
- [video_execution_contract.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/video_execution_contract.py)

## Related References
- [orchestration_context_memory_boundary_freeze_20260330.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/orchestration_context_memory_boundary_freeze_20260330.md)
- [scene_contract_v2_freeze_20260329.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/scene_contract_v2_freeze_20260329.md)
- [PLAN-20260331-043-progress-read-model-note.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260331-043-progress-read-model-note.md)
- [2026-04-01-derived-heuristic-gate-drift-thread.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/experience/sources/2026-04-01-derived-heuristic-gate-drift-thread.md)
