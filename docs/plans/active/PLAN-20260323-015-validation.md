# Validation Checklist: PLAN-20260323-015
- Plan ID: PLAN-20260323-015
- Scope: successor correction verification only
- Status: completed
- Updated At: 2026-03-23T09:03:08Z

## 1. Usage Rule
- This file owns the concrete verification for [PLAN-20260323-015](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260323-015.md).
- The plan owns sequencing, checkpoints, and architecture guardrails.
- This checklist owns focused tests, review evidence, and manual regression anchors.

## 2. Task A Validation: Image Path Boundary Purity
- Boundary checks:
- [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) image path no longer injects live `scene_overview` / `scene_scripts` alongside published-deliverable-based image context
- image path may still receive non-stage-boundary overlays, but not duplicate script-stage truth
- Equivalence checks:
- `with HITL + approve` and `wo HITL` image-stage inputs come from the same published deliverable source
- No dual-source prompt/context remains for `IMAGE_GENERATOR`
- Suggested evidence:
- focused unit tests for image context construction
- direct review evidence showing `_merge_media_context` no longer contributes live script-stage facts to image path

## 3. Task B Validation: Deliverable Runtime Ownership Repatriation
- Boundary checks:
- [published_deliverable_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_service.py) no longer writes `session.input_payload`
- runtime/control-plane caller now writes deliverable ref into runtime payload explicitly
- Read-path checks:
- publish/approve -> resume still carries the correct published deliverable ref
- No new dual-write location is introduced
- Suggested evidence:
- focused unit tests around publish + approve runtime payload writeback
- direct review evidence that service returns deliverable/ref only

## 4. Integration Validation
- `script approve -> resume -> image` consumes one formal script-stage source only
- `script approve -> resume -> video` remains unchanged and still consumes the published deliverable path
- Broader active-path backend regression passed on current-architecture-aligned unit/runtime suites:
- `tests/unit/test_task_queue.py`
- `tests/unit/test_tasks_endpoint.py`
- `tests/unit/test_runtime_session_service.py`
- `tests/unit/test_workflow_completion_adapter.py`
- `tests/unit/test_working_memory_service.py`
- `tests/unit/test_published_deliverable_service.py`
- `tests/unit/test_orchestrator_runtime_mainline.py`
- `tests/unit/test_audio_orchestration_runtime_gate.py`
- `tests/unit/test_episode_orchestrator_style.py`
- `tests/unit/test_orchestrator_image_context_boundary.py`
- Result: `92 passed`

## 5. Regression Scope Filter
- Excluded from this regression pass as architecture-stale or legacy harness tests:
- `backend/tests/integration/test_background_music.py`
- `backend/tests/e2e/test_final_integration.py`
- `backend/tests/e2e/test_complete_mas_system.py`
- `backend/tests/integration/test_api_workflow.py`
- `backend/tests/integration/test_mas_collaboration.py`
- Exclusion rationale:
- These files still rely on global `set_memory_services(...)`, `get_working_memory_service()` singleton harnesses, direct `OrchestratorAgent()` construction without explicit memory injection, or legacy WorkflowState/script-style manual e2e flows that no longer match the post-014/post-015 runtime boundary design.

## 6. Checkpoint Evidence Log
- A checkpoint:
- passed
- Evidence:
- [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) no longer injects `_merge_media_context(include_roles=True)` for `IMAGE_GENERATOR`; image static context is built only from `build_image_generation_context(...)`.
- Focused regression passed: `backend/tests/unit/test_orchestrator_image_context_boundary.py`
- Result:
- image path now consumes a single script-stage truth source and no longer mixes live WM `scene_overview/scene_scripts` with published-deliverable image context
- B checkpoint:
- passed
- Evidence:
- [published_deliverable_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_service.py) no longer writes `session.input_payload`
- Publish-path writeback now happens in [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py); approve-path writeback now happens in [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py)
- Focused regressions passed:
- `backend/tests/unit/test_published_deliverable_service.py::test_publish_script_deliverable_persists_payload_without_direct_wm_projection`
- `backend/tests/unit/test_published_deliverable_service.py::test_submit_gate_decision_approve_marks_deliverable_approved`
- `backend/tests/unit/test_runtime_session_service.py::test_submit_gate_decision_marks_revision_state`
- Result:
- runtime/control-plane ownership of payload mutation is restored; deliverable persistence is persistence/ref-only again
