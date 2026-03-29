# Validation Ledger: PLAN-20260328-035

## Scope
- Plan:
  - [PLAN-20260328-035.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260328-035.md)
- Goal:
  - isolate the clean quick-run `script -> image` prerequisite gap without reopening image provider size contract or weakening published-deliverable fail-fast behavior

## Phase 0
- Status: completed
- Planned checks:
  - capture authoritative runtime/task/log evidence for the new workflow-path defect exposed after `034` live smoke
  - freeze the issue owner to runtime/orchestration prerequisite enforcement rather than `ContextAssembler`, queue transport, or provider integration
  - create a managed successor before any implementation discussion
- Evidence:
  - runtime view for task `756a5a91-1d84-4f79-8b68-a3baf2fb9ec9` showed `status=failed`, `current_node_key=image`, `concept=completed`, `script=queued`, and `image=failed`
  - task detail for the same task recorded `current_step="Executing image_generator"` and the same `missing_runtime_input_ref` error
  - worker/orchestrator logs from the clean-stack live smoke showed `Completed workflow step 1/5: concept_planner` immediately followed by `Starting workflow step 2/5: image_generator`
  - [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) explicitly requires a published `script` stage payload for `IMAGE_GENERATOR`, `VIDEO_GENERATOR`, `VOICE_SYNTHESIZER`, and `AUDIO_GENERATOR`, and raises `missing_runtime_input_ref` when absent
  - [orchestration_queue_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_queue_policy.py) currently shapes the execution queue from `task_specs.order/run` only, without expressing a stage prerequisite such as `script` before script-consuming agents
- Results:
  - the new defect is frozen as a runtime/orchestration prerequisite gap
  - `ContextAssembler` fail-fast remains the correct diagnostic boundary and is not the patch point
  - the next phase is narrowed to identifying the single control-plane owner that must enforce `script` prerequisites in the initial quick-run path

## Phase 1
- Status: completed
- Planned checks:
  - audit the full control-plane path from candidate selection and task decomposition to execution queue shaping and runtime-input published-deliverable projection
  - decide whether the current issue is only a dispatch-order problem or also an approval/runtime-input projection problem
  - verify whether prerequisite enforcement must cover only initial queue build or also runtime standby activation and final dispatch gating
  - verify whether `prefer_approved=True` is currently enforced or only recorded as diagnostics metadata
  - freeze a minimal architecture-safe fix direction without adding a second SoT, Shared WM fallback, or loader-side silent recovery
- Evidence:
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) builds the initial quick-run queue from LLM-selected `candidate_agents` plus LLM-decomposed `task_specs`, then feeds them through [orchestration_queue_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_queue_policy.py), which currently honors only `order/run` and does not encode `script` as a mandatory prerequisite producer for script-consuming nodes
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) writes the script deliverable ref into `session.input_payload.published_deliverables["script"]` at gate-open time inside `complete_script_attempt_and_open_review_gate_sync(...)`, then overwrites the same slot with the approved ref during `submit_gate_decision_sync(... approve ...)`
  - [published_deliverable_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_service.py) already carries `is_candidate` and `is_approved` in the deliverable ref, so no second approval store is needed
  - [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) `resolve_published_stage_payload(... prefer_approved=True ...)` currently treats `prefer_approved` as metadata only; it resolves any present ref and does not reject candidate refs based on approval state
  - subagent review confirmed the semantic widening: `session.input_payload.published_deliverables` is currently mixing review-time candidate preview refs and downstream runtime-input refs, which expands the meaning of `approved`
- Results:
  - the defect is not just queue order; it is a combined control-plane contract gap:
    - runtime/orchestration does not enforce the `script` producer prerequisite before dispatching script consumers
    - runtime-session projection writes candidate refs into a downstream runtime-input surface that should be approved-only
  - the minimal architecture-safe fix direction is frozen as:
    - keep `WorkflowPublishedDeliverable` as the single approval/content SoT
    - make `session.input_payload.published_deliverables` an approved-only downstream projection
    - keep candidate review refs on existing gate/attempt review surfaces only
    - keep `ContextAssembler` read-only and fail-fast, with no Shared WM fallback
    - enforce mandatory `script` prerequisite in control-plane queue shaping / dispatch gating rather than in leaf agents or loader-side rescue logic
  - implementation review further narrowed the required cut:
    - prerequisite enforcement must cover initial `build_execution_queue`, runtime `activate_from_standby` insertion, and final pre-dispatch eligibility checks
    - `prefer_approved=True` must become a real read-side enforcement on the existing ref contract so unapproved refs cannot satisfy downstream runtime input
    - review surfaces remain sufficient for candidate preview, so approved-only projection does not require a parallel preview store

## Phase 2
- Status: completed
- Planned checks:
  - tighten the write-side runtime projection so `session.input_payload.published_deliverables` carries approved downstream refs only
  - enforce `prefer_approved=True` as a read-side contract without adding Shared WM fallback or a second approval store
  - enforce the `script` producer prerequisite across initial queue build, runtime standby activation, and pre-dispatch dispatch gating
  - update focused unit coverage and rerun the narrow `uv` regression suite
- Evidence:
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) `complete_script_attempt_and_open_review_gate_sync(...)` now clears the `script` runtime projection at gate-open, and `submit_gate_decision_sync(...)` writes the approved ref only on `approve` while clearing it on `revise/replan`
  - [published_deliverable_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_service.py) exposes `clear_published_deliverable_ref(...)` so runtime-session write paths can remove stale runtime projections without inventing a second storage surface
  - [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) now raises `runtime_input_ref_not_approved` when `prefer_approved=True` receives an unapproved runtime ref
  - [orchestration_queue_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_queue_policy.py) reorders script-consuming agents behind `SCRIPT_WRITER` during initial queue build and defers standby insertion until after any pending `SCRIPT_WRITER`
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) now performs a pre-dispatch `script_prerequisite_not_satisfied` gate before a script consumer can be marked running
  - focused regression command passed from `backend/`:
    - `PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/test_runtime_session_service.py tests/unit/test_execution_boundary_assembler_contexts.py tests/unit/test_audio_orchestration_runtime_gate.py tests/unit/test_orchestrator_runtime_mainline.py -q`
    - result: `90 passed, 2 warnings`
- Results:
  - approved-only downstream projection now holds at the runtime-session write boundary; candidate preview remains on gate/attempt review surfaces only
  - `prefer_approved=True` is now a true read-side contract check on the same deliverable ref model rather than a diagnostics-only hint
  - script-consuming agents can no longer slip ahead of `script_writer` through initial queue order, standby activation insertion, or pre-dispatch dispatch of a bad/missing runtime projection
  - functional regression is closed, but follow-up architecture review found a separate planning-state owner drift, so lifecycle closeout is reopened into Phase 3 instead of moving to `completed`

## Phase 3
- Status: completed
- Planned checks:
  - prove the exact root cause that pulled `OrchestrationStateAdapter` into mainline ownership and created a dual-carrier planning state
  - converge planning-state authoritative ownership onto a single source and remove Shared WM planning projection from mainline semantics
  - move `runtime_hints / execution_contract` derivation out of `ContextAssembler` so deleting the Shared WM projection cannot silently change runtime behavior
  - verify queue/control-plane prerequisite ownership remains single-owner after removing duplicate consumer-set definitions
  - update focused tests to follow the new owner boundaries and catch silent regressions in `VIDEO_GENERATOR.generate_audio` and `VIDEO_COMPOSER.compose_mode`
- Evidence:
  - deep architecture review traced the exact crossing point to `_load_authoritative_resume_task_specs(...) -> load_active_script_continuation_sync(...) -> hydrate_continuation_checkpoint(...) -> persist_task_specs(...)`, which makes checkpoint-derived planning state authoritative while also writing it back into Shared WM for continued mainline consumption
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) now reads resume planning state directly from `checkpoint_to_task_specs(...)`, builds per-agent execution contracts via `_build_agent_execution_contract(...)`, and injects scheduled-agent input through `_prepare_scheduled_agent_input(...)` without asking `ContextAssembler` to read planning state
  - [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) no longer exposes `resolve_runtime_hints(...)` or `build_execution_contract(...)`; it remains a published-deliverable/static-boundary assembler with fail-fast read-side enforcement only
  - [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) now retains only checkpoint build/validate/decode plus audio-contract and trace helpers; `hydrate_continuation_checkpoint(...)`, `persist_task_specs(...)`, and `load_task_specs(...)` are removed
  - [orchestration_runtime_controller.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_runtime_controller.py) no longer persists planning or activation-pool state during `activate_from_standby`; it appends trace only
  - [orchestration_queue_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_queue_policy.py) now owns the single `requires_approved_script_input(...)` predicate used by both queue shaping and orchestrator dispatch gating
  - the remaining Shared WM compat projections `workflow.diagnostics.compat.plan_snapshot`, `workflow.diagnostics.compat.activation_pool_snapshot`, and `workflow.diagnostics.compat.audio_route_snapshot` were also removed from app code to eliminate the residual shadow-SoT risk surface
  - subagent root-cause analysis confirms `workflow.task_specs` began as a Shared WM projection, later became a live execution input, and was never retired after `continuation_checkpoint` became the authoritative resume carrier
- Results:
  - planning-state authoritative ownership is converged onto `continuation_checkpoint`; Shared WM no longer carries a parallel planning-state path
  - `ContextAssembler` is back to a read-side boundary owner only and no longer participates in execution-contract or planning-state semantics
  - control-plane ownership remains separated from queue/transport ownership, with prerequisite semantics expressed once in queue policy and enforced again at dispatch by orchestrator without a second rule table
  - helper/adapter code is demoted back to pure conversion/validation/trace responsibilities; no hot-path helper now mutates planning state into Shared WM
  - focused backend `uv` regression passed:
    - `PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/test_orchestrator_runtime_mainline.py tests/unit/test_audio_orchestration_runtime_gate.py tests/unit/test_runtime_session_service.py tests/unit/test_execution_boundary_assembler_contexts.py tests/unit/test_video_generator_audio_route_injection.py tests/unit/test_video_composer_execution_boundary.py -q`
    - result: `103 passed, 2 warnings`

## Notes
- 2026-03-28T08:31:03Z created this successor after user-confirmed closeout of `034`. The image-size contract is now done; only the separate `script -> image` runtime gap carries forward.
- 2026-03-28T08:49:44Z completed Phase 1 design freeze. The plan now explicitly treats approved-only downstream projection and script-producer prerequisite enforcement as the two relevant control-plane responsibilities, while keeping approval/content truth in the existing published-deliverable model and forbidding loader fallbacks or extra SoT layers.
- 2026-03-28T09:00:53Z implementation review clarified the remaining execution scope: fixing only initial queue order would be insufficient because runtime standby activation can still insert script consumers, and write-side projection tightening alone would be insufficient because `prefer_approved` still needs explicit read-side enforcement.
- 2026-03-28T13:27:41Z completed Phase 2 implementation and focused regression. Functional regression closed, but this is no longer the end of the stream.
- 2026-03-28T14:03:56Z post-implementation architecture review found that `continuation_checkpoint` became the authoritative resume source without retiring the old Shared WM `workflow.task_specs` consumer path. The plan is therefore reopened in Phase 3 to remove the dual-carrier planning state, demote adapter/helper code back to non-owner roles, and complete the refactor in one pass rather than preserving compatibility seams.
- 2026-03-28T15:00:48Z completed Phase 3 and final shadow-SoT cleanup. The refactor now removes both the Shared WM planning-state projection and the remaining `workflow.diagnostics.compat.*` projection surfaces, leaving `continuation_checkpoint` as the sole planning-state carrier and `workflow.replan_trace` as the only retained runtime trace projection in this slice.
