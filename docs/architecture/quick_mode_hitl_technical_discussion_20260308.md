# Quick Mode HITL 技术讨论纪要

日期：2026-03-08

状态：技术讨论结论纪要

用途：作为后续技术规划与实施设计输入，不替代实施计划。

说明：

- 本文档是技术讨论纪要，不承担正式架构术语定义
- 顶层层级术语以 [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md) 为准

## 1. 讨论目标

本轮讨论不再重开产品边界，目标是回答：

- 基于当前仓库已经实现的架构和技术栈，`quick mode` 从 one-shot 重构为带 `HITL gate` 的单 `episode` 工作台，需要做哪些技术改造。
- 如何保证 `HITL` 与既有 `MAS / ReAct` 逻辑解耦。
- 哪些现有实现应复用，哪些必须扩展，哪些做法绝对不能采用。

## 2. 已锁定的产品输入

以下前提已由产品侧拍板，本轮技术讨论以此为边界：

- 本次修复目标就是打破 `quick mode` 的一键到底。
- `script` 之后需要门控，动作是：`approve / revise / replan`。
- `storyboard` 之后需要门控，动作是：`approve / revise`。
- `scene video` 之后需要门控，动作是：`approve / revise`。
- 本阶段 `final compose` 暂不增加门控。
- 局部修改的最小单位是 `scene`。
- `replan` 只允许出现在 `script gate`。
- 本阶段先完成 `quick mode` 的交互重构。
- 技术优先级排序：
  - 第一：满足人机交互需求，并保证后续可迁移，避免 `HITL` 与 `MAS` 耦合
  - 第二：增强可控性，但不改原有 `MAS / ReAct` 的总体决策逻辑
  - 第三：简单易用

## 3. 当前实现基础

本次讨论基于如下现状展开：

- `quick mode` 当前仍是典型页面向导：`input -> processing -> review -> export`，没有节点工作台，也没有中途 gate。`src/pages/HomePage.tsx`
- `quick mode` 的全局状态仍是请求级粗粒度：`currentRequest`、`results`、`currentStep`、少量 agent 进度计数，不足以表达 node / gate / attempt / revision。`src/store/useAppStore.ts`
- `project mode` 已有“列表 + 详情工作区”的工作台雏形，且已经支持脚本编辑、确认和单集生成入口，可作为交互结构参考，但当前仍停在 `episode` 级。`src/components/project/ProjectModeView.tsx` `src/store/useProjectStore.ts`
- `quick mode` 当前绑定的是 `/tasks` 接口，创建任务后直接启动后台线程或队列执行，没有暂停、恢复、审核决策控制能力。`backend/app/api/v1/endpoints/tasks.py`
- `project mode` 当前通过 `story_plan` 管理项目/分集规划，但状态仍是 `episode` 级，且仓储仍是内存实现，不足以承载持久化 gate。`backend/app/core/story_plan.py`
- `WorkflowState` 与 `SceneData` 已经具备 `scene` 级脚本、图像、视频、连续性字段，是本次扩展最值得复用的运行时基础。`backend/app/core/workflow_state.py`
- `script_writer` 已把 scene 级脚本与旁白信息组织成结构化产物写入 MAS 工作记忆，这天然对应 `script gate` 之前的候选产物边界。`backend/app/agents/script_writer.py`
- `image_generator` 与 `video_generator` 已经通过共享记忆与 artifact helper 按 scene 写入图像/视频产物，这天然对应 `storyboard gate` 和 `scene video gate`。`backend/app/agents/image_generator.py` `backend/app/agents/video_generator.py`
- 当前 WebSocket 事件仍以“进度更新 + 阶段就绪 + workflow 完成/失败”为主，没有 gate pending / decision / resume 语义。`src/hooks/useWebSocket.ts` `backend/app/api/v1/endpoints/websocket.py` `backend/app/services/websocket.py`

## 4. 技术角色讨论

## 4.1 架构负责人

结论：

- 必须保留现有 `MAS / ReAct` 内核，不把 `HITL` 写进 agent prompt、agent 状态或 tool 语义。
- `HITL` 必须建模为 control plane 能力，而不是 agent behavior。
- `quick mode` 与未来 `project mode` 必须复用同一个单 `episode` 工作流内核。

建议：

- 增加一层“单 episode control plane”，由它管理：
  - 当前运行到哪个 work node
  - 当前是否在 gate 上暂停
  - 哪个 gate 正在等待决策
  - 哪个 revision/attempt 是最新候选
- agent 恢复执行时，只接收“已批准产物 + 用户 revision 约束”，不接收“你正在 HITL 模式中”这种流程语义。

反对：

- 在 orchestrator prompt 中加入“这一步先等用户确认”。
- 前端直接拼装 agent 控制语义。
- 把 gate 逻辑做成 scattered `if/else`，分散在 `tasks.py`、`orchestrator.py`、React 页面里各自判断。

## 4.2 后端 / 工作流负责人

结论：

- 现有 `tasks` 模型、`Scene` / `Resource` 表、`WorkflowState` / `SceneData` 可以复用，但不能直接承载完整 gate 语义。
- 当前 `/tasks` 是请求级接口，不是 control plane；当前 `Task.status` 也不是 node/gate 状态机。
- 后端必须新增可持久化的 node / review / revision 层，而不是继续把所有状态塞进 `Task.status` 或 `Task.output_metadata`。

建议：

- 保留 `Task` 作为 quick mode 的外层请求对象和权限 / 列表入口。
- 在内部新增共享的单 `episode` runtime 实体，供 `quick mode` 和未来 `project mode` 共用。
- 最少需要新增这几类概念：
  - `workflow_session`
  - `workflow_node`
  - `node_attempt`
  - `review_decision`
  - `artifact_snapshot`
- `script gate` 是 episode 级 gate。
- `storyboard gate` 与 `scene video gate` 是 scene 级 gate。

推荐的状态方向：

- session 级：
  - `queued`
  - `running`
  - `pending_review`
  - `resuming`
  - `completed`
  - `failed`
- node 级：
  - `queued`
  - `running`
  - `pending_review`
  - `approved`
  - `revision_requested`
  - `completed`
  - `failed`
- decision 级：
  - `approve`
  - `revise`
  - `replan`

额外判断：

- `Task` / `Scene` / `Resource` 可以继续做面向交付的业务表。
- `attempt / review / lineage` 不建议直接复用 `Scene` / `Resource` 主表硬扛，否则历史版本、审核结论和失效传播会很难表达。

## 4.3 前端负责人

结论：

- `quick mode` 不应该继续是“表单 + 进度页 + 最终成片”的页面向导。
- 应该演进为单 `episode` 工作台，但 UI 仍然是任务工作区，不是 DAG 编辑器。
- `project mode` 当前的“双栏工作台”结构可以借鉴，但需要把粒度从 `episode` 下探到 `scene`。

建议的 quick mode 目标交互：

- 入口仍保留现有表单页。
- 提交后不再进入纯 `processing` 页面，而是进入单 `episode` 工作台。
- 工作台结构建议为：
  - 顶部：全局进度与当前 gate
  - 左侧：scene 列表与状态
  - 中间：当前候选产物预览
  - 右侧：允许动作、revision 输入、影响范围与成本提示
- `script gate`：
  - 展示整集脚本编辑区
  - 展示 scene outline
  - 操作：`approve / revise / replan`
- `storyboard gate`：
  - 逐 scene 预览 storyboard / keyframe
  - 操作：`approve / revise`
- `scene video gate`：
  - 逐 scene 预览场景视频
  - 操作：`approve / revise`

建议复用：

- `ProjectModeView` 的“列表 + 详情 + 动作条”交互骨架。
- `AgentOrchestrator`、`RealTimeProgress` 作为折叠式诊断面板，而不是主工作区。
- `VideoPlayer` 等既有媒体预览组件。

建议重构：

- `HomePage.tsx` 的粗粒度 step 页面切换。
- `useAppStore` 中 quick mode 的状态模型。
- `useWebSocket` 对事件的处理语义，只支持完成态和粗粒度 ready 事件远远不够。

反对：

- 用多个弹窗串起所有 gate。
- 用聊天式消息流承载 scene review。
- 在一个全局 store 里混放 quick workflow、project workflow 和临时 UI 杂项。
- 暴露 agent/tool 节点图给用户。

## 4.4 算法 / 连续性工程师

结论：

- 本阶段把“局部修改最小单位”定在 `scene` 是可行的，但必须补 continuity contract。
- 用户 revise 只能改固定意图下的 node 产物，不能直接改写 `MAS` 的总体决策。
- `script gate` 之前允许 `replan`，其余 gate 只允许局部 revise，这是一个合理边界。

建议：

- continuity state 至少要从已批准产物中抽出：
  - 角色出场
  - 外观 / 服装 / 道具
  - 场景与时间
  - 镜头语言
  - 旁白语义
  - 音乐 / 情绪
- `storyboard revise(scene_n)`：
  - 至少失效 `scene_n` 的视频尝试
  - 若运行时已标明显式连续性依赖，例如 `depends_on_scene` 或 `requires_continuity_from`，需要把下游 scene 标成 `stale` 或 `continuity_risk`
- `scene video revise(scene_n)`：
  - 只重建该 scene 的视频 attempt
  - 不自动回滚整集计划
- `script revise`：
  - 仍在 `script gate` 内，不进入 `replan`
  - 只要用户没有选择 `replan`，就保持既有 overall plan，不重跑概念规划逻辑
- `script replan`：
  - 明确回到 planner/script 阶段
  - 失效所有 downstream storyboard/video candidate

反对：

- 让任意 revise 默认影响全局。
- 没有 continuity closure 计算时仍承诺“只改这一处”。
- 把用户 revise 文本直接当成 agent 全局新目标。

## 4.5 运行时 / 基础设施观点

结论：

- 当前 `tasks.py` 中直接后台线程执行，只适合 demo，不适合可暂停、可恢复、可审核的 HITL 工作流。
- 现阶段不必先引入更重的编排系统；基于现有技术栈，优先补“数据库持久化 + 队列驱动 + control plane service”更现实。

建议：

- 先把 quick mode gate runtime 建成可持久化的 DB-backed control plane。
- worker 继续使用现有队列 / 异步执行体系，但必须从“整条一口气跑完”改为“运行到 gate 即停、收到决策再续跑”。
- 暂不推荐为了这次改造直接引入 `Temporal`；否则会把本阶段目标从交互重构拉成基础设施迁移。

## 5. 技术团队联合结论

## 5.1 必须保留的部分

- 保留现有 `MAS / ReAct` agent 设计和单 agent 自主循环，不在 agent 内硬编码 HITL。
- 保留 `WorkflowState` / `SceneData` 作为 scene 级运行时事实源。
- 保留 `script_writer`、`image_generator`、`video_generator` 的 scene artifact 边界。
- 保留 `Task` 作为 quick mode 外层请求对象。
- 保留 `project mode` 作为未来复用单 `episode` 内核的外层编排层，而不是另起一套实现。

## 5.2 必须新增或扩展的部分

### A. 单 episode control plane

需要把 quick mode 从“请求对象 + 一次执行”升级为“请求对象 + 可暂停的 workflow session”。

最关键的是新增：

- gate-aware session 状态
- node 状态
- node attempt / revision lineage
- review decision 记录
- resume / rerun / replan 入口

### B. 持久化 review runtime

当前的 `Task.status` 只能表示任务是否完成，不能表达：

- 当前在哪个 gate 停住
- scene 7 的 storyboard 第 2 次尝试是否被驳回
- 哪个 video attempt 是最新候选
- 哪个 decision 触发了重跑

因此必须引入新的持久化结构，不能只靠内存或 `output_metadata` 拼装。

### C. 新的 API 契约

quick mode 至少需要新增一组面向工作台的接口。

推荐方向：

- `GET /tasks/{task_id}/workspace`
- `POST /tasks/{task_id}/gates/script/decision`
- `POST /tasks/{task_id}/scenes/{scene_number}/storyboard/decision`
- `POST /tasks/{task_id}/scenes/{scene_number}/video/decision`
- `POST /tasks/{task_id}/resume`

说明：

- 外部 URL 可以先挂在 `/tasks` 下，兼容 quick mode 入口。
- 但内部不应把 `/tasks` 直接当唯一 domain model；这些 API 最好只是 control plane façade。

### D. 新的事件模型

当前 `useWebSocket` 主要识别：

- `concept_plan_ready`
- `image_assets_ready`
- `video_assets_ready`
- `workflow_completed`

这对 gate workflow 不够。

建议统一走 `event.state` / `event.progress`，补充 payload state：

- `script_review_pending`
- `storyboard_review_pending`
- `scene_video_review_pending`
- `review_decision_applied`
- `workflow_resumed`
- `scene_attempt_started`
- `scene_attempt_completed`
- `scene_marked_stale`

不建议继续扩散成大量前端专用消息类型。

### E. quick mode 前端状态模型

当前 `useAppStore` 只能支撑：

- 当前请求
- 当前页面 step
- agent 进度
- 最终结果

需要新增 quick workflow store，至少表达：

- `workspace`
- `current_gate`
- `active_scene`
- `script_candidate`
- `scene_storyboards`
- `scene_videos`
- `node_status_map`
- `pending_decision`
- `revision_draft`
- `stale_downstream`

前端判断应围绕 gate/node/session，而不是围绕 `currentStep === processing/review`。

## 5.3 推荐的整体技术走向

技术团队在方案层面收敛到这一点：

- 对外：
  - `quick mode` 继续以 `Task` 作为入口
  - UI 变成单 `episode` 工作台
- 对内：
  - 引入共享的单 `episode` control plane
  - `Task` 只是 façade
  - `project mode` 未来复用同一 control plane，只是在外层多一层 `project -> episode`

换句话说，推荐做法不是：

- 继续把 quick mode 永久留在 `/tasks + one-shot`
- 再给 project mode 单独做一套 gate runtime

而是：

- quick mode 先接入共享内核
- project mode 后续复用

## 6. 本轮明确不建议的做法

- 不要把 `HITL` 逻辑写进 `script_writer`、`image_generator`、`video_generator` prompt。
- 不要把 gate 语义塞进 `Task.status` 单字段里。
- 不要把 revision lineage 只保存在前端本地状态。
- 不要让 quick mode 继续只靠“任务完成后进 review”。
- 不要把 quick mode 和 project mode 分别实现两套工作流核心。
- 不要把 scene revise 承诺成“任意局部修改都不影响后续”。
- 不要为了本阶段改造把项目直接带入重量级 runtime 迁移。

## 7. 进入技术规划前仍需明确的实现问题

这些问题不影响当前讨论结论，但需要在正式技术设计里写实：

1. 单 `episode` control plane 的持久化表结构如何建模。
2. `Task` 与 `workflow_session` 是一对一还是一对多。
3. `artifact_snapshot` 采用独立表还是对象存储索引表。
4. `scene revise` 的失效传播是否只做显式依赖传播，还是先做 conservative stale 标记。
5. quick mode 前端是新增 `useQuickWorkflowStore`，还是在现有 store 上分层扩展。
6. dev / prod 两种运行模式下，resume 语义如何保证幂等。

## 8. 可直接作为规划前提的结论

- `HITL` 与 `MAS` 必须解耦，`review gate` 放在 control plane。
- 本次 quick mode 改造不是“加几个确认按钮”，而是“升级为带 gate 的单 episode 工作台”。
- 现有最值得复用的技术基础是：
  - `WorkflowState` / `SceneData`
  - scene 级 script/image/video artifact 边界
  - `project mode` 的工作台交互骨架
- 现有最需要替换或扩展的技术部分是：
  - one-shot task runtime
  - 粗粒度前端 step 状态
  - 缺失的 node/review/revision 持久化模型
  - 缺失的 gate API 和事件语义
