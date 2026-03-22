# Validation Checklist: PLAN-20260321-012
- Plan ID: PLAN-20260321-012
- Scope: current delivery stage verification only
- Status: active
- Updated At: 2026-03-21T15:53:30Z

## 1. Usage Rule
- This file owns the concrete delivery verification for [PLAN-20260321-012](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260321-012.md).
- The plan owns stage goals, checkpoints, and adherence principles.
- This checklist owns test targets, command recipes, manual validation records, and evidence anchors.

## 2. Phase A Validation
- Required artifacts:
- 职责拆分表已落文，能逐段解释 `task_queue.py` 当前逻辑的归属，不留“先放这里”的灰区。
- runtime-first read-model 优先级表已落文，明确 `runtime/session -> gate -> current_node -> nodes -> Task -> telemetry` 的展示优先级。
- “继续查看当前任务 / gate decision -> resume execution / 历史 broker 重消费”三种语义已显式拆开。
- Acceptance rule:
- 若任何拟改逻辑无法明确归到 queue adapter、execution host/bootstrap、runtime/control-plane、frontend read model 之一，则 Checkpoint A 不通过。

## 3. Phase B Validation
- Backend focused checks:
- `task_queue.py` 只保留 adapter 级职责：入队、revoke/cancel、消费入口、execution eligibility 接线、最薄转发。
- worker consume 路径仍支持 terminal short-circuit、revoke/cancel、生效中的 execution eligibility policy。
- runtime/control-plane 抽离后，失败/暂停/恢复状态仍能正确写入 runtime session。
- Backend concrete test targets:
- [backend/tests/unit/test_task_queue.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_task_queue.py)
  - 终态 quick runtime 不再被历史消费链重新执行
  - `queue_task()` 仍能持久化 `celery_task_id` 并执行入队门控
  - runtime payload 与 dispatch host 路径在抽离后仍保持 contract 正确
- [backend/tests/unit/test_tasks_endpoint.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_tasks_endpoint.py)
  - `get_current_quick_run()` 继续返回 workspace unfinished run + runtime view
  - `create_task()` 仍执行 replace-old-run 语义
  - `get_task_status()` 与 `get_task_runtime()` 继续共用 runtime projection
- [backend/tests/unit/test_runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_runtime_session_service.py)
  - runtime/control-plane 主写路径在抽离后仍成立
- [backend/tests/unit/test_start_dev_uv.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_start_dev_uv.py)
  - dev harness 的 worker/beat 启动策略不回退
- [backend/tests/unit/test_working_memory_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_working_memory_service.py)
  - gate/resume 相关 shared WM 边界不回退
- Suggested commands:
- `uv run pytest -q backend/tests/unit/test_task_queue.py`
- `uv run pytest -q backend/tests/unit/test_tasks_endpoint.py`
- `uv run pytest -q backend/tests/unit/test_runtime_session_service.py`
- `uv run pytest -q backend/tests/unit/test_start_dev_uv.py`
- `uv run pytest -q backend/tests/unit/test_working_memory_service.py`
- Evidence to capture:
- 记录通过/失败结果、失败归因、如有需要的补充 targeted test。

## 4. Phase C Validation
- Frontend focused checks:
- step-0 failure 场景下，workspace 首屏主状态应反映 runtime failure，而不是被 `nodes queued` 误导。
- websocket/polling 合流后，current run 真值优先级保持一致。
- `awaiting_human`、approve/revise/replan、resume 后的状态切换都以 runtime/read model 为主。
- Frontend concrete test targets:
- [__tests__/integration/runtime-gate-sync.test.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/__tests__/integration/runtime-gate-sync.test.tsx)
  - script gate 视图继续由 runtime 驱动
  - approve/revise/replan 后写回的仍是 resumed runtime view，而不是 queue 信号
- 若后续修改了 polling/WS 合流逻辑，应补充或扩展针对 [useTaskPolling.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useTaskPolling.ts) 与 [useWebSocket.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useWebSocket.ts) 的 focused integration coverage
- Suggested commands:
- `npm test -- --runInBand __tests__/integration/runtime-gate-sync.test.tsx`
- Evidence to capture:
- step-0 failure、awaiting_human、resume 三类 UI 截图或状态记录。

## 5. Phase D Validation
- Manual quick HITL regression:
- 使用本地开发启动路径重跑 quick HITL 链路，补记新的 `task_id` 与 `workflow_session_id`。
- 验证 `script gate -> approve -> resume -> image/video`。
- 若媒体阶段失败，明确区分 provider config / execution contract 与 queue/runtime 边界回归。
- Final acceptance rule:
- 只有在未重新引入 runtime semantics into queue layer 的前提下，且 quick HITL 主线可解释地通过或可解释地失败，Checkpoint D 才算通过。

## 6. Checkpoint Evidence Log
- A checkpoint:
- 待填充
- B checkpoint:
- 待填充
- C checkpoint:
- 待填充
- D checkpoint:
- 待填充
