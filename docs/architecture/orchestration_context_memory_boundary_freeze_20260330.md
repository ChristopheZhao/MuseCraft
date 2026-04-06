# Orchestration / Context / Memory Boundary Freeze

- Date: `2026-03-30`
- Scope: `PLAN-20260329-038` Sprint 4
- Purpose: freeze owner boundaries for orchestration, context assembly, memory writeback, working memory, and consistency assets after `PLAN-20260330-039` removed the external runtime blocker.

## Owner Matrix

| Surface | Owner | Allowed responsibilities | Forbidden responsibilities |
| --- | --- | --- | --- |
| `OrchestratorAgent` | MAS control plane | schedule agents, pass execution contracts, update runtime session/node state, write Shared WM facts that are part of the MAS mainline | infer business truth from queue/worker state, bypass published-boundary contracts, hide runtime errors via fallback |
| `ContextContractAssembler` | read-model / boundary adapter | read published deliverables and Shared WM facts, build downstream static context, persist `scene_info_ref`, fail closed when required boundary inputs are missing | mutate runtime state, synthesize fallback payloads from stale Shared WM when required published refs are absent, become a repair layer |
| `MemoryWriter` | standardized long-term writeback | persist explicit fact snapshots and lightweight generation metadata to long-term memory | persist runtime status, gate decisions, queue handles, task specs, or planning authority |
| `WorkingMemoryService` | short-term memory lifecycle | create/get/reset MAS and agent scopes, preserve MAS scope while cleaning agent scopes, expose controlled write API | own business rules, synthesize boundary payloads, silently promote agent scope into MAS SoT |
| `ConsistencyTool` | prompt-asset collector | read `scene_info_ref`, collect style/character/opening/continuity assets, explicitly register final-frame references for continuity | own scene ordering, retries, runtime decisions, gate state, or a second continuity state machine |

## Read / Write Path Mapping

- Runtime SoT writes remain in control-plane services and orchestrator runtime transitions.
- `ContextContractAssembler` is read-only with one explicit storage side effect: persisting `scene_info_ref` for media-agent boundary input.
- Shared WM remains the MAS fact surface:
  - MAS scope stores project/scene facts.
  - agent scopes are scratchpads derived from MAS scope and are disposable.
- `MemoryWriter` writes only to long-term memory services and ignores unknown output fields.
- `ConsistencyTool.get_prompt_assets` is read-only.
- `ConsistencyTool.register_reference` is the explicit continuity-reference write path and only stores final-frame references.

## Forbidden Fallback Paths

- Do not rebuild required downstream script/image/video boundaries from stale Shared WM when a published deliverable ref is missing.
- Do not let `MemoryWriter` persist runtime status, queue state, gate state, or planning contracts “for convenience”.
- Do not let `WorkingMemoryService.cleanup_workflow()` clear MAS scope facts; only agent scopes are disposable there.
- Do not let `ConsistencyTool` or prompt composers hold retry, reconcile, or execution-order semantics.
- Do not introduce Shared WM fallback as a silent repair for broken context boundaries.

## Evidence Anchors

- `ContextAssembler` fail-closed boundary tests:
  - `backend/tests/unit/test_execution_boundary_assembler_contexts.py`
- WorkingMemory scope-boundary tests:
  - `backend/tests/unit/test_working_memory_service.py`
- Consistency asset contract tests:
  - `backend/tests/unit/test_consistency_asset_contract_v2.py`
  - `backend/tests/unit/test_consistency_tool_boundary.py`
- MemoryWriter boundary tests:
  - `backend/tests/unit/test_memory_writer_boundary.py`
