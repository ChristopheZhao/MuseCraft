# MAS Runtime / Control-Plane 细化设计稿

日期：2026-03-08

状态：Phase 0-2 设计细化稿

用途：作为 `PLAN-20260308-003` 的 P0-2 交付物，细化 `single-episode runtime kernel` 的数据模型、状态机、命令面和与现有代码的边界映射。

关联文档：

- [MAS 编排边界解耦与单 Episode Runtime Kernel 重构计划](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260308-003.md)
- [MAS Orchestrator 重构专项审查清单](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_refactor_audit_checklist_20260308.md)
- [MAS Orchestrator 重构边界与技术设计草案](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_refactor_boundary_and_technical_design_20260308.md)
- [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md)
- [MAS Architecture Alignment Note](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_alignment_note_20260323.md)

说明：

- 本文档细化四层架构中的“控制层 / runtime substrate”边界，不承担顶层层级术语定义

## 1. 设计目标

本设计稿回答 4 个问题：

1. `single-episode runtime kernel` 的最小数据模型是什么
2. `workflow_session / node / attempt / gate / decision` 的状态机怎么设计
3. quick mode 和 project mode 如何共享同一个 runtime kernel
4. 如何从当前 `Task + task_queue + orchestrator + WorkflowState` 平滑迁移

## 2. 当前边界映射

现有对象的正确定位如下：

### 2.1 Task

[task.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/models/task.py#L33)

当前定位：

- 外层请求对象
- 列表页/权限/交付摘要宿主
- 粗粒度进度状态

不再承担：

- node/attempt/gate 的运行时 SoT
- `pause/resume/revise/replan` 细粒度状态

### 2.2 WorkflowState / SceneData

[workflow_state.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/core/workflow_state.py#L32)  
[workflow_state.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/core/workflow_state.py#L122)

当前定位：

- `episode` 领域事实层
- scene 级脚本、图像、视频、连续性数据的 SoT
- artifact 读写和 agent 上下文聚合的来源

不再承担：

- 运行时控制状态
- gate 决策状态
- retry/replan/pause/resume 生命周期

### 2.3 EpisodeRuntimeState

[story_plan.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/core/story_plan.py#L600)

当前定位：

- project mode 的 episode 级摘要投影

后续建议：

- 继续保留为 summary projection
- 追加来自 `workflow_session` 的投影字段
- 不再持有独立 episode runtime 逻辑

## 3. Runtime 核心对象

## 3.1 workflow_session

作用：

- 单个 `episode` 的 runtime 根对象
- quick mode 的单任务内核运行单元
- project mode 下每个 episode 的共享执行单元

建议字段：

- `id`
- `task_id`
- `mode`: `quick | project_episode`
- `project_id`
- `episode_id`
- `shared_memory_id`
- `status`: `queued | running | waiting_gate | resuming | completed | failed | cancelled`
- `current_node_key`
- `current_attempt_id`
- `input_payload`
- `gate_policy`
- `summary_output`
- `error_message`
- `started_at`
- `completed_at`

设计说明：

- `shared_memory_id` 允许复用当前 agent 仍依赖的 `workflow_state_id`
- `task_id` 与 `workflow_session` 保持 `1:N` 可能性，但 quick mode 默认 `1:1`
- `input_payload` 只保留用户输入和入口级参数，不复制全部 scene/agent 中间态

## 3.2 workflow_node_state

作用：

- 表示 session 内固定骨架上的一个可执行节点
- 承载节点级状态和最新 gate 绑定

建议字段：

- `id`
- `session_id`
- `node_key`
- `node_type`: `script | storyboard | scene_video | compose | quality`
- `scope_type`: `episode | scene`
- `scope_ref`
- `status`: `queued | running | pending_gate | approved | needs_revision | completed | failed | skipped | stale`
- `revision_index`
- `gate_required`
- `last_gate_id`
- `artifact_refs`
- `diagnostics`
- `updated_at`

设计说明：

- v1 不需要单独 `edge` 表，节点顺序由 kernel 固定展开
- scene 节点建议使用稳定 `node_key`，例如：
  - `storyboard:scene:3`
  - `scene_video:scene:3`
- `stale` 用于 scene revise 后标记下游需重算或存在 continuity 风险的节点

## 3.3 workflow_node_attempt

作用：

- 记录节点单次执行
- 为 retry/revise/replan 建立 lineage

建议字段：

- `id`
- `session_id`
- `node_id`
- `attempt_no`
- `trigger_reason`: `initial | revise | replan | retry | resume`
- `requested_by`: `system | human | policy`
- `input_contract`
- `output_artifacts`
- `metrics`
- `status`: `running | succeeded | failed | aborted`
- `error_code`
- `error_message`
- `started_at`
- `ended_at`

设计说明：

- 任何 revise/retry 不覆盖旧 attempt，只新增 attempt
- `input_contract` 是运行时真实执行证据，后续审计和复盘直接看这里

## 3.4 workflow_gate

作用：

- 记录节点执行后的 gate/evaluator 结果
- 统一承载 system gate 和 human review gate

建议字段：

- `id`
- `session_id`
- `node_id`
- `attempt_id`
- `gate_name`: `script_review | storyboard_review | scene_video_review | delivery_check | quality_check`
- `gate_type`: `human_review | system_evaluator`
- `status`: `pending | passed | failed | awaiting_human | decided`
- `contract_version`
- `artifact_refs`
- `facts`
- `result_code`
- `reason_code`
- `allowed_actions`
- `recommended_action`
- `created_at`
- `resolved_at`

设计说明：

- `artifact_refs` 不复制大文件内容，只引用产物
- `facts` 统一放规范化事实，不放面向 UI 的拼装字符串

## 3.5 workflow_gate_decision

作用：

- 记录 human/system 对 gate 的正式决策

建议字段：

- `id`
- `gate_id`
- `session_id`
- `node_id`
- `action`: `approve | revise | replan | retry | abort`
- `actor_type`: `human | system | policy`
- `actor_id`
- `feedback_text`
- `structured_constraints`
- `invalidation_scope`: `node | downstream | session`
- `created_at`

设计说明：

- `structured_constraints` 是后续 contract assembler 的重要输入
- `replan` 仅在 `script_review` gate 合法

## 4. Runtime 状态机

## 4.1 Session 级状态机

状态：

- `queued`
- `running`
- `waiting_gate`
- `resuming`
- `completed`
- `failed`
- `cancelled`

建议迁移：

- `queued -> running`
- `running -> waiting_gate`
- `waiting_gate -> resuming`
- `resuming -> running`
- `running -> completed`
- `running -> failed`
- `waiting_gate -> cancelled`
- `running -> cancelled`

语义：

- `waiting_gate` 表示至少有一个当前 blocking gate 未决
- `resuming` 是消费决策后的过渡态，用于幂等恢复

## 4.2 Node 级状态机

状态：

- `queued`
- `running`
- `pending_gate`
- `approved`
- `needs_revision`
- `completed`
- `failed`
- `skipped`
- `stale`

建议迁移：

- `queued -> running`
- `running -> pending_gate`
- `pending_gate -> approved`
- `pending_gate -> needs_revision`
- `approved -> completed`
- `needs_revision -> queued`
- `completed -> stale`
- `running -> failed`

语义：

- `pending_gate` 仅表示等待 gate
- `approved` 表示 gate 已放行，但下游未必执行完
- `stale` 表示上游 revise/replan 导致当前节点结果不再可信

## 4.3 Attempt 级状态机

状态：

- `running`
- `succeeded`
- `failed`
- `aborted`

说明：

- attempt 不做复杂状态机，只记录一次实际运行结果
- 如被人工 revise 或上游 replan 废弃，可通过 node/state lineage 表达，不需要 attempt 回滚

## 4.4 Gate 级状态机

状态：

- `pending`
- `passed`
- `failed`
- `awaiting_human`
- `decided`

语义：

- `pending`：system evaluator 已创建但还未完成
- `awaiting_human`：已产出候选，等待人工动作
- `decided`：human/system 已提交正式决策

## 5. Kernel 节点骨架

本项目 v1 的 `single-episode runtime kernel` 使用固定骨架：

- `script`
- `storyboard:scene:n`
- `scene_video:scene:n`
- `compose`
- `quality`

设计理由：

- 当前视频流水线本来存在强依赖
- 先保证边界正确，再逐步释放阶段内编排权
- 不在本期强上自由 DAG

## 6. Gate Policy

本期固定 gate policy：

### 6.1 script gate

- `gate_name`: `script_review`
- `scope_type`: `episode`
- `allowed_actions`: `approve | revise | replan`

### 6.2 storyboard gate

- `gate_name`: `storyboard_review`
- `scope_type`: `scene`
- `allowed_actions`: `approve | revise`

### 6.3 scene video gate

- `gate_name`: `scene_video_review`
- `scope_type`: `scene`
- `allowed_actions`: `approve | revise`

## 7. Decision 与失效传播

### 7.1 approve

- 当前 gate 通过
- 当前 node 标记为 `approved`
- kernel 继续推进下一个 node

### 7.2 revise

- 为当前 node 创建新的 `workflow_node_attempt`
- 当前 node 进入 `needs_revision -> queued`
- 根据 node 类型决定失效范围：
  - `script` revise：保持 overall plan，不触发 replan
  - `storyboard:scene:n` revise：至少让 `scene_video:scene:n` 变 `stale`
  - `scene_video:scene:n` revise：只重建当前 scene video attempt

### 7.3 replan

- 仅 `script_review` gate 合法
- session 内下游节点全部标记为 `stale`
- `script` node 新建 attempt
- session 进入 `resuming`

## 8. API / 命令面映射

## 8.1 内部命令

- `start_session(task_id, mode, project_id?, episode_id?)`
- `run_until_wait_or_complete(session_id)`
- `submit_gate_decision(session_id, node_key, action, feedback, constraints)`
- `retry_node(session_id, node_key)`
- `cancel_session(session_id)`
- `get_session_view(session_id)`

## 8.2 外部 API

### Quick mode

- `POST /tasks`
  - 创建 `Task`
  - 同时创建 `workflow_session`
- `GET /tasks/{task_id}/runtime`
  - 返回 session summary、node list、active gate、allowed actions
- `POST /tasks/{task_id}/nodes/{node_key}/decision`
  - body: `action`, `feedback_text`, `structured_constraints`
- `POST /tasks/{task_id}/nodes/{node_key}/retry`
- `POST /tasks/{task_id}/cancel`

### Project mode

- 继续保留 project API 作为产品入口
- 但内部统一转到 episode session：
  - `POST /projects/{project_id}/orchestrate`
  - `PUT /projects/{project_id}/episodes/{episode_id}/script`

## 9. 与现有代码的迁移映射

## 9.1 tasks.py

[tasks.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/tasks.py#L98)

现状问题：

- `create_task()` 直接后台线程执行 orchestrator
- `get_task_status()` 临时 new orchestrator 拼 workflow 状态
- `retry/cancel` 只有 whole-task 语义

目标：

- `create_task()` 只创建 task + session，并交给 kernel runner
- `get_task_status()` 改查 runtime summary
- `retry/cancel` 改消费 session/node 级命令

## 9.2 task_queue.py

[task_queue.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py#L56)

现状问题：

- `sync_process_video_task()` 直接把 orchestrator 当 runtime owner
- runtime 生命周期被 `task_queue` 和 orchestrator 双写

目标：

- `sync_process_video_task()` 改成：
  - 加载 session
  - 调用 `EpisodeRuntimeKernel.run_until_wait_or_complete(session_id)`

## 9.3 workflow_state.py

[workflow_state.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/core/workflow_state.py#L122)

现状优点：

- `SceneData` 已覆盖 scene 级脚本、图像、视频、连续性字段

目标：

- 保持其作为领域事实层
- 不再让其持有运行时控制状态

## 9.4 story_plan.py / project mode

[story_plan.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/core/story_plan.py#L600)

现状问题：

- `EpisodeRuntimeState` 过粗
- `ProjectStateRepository` 仍为内存实现

目标：

- `EpisodeRuntimeState` 退为 projection
- project mode 由外层 episode 调度 + 内部共享 session kernel 实现

## 10. WebSocket / 事件模型

建议新增事件：

- `runtime_session_started`
- `runtime_node_running`
- `runtime_gate_pending`
- `runtime_gate_decided`
- `runtime_node_stale`
- `runtime_session_resuming`
- `runtime_session_completed`
- `runtime_session_failed`

事件载荷至少包含：

- `task_id`
- `session_id`
- `node_key`
- `gate_name`
- `status`
- `allowed_actions`
- `artifact_refs`

## 11. P0-2 完成标准

P0-2 视为完成，需要同时满足：

- runtime 核心对象和字段已明确
- session/node/attempt/gate 状态机已明确
- quick/project 共用 `single-episode runtime kernel` 的关系已明确
- 与 `Task / WorkflowState / EpisodeRuntimeState` 的边界映射已明确
- 下一步可直接进入 kernel 实现，而不会再次回到 orchestrator 里补状态字段
