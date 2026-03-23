# Validation Checklist: PLAN-20260323-014
- Plan ID: PLAN-20260323-014
- Scope: successor correction verification only
- Status: superseded
- Updated At: 2026-03-23T13:01:39Z

## 1. Usage Rule
- This file owns the concrete verification for [PLAN-20260323-014](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260323-014.md).
- The plan owns sequencing, checkpoints, and architecture guardrails.
- This checklist owns focused tests, review evidence, and manual regression anchors.

## 2. Task A Validation: Published Deliverable Boundary Correction
- Boundary checks:
- [published_deliverable_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_service.py) 不再包含 direct shared WM get/put helpers
- published deliverable payload 组装由明确 stage-output builder 承担
- deliverable ref 投影回 shared WM 由明确 projection writer 承担
- Downstream checks:
- [memory_views.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py) 在 published `script` deliverable 缺失时不再 fallback 到 live shared WM
- image/video context builder 继续允许 live `scene_outputs.*` overlay，但不允许 stage-boundary truth 回退
- Equivalence checks:
- `with HITL + approve` 与 `wo HITL` 的 media 输入来源一致
- published deliverable 发布失败时出现显式错误或可见诊断，而不是静默降级
- Suggested evidence:
- focused backend unit tests around:
- script deliverable payload builder
- deliverable ref projection writer
- gate approve -> resume -> media read path
- negative-path proof for missing deliverable -> explicit diagnostic

## 3. Task B Validation: Project Explicit Composition and Dispatch Retirement
- Composition checks:
- [episode_orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/episode_orchestrator.py) 不再使用 `memory_services or build_memory_services()`
- project queued/direct path 使用显式 `EpisodeOrchestratorAgent.create_default()` 或显式注入 memory
- Retirement checks:
- `backend/app/core/mode_router.py` 已删除
- 没有生产调用路径再依赖 `dispatch_generation()`
- Adjacent drift checks:
- [audio_delivery_gate_evaluator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/audio_delivery_gate_evaluator.py) 不再隐式 build memory
- quick/project active path 不再新增 `memory_services or build_memory_services()` 漏口
- Suggested evidence:
- focused unit tests around project entry composition
- direct proof that project path no longer traverses `mode_router`
- `rg -n "or build_memory_services\\(|build_memory_services\\(" backend/app` review evidence, with active-path residuals either removed or explicitly out of scope
- Review result note:
- After Task B, no additional quick/project active-path implicit composition leak was found in the corrected scope.
- Remaining `build_memory_services()` matches are limited to explicit factories, project planning entry composition, and older support/legacy modules outside `014` scope; they should not be reinterpreted as unresolved `dispatch` or project-mainline drift.

## 4. Integration Validation
- Cross-boundary regression:
- `script approve -> resume -> image/video` 仍成功，但 publish/read path 已经过 builder + persistence + projection writer，而不是 service direct WM IO
- Documentation regression:
- [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md) 与代码当前组件映射一致

## 5. Checkpoint Evidence Log
- A checkpoint:
- passed
- Evidence:
- `py_compile` passed for published deliverable / orchestrator / memory view files
- `rg` confirmed [published_deliverable_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_service.py) no longer owns direct shared WM helpers
- direct proof: missing published script deliverable now raises explicit `ValueError` in image/video context builders
- direct proof: published script deliverable remains readable for downstream media context after projection
- default pytest: `tests/unit/test_published_deliverable_service.py tests/unit/test_episode_orchestrator_style.py` passed with a realistic timeout window (`3 passed`)
- default pytest: `tests/unit/test_runtime_session_service.py tests/unit/test_workflow_completion_adapter.py` passed (`7 passed`)
- default pytest: `tests/unit/test_working_memory_service.py` passed (`4 passed`) after correcting the test to seed `scene_outputs.image` before asserting video-generation readiness, which matches the existing downstream contract instead of relaxing the implementation boundary
- default pytest: `tests/unit/test_tasks_endpoint.py` passed (`5 passed`)
- Result:
- passed; earlier timeout noise was explained by import/collection overhead under overly aggressive shell `timeout` windows rather than contradictory Task A assertion failures
- B checkpoint:
- passed
- Evidence:
- `py_compile` passed for project composition and queue host files
- `rg -n "mode_router|dispatch_generation" backend/app backend/tests` returned no remaining production/test references after deletion
- focused pytest: `tests/unit/test_task_queue.py -k "run_generation_in_host"` passed for quick + project host routing
- static review: `rg -n "build_memory_services\\(|or build_memory_services\\(" backend/app` found no new quick/project active-path implicit composition leak after `014`; remaining hits are limited to explicit factories, the project planning entry, and support/example modules outside the dispatch-retirement scope
- direct proof: `AudioDeliveryGateEvaluator()` and `EpisodeOrchestratorAgent()` now fail fast without explicit `memory_services`
- direct proof: `queued_task_execution_host.run_generation_in_host(PROJECT, ...)` now routes directly through `EpisodeOrchestratorAgent.create_default()`
- direct proof: `projects._run_episode_orchestration(...)` now routes directly through `EpisodeOrchestratorAgent.create_default()`
- default pytest: `tests/unit/test_audio_orchestration_runtime_gate.py` passed (`58 passed`)
- default pytest: `tests/unit/test_task_queue.py -k "run_generation_in_host"` passed (`2 passed, 6 deselected`)
- Result:
- passed; earlier timeout noise was explained by slow import/collection under too-short shell timeouts, and focused default pytest runs now pass in the corrected scope
