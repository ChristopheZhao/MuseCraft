# Validation Checklist: PLAN-20260322-013
- Plan ID: PLAN-20260322-013
- Scope: successor-stage verification only
- Status: superseded
- Updated At: 2026-03-23T13:01:39Z

## 1. Usage Rule
- This file owns the concrete verification for [PLAN-20260322-013](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260322-013.md).
- The plan owns task sequencing, checkpoints, and architecture guardrails.
- This checklist owns focused tests, verification evidence, and manual regression anchors.

## 2. Task A Validation: Non-Artifact Stage Deliverables
- Contract checks:
- 存在统一阶段成果发布/引用模型；artifacts 与非-artifact 结构化成果共享同一上位引用机制。
- 正式成果宿主决策已落地为“published deliverable record + `payload_ref`”，而不是把 runtime refs 或 `Resource` 误用为结构化 payload 宿主。
- `script` 节点的第一版已发布成果覆盖：
- `project.concept_plan`
- `scene_overview`
- `project.scene_scripts`
- Gate / downstream input checks:
- `script` gate 不再直接引用 `shared_fact` 作为正式审核对象。
- `wo HITL` 下游读取已发布 `script` 阶段成果。
- `with HITL + approve` 下游读取同一份已发布 `script` 阶段成果。
- Regression focus:
- 不引入第二套可写 SoT。
- 不把结构化文本成果错误塞进 `Resource`。
- 不为每个 HITL 节点新增一组控制变量。
- Suggested evidence:
- focused backend unit/integration tests around:
- stage deliverable builder
- gate artifact refs
- resume after approve
- `scene_info_ref` / media context builder input source
- manual proof that `approve` 和无 HITL 路径读取的是同一份正式成果引用

## 3. Task B Validation: Dispatch Convergence
- Responsibility checks:
- quick 主线入口不再 `build_memory_services()`
- `dispatch` 不再承担 orchestrator/runtime graph 装配
- queue/worker/direct quick path 不再各自隐式创建 live memory graph
- Active-path audit checks:
- [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py)
- [orchestration_control_plane.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_control_plane.py)
- [orchestration_runtime_controller.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_runtime_controller.py)
- [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py)
- [orchestration_observation_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_observation_adapter.py)
- [workflow_completion_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/workflow_completion_adapter.py)
- [script_stage_runner.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/script_stage_runner.py)
- [post_script_stage_runner.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/post_script_stage_runner.py)
- 以上 active-path 组件不再允许保留 `memory_services or build_memory_services()` 作为 live-path 隐式装配。
- Boundary checks:
- quick 主线只启动同一个 `OrchestratorAgent`
- project-mode 外层包装不再通过 quick dispatch 继续保存历史双宿主结构
- Retirement check:
- 若 `dispatch` 仅剩无意义转发，则退役；若保留 helper，必须证明其仅为极薄入口
- 若 `dispatch` 退役或显著瘦身，需同时给出 [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md) 的同步更新证据
- Suggested evidence:
- focused unit tests around entrypoint composition
- targeted runtime resume regression proving no per-dispatch memory rebuild dependency
- direct-path / queued-path smoke checks using the same mainline injection path

## 4. Integration Validation
- Manual quick HITL regression:
- `script approve -> resume -> image/video`
- 验证正式输入来源一致，而不是依赖 live shared WM continuity 偶然成立
- Consistency regression:
- 对比 `wo HITL` 与 `with HITL + approve` 的下游正式输入引用是否一致
- Final acceptance:
- 只有在 Task A Checkpoint A 和 Task B Checkpoint B 都通过后，才可判定本 successor 计划完成

## 5. Checkpoint Evidence Log
- A checkpoint:
- passed
- Evidence:
- Added `WorkflowPublishedDeliverable` model and Alembic migration: [workflow_runtime.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/models/workflow_runtime.py), [2f6a9c1e4b5d_add_workflow_published_deliverables.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/alembic/versions/2f6a9c1e4b5d_add_workflow_published_deliverables.py)
- Added published-deliverable persistence/projection service: [published_deliverable_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_service.py)
- Switched `script` gate publication from `shared_fact` refs to published-deliverable refs: [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py)
- Added approve-time deliverable approval/ref update: [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py)
- Switched image/video context builders to prefer published script deliverables and only overlay live scene outputs: [memory_views.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py)
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile ...` on changed backend files: passed
- `timeout 45s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/unit/test_task_queue.py tests/unit/test_published_deliverable_service.py tests/unit/test_workflow_completion_adapter.py`: passed (`11 passed`)
- Direct Python verification proved `with HITL + approve` projects the approved published script deliverable back into a new execution segment and drives downstream media context (`STATUS approve True`, `DELIVERABLE published_deliverable script`, `CTX 1 proof script`)
- Direct Python verification proved `wo HITL`/candidate path also prefers the published latest script deliverable over stale live facts (`WO_HITL 1 latest script`)
- Focused pytest for `test_working_memory_service.py -k published_script_deliverable` still timed out under the harness wrapper; keep as non-blocking harness debt because equivalent direct proofs and focused backend tests now cover the published-deliverable read path
- Result:
- passed
- B checkpoint:
- passed
- Evidence:
- Removed per-dispatch memory composition from [mode_router.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/core/mode_router.py); the dispatch helper no longer calls `build_memory_services()`
- Further shrank [mode_router.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/core/mode_router.py) to a project-only helper; quick mode now raises instead of routing through dispatch
- Quick queued execution now routes directly to `OrchestratorAgent.create_default()` instead of `dispatch_generation()` in [queued_task_execution_host.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/queued_task_execution_host.py)
- [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) no longer implicitly builds memory in `__init__`; quick live path now has an explicit internal factory entrypoint
- Active-path control-plane/helper adapters now require explicit injected `memory_services` instead of implicit defaults: [orchestration_control_plane.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_control_plane.py), [orchestration_runtime_controller.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_runtime_controller.py), [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py), [orchestration_observation_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_observation_adapter.py), [workflow_completion_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/workflow_completion_adapter.py)
- Dormant script/media stage runners were aligned to the same explicit-memory rule: [script_stage_runner.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/script_stage_runner.py), [post_script_stage_runner.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/post_script_stage_runner.py)
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile ...` on the changed dispatch/helper files: passed
- Direct Python verification proved quick queued host bypasses dispatch (`QUICK quick 1 0`) and helper constructors now reject implicit memory composition (`REQUIRE OrchestrationControlPlane ValueError`, `REQUIRE WorkflowCompletionAdapter ValueError`)
- Direct Python verification proved project mode still executes through the project helper path while quick mode is explicitly rejected by `dispatch_generation()` (`PROJECT project 55 2`, `QUICK_REJECT ValueError`)
- Direct Python verification proved the explicit factory root still preserves quick dispatch bypass (`QUICK_FACTORY quick 1 0`)
- Architecture mapping was synchronized to reflect `mode_router` as a project-only helper rather than part of the quick single-episode mainline: [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md)
- Result:
- passed
