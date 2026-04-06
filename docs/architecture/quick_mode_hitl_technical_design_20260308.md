# Quick Mode HITL 技术方案草案

日期：2026-03-08

状态：技术方案草案

用途：定义 `quick mode` 从 one-shot 工作流升级为带 `HITL gate` 的单 `episode` 工作台所需的技术改造，作为后续实施与拆解依据。

说明：

- 本文档属于 quick mode 场景下的二级方案设计；顶层层级术语仍以 [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md) 为准
- 术语对齐说明见 [mas_architecture_alignment_note_20260323.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_alignment_note_20260323.md)

## 1. 背景

当前 `quick mode` 仍是典型 one-shot 交互：

- 前端页面流仍是 `input -> processing -> review -> export`，中途没有节点级确认与局部重跑。`src/pages/HomePage.tsx`
- 后端 `/tasks` 接口创建任务后直接启动整条工作流，不支持暂停、恢复、审批决策。`backend/app/api/v1/endpoints/tasks.py`
- orchestrator 当前只发粗粒度状态事件，如 `image_assets_ready`、`video_assets_ready`、`workflow_completed`。`backend/app/agents/orchestrator.py`

与此同时，仓库已经具备本次扩展最关键的复用基础：

- `WorkflowState` / `SceneData` 已有 scene 级脚本、图像、视频、连续性字段。`backend/app/core/workflow_state.py`
- `script_writer` 已经把 scene 级脚本事实写入 `project.scene_scripts`。`backend/app/agents/script_writer.py`
- `image_generator` / `video_generator` 已按 scene 写入产物。`backend/app/agents/image_generator.py` `backend/app/agents/video_generator.py`
- `project mode` 已有“列表 + 详情 + 动作条”的工作台骨架，可复用交互结构。`src/components/project/ProjectModeView.tsx`

因此，本次方案不推翻现有 `MAS / ReAct` 内核，而是在其外部增加一层可持久化的 gate-aware control plane。

## 2. 已确认的产品边界

以下结论已锁定，方案不再讨论：

- 本次目标是打破 `quick mode` 一键到底。
- gate 顺序为：
  - `script gate`: `approve / revise / replan`
  - `storyboard gate`: `approve / revise`
  - `scene video gate`: `approve / revise`
- `final compose` 本阶段不增加 gate。
- 局部修改最小单位是 `scene`。
- `replan` 只允许出现在 `script gate`。
- 本阶段只先完成 `quick mode` 重构。
- 第一优先级是 `HITL` 与 `MAS` 解耦，并保证后续可迁移。

## 3. 设计原则

### 3.1 MAS 与 HITL 解耦

- `MAS` 继续负责规划、生成、连续性维护与 ReAct 决策。
- `HITL` 只负责 gate 决策，不进入 agent prompt、agent state、tool schema。
- 用户反馈先结构化为 decision contract，再由 control plane 转成下次执行输入。

一句话定义：

- `MAS` 产出候选
- `Gate` 决定是否放行
- `Policy` 决定何时需要人

### 3.2 Quick / Project 共用内核

- `quick mode = 单 episode workflow kernel`
- `project mode = 多 episode 外层编排`

本阶段虽然只改 quick，但数据模型、API 语义、事件语义都必须按单 `episode` 共享内核设计，不能做 quick 专属实现。

### 3.3 Scene 是最小 revise 单位

- `storyboard revise` 只作用于当前 scene，并失效该 scene 的下游视频候选。
- `scene video revise` 只作用于当前 scene 的视频 attempt。
- 任何触及全局叙事、角色设定、时空、镜头顺序、时长节奏的修改，必须在 `script gate` 使用 `replan`。

### 3.4 Control Plane 是一等能力

暂停、审批、恢复、重跑、失效传播、revision lineage 都属于 control plane，不能分散在：

- React 页面本地逻辑
- agent prompt 分支
- `Task.status` 单字段

## 4. 目标架构

## 4.1 总体结构

对外：

- 仍由 `Task` 作为 quick mode 的创建入口和列表入口
- 前端由“步骤页”改为“单 episode 工作台”

对内：

- 新增单 `episode` control plane
- orchestrator 不再默认一次跑到底，而是“运行到下一个 gate 或结束”
- gate 决策通过 control plane 驱动恢复执行

目标分层：

1. `UI Workspace Layer`
   - 展示脚本 / storyboard / scene video
   - 收集 `approve / revise / replan`

2. `Control Plane Layer`
   - session/node/attempt/review 状态机
   - gate 决策
   - resume / rerun / invalidation

3. `MAS Runtime Layer`
   - orchestrator
   - script_writer
   - image_generator
   - video_generator
   - composer / QC

4. `Artifact + Memory Layer`
   - `WorkflowState`
   - shared working memory
   - artifact snapshots
   - continuity snapshot

## 4.2 工作流节点定义

本阶段 quick mode 的标准主链路：

1. `script_generation`
2. `script_review_gate`
3. `storyboard_generation`
4. `storyboard_review_gate`
5. `scene_video_generation`
6. `scene_video_review_gate`
7. `final_compose`

说明：

- `script_generation` 作用域为 `episode`
- `storyboard_generation` 与 `scene_video_generation` 作用域为 `scene`
- 即便 `final_compose` 本期无 gate，也保留为显式 work node，便于未来扩展

## 5. 数据模型

## 5.1 保留现有模型

继续保留：

- `Task`
- `Scene`
- `Resource`
- `WorkflowState`
- `SceneData`

原因：

- `Task` 仍适合做外层请求对象、任务列表与权限边界
- `WorkflowState` / `SceneData` 已经是 scene 级事实源
- `Scene` / `Resource` 可继续承担交付产物索引

## 5.2 新增运行时模型

建议新增以下持久化实体：

### A. `workflow_session`

表示单个 quick mode `episode` 工作流实例。

关键字段建议：

- `id`
- `task_id`
- `mode`
- `workflow_state_id`
- `status`: `queued | running | pending_review | resuming | completed | failed | cancelled`
- `current_node_key`
- `active_gate_key`
- `active_revision_id`
- `created_at`
- `updated_at`

说明：

- 本阶段建议 `Task : WorkflowSession = 1 : 1`
- 后续如需支持 task 内多次 rerun，可演进为 `1 : N`

### B. `workflow_node_state`

表示 session 内每个 work node / gate node 的执行状态。

关键字段建议：

- `id`
- `workflow_session_id`
- `node_key`
- `node_type`: `work | gate`
- `stage`: `script | storyboard | scene_video | compose`
- `scope_type`: `episode | scene`
- `scope_id`
- `status`: `queued | running | pending_review | approved | revision_requested | replanning | completed | failed | stale`
- `latest_attempt_id`
- `latest_approved_snapshot_id`
- `created_at`
- `updated_at`

说明：

- `scope_id` 对 episode 级节点可为空
- 对 scene 级节点建议写 `scene_number`

### C. `workflow_node_attempt`

表示某个 node 的一次执行尝试。

关键字段建议：

- `id`
- `workflow_node_state_id`
- `attempt_no`
- `trigger`: `initial_run | revise | replan_resume | retry`
- `input_snapshot`
- `continuity_snapshot_ref`
- `status`: `running | succeeded | failed | superseded`
- `error`
- `cost`
- `tokens`
- `started_at`
- `finished_at`

### D. `workflow_review_decision`

表示某次 gate 上的人工决策。

关键字段建议：

- `id`
- `workflow_session_id`
- `workflow_node_state_id`
- `action`: `approve | revise | replan`
- `scope_type`
- `scope_id`
- `notes`
- `constraint_patch`
- `created_by`
- `created_at`

### E. `artifact_snapshot`

表示节点输出的候选或已批准产物快照。

关键字段建议：

- `id`
- `workflow_session_id`
- `workflow_node_state_id`
- `artifact_type`: `script | storyboard | scene_video`
- `scope_type`: `episode | scene`
- `scope_id`
- `revision_no`
- `attempt_id`
- `is_candidate`
- `is_approved`
- `supersedes_snapshot_id`
- `payload_ref`
- `summary`
- `created_at`

说明：

- `payload_ref` 可指向对象存储、资源表、或独立 JSON 存储
- 不建议把完整大 JSON 长期塞进 `Task.output_metadata`

## 5.3 Artifact Contract

### Script Artifact

以 `episode` 为主视角，同时保留 scene 级脚本事实：

- `scene_number`
- `script_text`
- `voice_over_text`
- `narrative_description`
- `motion_beats`
- `characters_present`
- `character_descriptions`
- `pacing_and_timing`

这些字段当前多数已经存在于 `project.scene_scripts` 或 `SceneData` 中，可直接复用。`backend/app/agents/script_writer.py` `backend/app/core/workflow_state.py`

### Storyboard Artifact

以 `scene` 为单位：

- `image_prompt`
- `image_url` / `image_path`
- `visual_description`
- `camera_angle`
- `lighting_style`
- `art_style`
- `props_and_objects`
- `color_palette`
- `scene_design_elements`

### Scene Video Artifact

以 `scene` 为单位：

- `video_prompt`
- `video_url` / `video_path`
- `video_generation_mode`
- `initial_state_description`
- `action_sequence_description`
- `target_outcome_description`
- `timing_structure_description`
- `complete_video_description`

## 5.4 Continuity Snapshot

建议新增独立 continuity snapshot 视图，不直接等同于任一 agent 内部状态。

最小集合：

- 角色外观 / 服装 / 道具摘要
- 场景 / 时空摘要
- 叙事意图摘要
- 镜头语言摘要
- 音乐 / 情绪摘要
- `depends_on_scene`
- `requires_continuity_from`
- 上游已批准 artifact 的版本引用

用途：

- `image_generator` 只消费“已批准 script artifact + continuity snapshot”
- `video_generator` 只消费“已批准 storyboard artifact + continuity snapshot”

## 6. 状态机

## 6.1 Session 状态机

推荐状态：

- `queued`
- `running`
- `pending_review`
- `resuming`
- `completed`
- `failed`
- `cancelled`

关键迁移：

- `queued -> running`
- `running -> pending_review`
- `pending_review -> resuming`
- `resuming -> running`
- `running -> completed`
- `running -> failed`

## 6.2 Node 状态机

推荐状态：

- `queued`
- `running`
- `pending_review`
- `approved`
- `revision_requested`
- `replanning`
- `completed`
- `failed`
- `stale`

关键迁移示例：

### Script Gate

- `script_generation.running -> completed`
- `script_review_gate.queued -> pending_review`
- `pending_review + approve -> approved -> storyboard_generation.queued`
- `pending_review + revise -> revision_requested -> script_generation.queued`
- `pending_review + replan -> replanning -> script_generation.queued`

### Storyboard Gate

- `storyboard_generation(scene_n).running -> completed`
- `storyboard_review_gate(scene_n).queued -> pending_review`
- `pending_review + approve -> approved -> scene_video_generation(scene_n).queued`
- `pending_review + revise -> revision_requested -> storyboard_generation(scene_n).queued`

### Scene Video Gate

- `scene_video_generation(scene_n).running -> completed`
- `scene_video_review_gate(scene_n).queued -> pending_review`
- `pending_review + approve -> approved`
- `pending_review + revise -> revision_requested -> scene_video_generation(scene_n).queued`

## 6.3 失效传播规则

### Script Revise

- 保持既有 overall plan，不触发概念层重规划
- 失效全部 downstream storyboard candidate
- 失效全部 downstream scene video candidate

### Script Replan

- 回到 planner/script 阶段
- 失效所有 downstream storyboard/video candidate
- 可以重建 scene 结构与节奏约束

### Storyboard Revise(scene_n)

- 失效 `scene_n` 的 storyboard candidate
- 失效 `scene_n` 的所有 scene video candidate
- 若存在显式 continuity 依赖，下游 scene 标记 `stale` 或 `continuity_risk`

### Scene Video Revise(scene_n)

- 仅失效 `scene_n` 的 scene video candidate
- 不自动回滚 script/storyboard

## 7. API 设计

## 7.1 保留的现有入口

保留：

- `POST /tasks`
- `GET /tasks/{task_id}`

但语义调整为：

- `POST /tasks` 创建 quick mode task + workflow session
- 后台 worker 只运行到下一个 gate 或完成，而不是保证整链跑完

## 7.2 新增 Workspace / Gate API

建议第一阶段挂在 `/tasks` 下，作为 façade：

### `GET /tasks/{task_id}/workspace`

返回 quick mode 工作台状态。

最小返回结构建议：

- `task`
- `session`
- `current_gate`
- `script_candidate`
- `scene_list`
- `scene_storyboards`
- `scene_videos`
- `node_status_map`
- `pending_decision`

### `POST /tasks/{task_id}/gates/script/decision`

请求体：

- `action`: `approve | revise | replan`
- `notes`
- `constraint_patch`

### `POST /tasks/{task_id}/scenes/{scene_number}/storyboard/decision`

请求体：

- `action`: `approve | revise`
- `notes`
- `constraint_patch`

### `POST /tasks/{task_id}/scenes/{scene_number}/video/decision`

请求体：

- `action`: `approve | revise`
- `notes`
- `constraint_patch`

### `POST /tasks/{task_id}/resume`

场景：

- gate 决策已写入
- control plane 将 session 从 `pending_review` 推进到 `resuming`

### `POST /tasks/{task_id}/cancel`

用途：

- 显式终止当前 workflow session

## 7.3 决策 Contract

所有 gate 输入统一结构化，不直接接收“自由文本即全局语义”：

- `action`
- `scope_type`
- `scope_id`
- `notes`
- `constraint_patch`

其中 `constraint_patch` 建议以结构化字段为主，例如：

- `camera_adjustment`
- `mood_adjustment`
- `character_pose_adjustment`
- `background_adjustment`
- `timing_adjustment`
- `narration_adjustment`

## 8. 事件与 WebSocket 设计

## 8.1 设计原则

- 继续统一走 `event.state` / `event.progress`
- 不扩散前端专用消息类型
- payload 中表达 gate/node/session 语义

## 8.2 新增状态事件

建议新增：

- `script_review_pending`
- `storyboard_review_pending`
- `scene_video_review_pending`
- `review_decision_applied`
- `workflow_resumed`
- `scene_attempt_started`
- `scene_attempt_completed`
- `scene_marked_stale`

## 8.3 事件载荷建议

示例：

```json
{
  "state": "storyboard_review_pending",
  "task_id": "task_xxx",
  "workflow_session_id": "wf_xxx",
  "node_key": "storyboard_review_gate",
  "scope_type": "scene",
  "scope_id": 3,
  "candidate_snapshot_id": "snap_xxx",
  "pending_actions": ["approve", "revise"]
}
```

说明：

- 事件层负责同步工作台状态
- 前端不从事件里推断业务规则，只做展示和本地刷新

## 9. Orchestrator / Control Plane 扩展

## 9.1 不修改的部分

不改变：

- `script_writer` / `image_generator` / `video_generator` 的 ReAct 主循环
- agent 的工具选择逻辑
- agent 的 supplier/tool 抽象边界

## 9.2 需要新增的控制逻辑

建议新增 `QuickWorkflowControlPlaneService`，职责如下：

- 创建 `workflow_session`
- 初始化 node 图
- 启动下一节点执行
- 在 gate 节点前后写入 node/attempt/snapshot 状态
- 接受 review decision
- 计算失效传播
- 决定 resume / rerun / replan

## 9.3 Orchestrator 的协作方式

推荐改造方向：

- orchestrator 接收明确的 execution scope
- 每次执行只负责跑到下一个 gate 或结束
- 在产物完成后，将候选写入 snapshot，并由 control plane 决定是否暂停

即：

- orchestrator 负责生成
- control plane 负责停、放、重跑

## 9.4 与 Shared Memory 的关系

shared memory 继续作为 agent 运行时事实源，但新增约束：

- 需要区分 `latest_draft` 与 `approved_revision`
- 下游 agent 不得默认消费未批准上游草稿
- gate 决策应落 DB，再由 control plane 组装成下一次 agent 输入

## 10. 前端工作台设计

## 10.1 页面结构

推荐 quick mode 提交后进入单 `episode` 工作台，替换当前纯 `processing` 页面。

结构建议：

- 顶部：全局进度、当前 gate、成本摘要
- 左侧：scene 列表与状态
- 中间：当前候选产物预览
- 右侧：decision panel + revise 输入 + 影响范围

## 10.2 各阶段呈现

### Script Gate

- 展示整集脚本
- 展示 scene outline
- 动作：`approve / revise / replan`

### Storyboard Gate

- 展示当前 scene storyboard / keyframe
- 动作：`approve / revise`

### Scene Video Gate

- 展示当前 scene 视频
- 动作：`approve / revise`

## 10.3 状态管理

建议新增独立 `useQuickWorkflowStore`，不要继续把 quick workflow 全塞进 `useAppStore`。

最小状态建议：

- `workspace`
- `session`
- `current_gate`
- `active_scene`
- `script_candidate`
- `scene_storyboards`
- `scene_videos`
- `node_status_map`
- `pending_decision`
- `revision_draft`
- `stale_downstream`

`useAppStore` 保留：

- mode
- notifications
- 全局 UI 杂项
- WebSocket 连接态

## 10.4 可复用组件

建议复用：

- `ProjectModeView` 的双栏工作区思路
- `VideoPlayer`
- `AgentOrchestrator`
- `RealTimeProgress`

建议重构：

- `HomePage.tsx` 的粗粒度 step 驱动
- `useWebSocket.ts` 对 gate 事件的处理
- quick mode 的本地 step 状态模型

## 11. 迁移策略

## 11.1 第一阶段

先完成基础运行时与 script gate：

- 新增 `workflow_session` / `workflow_node_state` / `workflow_node_attempt` / `workflow_review_decision`
- `POST /tasks` 改为创建 session
- 补 `GET /tasks/{task_id}/workspace`
- 补 `script gate` 决策与 resume
- quick mode 页面切换到工作台壳

## 11.2 第二阶段

接入 storyboard gate：

- scene 级 storyboard snapshot
- scene 级 decision API
- `storyboard_review_pending` 事件
- scene stale 标记

## 11.3 第三阶段

接入 scene video gate：

- scene video snapshot
- scene video decision API
- scene 级 revise 重跑

## 11.4 第四阶段

让 project mode 复用单 `episode` 内核：

- `project -> episode workflow session`
- Project UI 外层只负责 episode 选择与汇总，不重写内部 gate 逻辑

## 12. 明确不做的事情

- 不在 agent prompt 中编码“先等用户确认”
- 不把 gate 语义塞进 `Task.status`
- 不在前端实现失效传播规则
- 不承诺任意 revise 都严格只影响一个点
- 不在本阶段把系统迁到重量级 workflow runtime

## 13. 测试与观测建议

至少补以下验证：

- control plane 单元测试
  - gate 状态迁移
  - review decision 应用
  - stale 传播
- API 测试
  - workspace 查询
  - script/storyboard/video decision
  - resume 幂等
- 前端状态测试
  - gate pending 时工作台渲染
  - decision 后状态刷新
- 事件测试
  - `event.state` 新增 gate 事件
  - 前端事件消费正确更新 store

建议新增运行时诊断：

- 当前 gate
- 当前 node
- active attempt
- last decision
- stale scenes
- resume source

## 14. 方案结论

本次改造的正确落点不是“修 quick mode 页面交互”，也不是“让 agent 生成后等用户回复”，而是：

- 保留现有 `MAS / ReAct` 单 agent 内核
- 复用现有 scene 级 artifact 与 `WorkflowState`
- 新增单 `episode` control plane
- 用持久化 node / attempt / review / snapshot 支撑 gate
- 让 quick mode 先成为共享内核的第一个落地点
- 未来 project mode 直接复用该内核

如果后续实施按这个边界推进，`HITL` 可以在未来平滑从“强人工确认”迁移到“轻门控 / 抽检 / 默认自动通过”，而不需要重写 `MAS` 主逻辑。
