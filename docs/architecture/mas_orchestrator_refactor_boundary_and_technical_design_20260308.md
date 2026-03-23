# MAS Orchestrator 重构边界与技术设计草案

日期：2026-03-08

状态：技术设计草案

用途：作为后续专项审查、架构重构和实施拆解的正式输入。

说明：

- 本设计稿服从 [AGENTS.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/AGENTS.md) 中的原则约束
- 如后续实现或讨论纪要与本设计稿冲突，应以仓库原则和更新后的正式设计为准
- 第 3 节用于描述设计起点基线，其中部分问题已在后续阶段逐步修复，不应直接等同于当前实现状态
- 本文档属于四层架构下的二级细化设计，不承担顶层层级术语定义；顶层术语以 [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md) 为准

关联文档：

- [MAS Orchestrator 边界专题讨论纪要](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_boundary_discussion_minutes_20260308.md)
- [HITL Gate 与 MAS 解耦讨论纪要](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/hitl_gate_discussion_minutes_20260308.md)
- [Quick Mode HITL 技术讨论纪要](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/quick_mode_hitl_technical_discussion_20260308.md)
- [MAS Architecture Alignment Note](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_alignment_note_20260323.md)

## 1. 设计目标

本次重构的目标不是“把 `orchestrator.py` 拆小”，而是恢复正确分层：

- `orchestrator` 回到 `planner + runtime consumer`
- `control-plane` 独立为一等运行时层
- `gate/evaluator` 独立为事实检查与放行判断层
- `leaf-agent` 回到“只执行 execution contract 的 ReAct agent”

同时满足以下约束：

- 允许当前阶段保留有限的预定义骨架
- 预定义约束尽量迁入 `policy + gate`
- 不再把 gate、fallback、runtime probing 堆进 orchestrator
- 不再让 leaf agent 读取 control-plane 内部协议
- 为 quick mode `HITL` 和 project mode 复用同一单 `episode` runtime kernel 铺路

## 2. 非目标

本阶段不追求：

- 立刻把中心化编排改成完全自由 DAG
- 立刻把所有规则都交给模型
- 立刻引入全新重型编排基础设施
- 一次性重写所有 agent

本阶段只解决边界错误，不做无边界的“全面重构”。

## 3. 设计起点问题归纳（部分问题已在后续阶段修复）

### 3.1 Orchestrator 过载

当前 [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) 同时承担：

- 规则编排
- route/signal 组装
- runtime probing
- delivery check
- fallback/replan
- 部分运行时控制

典型问题区：

- `_build_workflow_plan()`：写死 `active_pool / standby_pool / actions`
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1331)
- `_decide_replan_action()`：写死特定 fallback/replan
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1579)
- `_build_audio_route_payload()`、`_build_audio_signal_payload()`
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1848)
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1907)
- `_collect_runtime_video_audio_facts()`、`_probe_video_audio_stream()`
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1941)
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L2030)
- `_should_run_agent()`：按具体 agent 类型写业务开关
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L2061)

### 3.2 Leaf Agent 边界失效（设计起点基线）

设计起点时 [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py) 曾读取 control-plane 协议并二次改写 tool calls：

- 读取 `workflow.plan / workflow.audio_route`
  - [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L324)
- 解析上游 action
  - [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L357)
- patch tool calls
  - [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L378)
  - [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L423)

这违反了 “leaf agent 只执行 contract” 的目标边界。该问题后续已在 `P1-2` 修复，但保留在本节作为设计起点反例。

### 3.3 Control-Plane 实际缺位

当前只有 `Task` 和 shared memory facts，没有真正的 runtime control-plane：

- [tasks.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/tasks.py#L97)
- [task_queue.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py#L56)

这导致：

- quick mode 只能 whole-task one-shot
- project mode 难以复用单 `episode` runtime kernel
- `HITL pause/resume/revise/replan` 缺少宿主

## 4. 目标分层

### 4.1 Layer A: Skeleton Orchestrator

职责：

- 维护有限阶段骨架
- 消费 capability catalog
- 结合上下文、预算、gate 结果生成下一步 `ExecutionIntent`
- 调用 leaf agents
- 消费 `AgentResult` 和 `GateResult`

禁止：

- 直接探测交付物
- 直接做 `ffprobe`
- 直接做 gate 事实判断
- 直接写死 agent-specific 业务开关
- 直接修改 runtime 状态机

### 4.2 Layer B: Control-Plane Runtime

职责：

- 管理 `workflow_session / node / attempt / gate / decision`
- 管理 `pause / resume / retry / revise / replan / abort`
- 管理 lineage、budget、幂等和事件
- 把 `ExecutionIntent` 落成 `ExecutionContract`

禁止：

- 直接参与媒体内容生成
- 直接承担业务特定启发式判断
- 直接调用 provider SDK 或工具

### 4.3 Layer C: Policy + Gate/Evaluator

`Policy` 职责：

- 决定哪些 gate 生效
- 决定哪些动作允许自动通过
- 决定 retry/replan/halt 的策略

`Gate/Evaluator` 职责：

- 输入前置条件检查
- 交付物验证
- 质量检查
- 输出结构化 `GateResult`

禁止：

- 直接修改执行队列
- 直接激活 standby agent
- 直接拼装 leaf agent 输入

### 4.4 Layer D: Context Assembler / Contract Assembler

职责：

- 把 shared memory / workflow state 的业务事实组装为 agent 可消费上下文
- 把 control-plane 约束组装为显式 `ExecutionContract`

禁止：

- 继续透传 `workflow.plan / audio_route / activation_pool`
- 把 control-plane 内部命令暴露给 leaf agent

### 4.5 Layer E: Leaf Agents

职责：

- Observe -> Plan -> Act -> Reflect
- 消费业务事实和 `ExecutionContract`
- 通过工具执行
- 输出产物和结构化执行结果

禁止：

- 读取 `workflow.plan / audio_route / activation_pool / standby_pool`
- 解析 orchestrator action graph
- 在 ACT 前 patch tool calls
- 自己承担 gate/fallback/control-plane 判断

## 5. 边界对象设计

### 5.1 ExecutionIntent

由 `orchestrator` 产出，交给 `control-plane`。

最小字段：

- `intent_id`
- `session_id`
- `node_key`
- `target_agent`
- `operation`
- `scope`
- `goal`
- `constraints`
- `expected_artifacts`
- `retry_policy_ref`

用途：

- 表达“下一步打算做什么”
- 不直接暴露给 leaf agent

### 5.2 ExecutionContract

由 `control-plane + assembler` 产出，交给 leaf agent。

最小字段：

- `contract_version`
- `contract_id`
- `agent`
- `operation`
- `scope`
- `inputs`
- `constraints`
- `expected_outputs`
- `storage`

约束：

- 允许包含显式执行约束，如 `generate_audio: false`
- 不允许包含 control-plane 内部协议，如：
  - `workflow.plan`
  - `activation_pool`
  - `route_source`
  - `decision_reason`
  - `run_other_agent`

### 5.3 GateResult

由 `gate/evaluator` 产出，交给 `control-plane` 和 `orchestrator` 消费。

最小字段：

- `contract_version`
- `session_id`
- `node_id`
- `attempt_id`
- `gate_name`
- `gate_type`
- `scope`
- `artifact_refs`
- `facts`
- `result`
- `reason_code`
- `diagnostics`
- `allowed_actions`
- `recommended_action`

结果类型：

- `pass`
- `fail`
- `inconclusive`
- `awaiting_human`

## 6. Runtime / Control-Plane 实体

### 6.1 workflow_session

作用：单个 `episode` 的 runtime 根对象。

最小字段：

- `id`
- `task_id`
- `mode`
- `project_id`
- `episode_id`
- `shared_memory_id`
- `status`
- `current_node_key`
- `current_attempt_id`
- `input_payload`
- `gate_policy`
- `summary_output`
- `error_message`
- `started_at`
- `completed_at`

### 6.2 workflow_node_state

作用：session 内的可执行节点状态。

最小字段：

- `id`
- `session_id`
- `node_key`
- `node_type`
- `scope_type`
- `scope_ref`
- `status`
- `revision_index`
- `gate_required`
- `last_gate_id`
- `artifact_refs`
- `diagnostics`
- `updated_at`

### 6.3 workflow_node_attempt

作用：节点的单次执行实例。

最小字段：

- `id`
- `session_id`
- `node_id`
- `attempt_no`
- `trigger_reason`
- `requested_by`
- `input_contract`
- `output_artifacts`
- `metrics`
- `status`
- `error_code`
- `error_message`
- `started_at`
- `ended_at`

### 6.4 workflow_gate

作用：节点执行后的 gate/evaluator 结果。

最小字段：

- `id`
- `session_id`
- `node_id`
- `attempt_id`
- `gate_name`
- `gate_type`
- `status`
- `contract_version`
- `artifact_refs`
- `facts`
- `result_code`
- `reason_code`
- `allowed_actions`
- `recommended_action`
- `created_at`
- `resolved_at`

### 6.5 workflow_gate_decision

作用：human/system 对 gate 的正式决策。

最小字段：

- `id`
- `gate_id`
- `session_id`
- `node_id`
- `action`
- `actor_type`
- `actor_id`
- `feedback_text`
- `structured_constraints`
- `invalidation_scope`
- `created_at`

## 7. Kernel 设计

统一引入 `single-episode runtime kernel`。

固定骨架：

- `script`
- `storyboard:scene:n`
- `scene_video:scene:n`
- `compose`
- `quality`

说明：

- quick mode：一个 `Task` 对应一个 `workflow_session`
- project mode：外层 episode 调度创建多个 `workflow_session`
- project mode 不再自带另一套 episode runtime 逻辑

## 8. Quick / Project 复用关系

### Quick Mode

- 外层仍保留 `Task`
- 内部通过 `workflow_session` 运行单 `episode` kernel
- 用户直接对当前 session/gate 做交互

### Project Mode

- 外层保留 project/episode 调度
- 每个 episode 共享同一个 kernel
- `EpisodeOrchestrator` 只负责：
  - 选 episode
  - 创建 session
  - 聚合摘要

不再负责持有另一套执行逻辑。

## 9. API / 命令面

最小内部命令：

- `start_session`
- `run_until_wait_or_complete`
- `submit_gate_decision`
- `retry_node`
- `cancel_session`
- `get_session_view`

最小 API：

- `POST /tasks`
- `GET /tasks/{task_id}/runtime`
- `POST /tasks/{task_id}/nodes/{node_key}/decision`
- `POST /tasks/{task_id}/nodes/{node_key}/retry`
- `POST /tasks/{task_id}/cancel`

project mode 保留外层 orchestration API，但内部都翻译成对 episode session 的操作。

## 10. Agent 边界设计

### 10.1 video_generator

必须去编排化。

应移除：

- `_resolve_audio_route_hint()`
- `_extract_generate_audio_from_plan()`
- `_inject_orchestration_hints_into_video_calls()`

迁移目标：

- 只读取 scene 事实、连续性上下文、显式 `ExecutionContract`
- 不再知道 `workflow.plan` 是什么
- 不再在 ACT 阶段 patch tool calls

### 10.2 video_composer

当前 `mix_type` 不应继续由 agent 内部推断。  
后续应由 `ExecutionContract.constraints.compose_mode` 显式给出。

反例：

- [video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py#L68)

### 10.3 voice_synthesizer

当前问题不属于 control-plane 泄漏主问题。  
但 `_try_fill_scene_number_for_voice_call()` 这类 normalization 更适合长期上移到共享 adapter。

### 10.4 quality_checker

应作为 evaluator 族保留，但检查对象应来自显式 contract。  
agent 内部不应自己决定“切换到 image fallback”。

## 11. 架构禁区

以下模式从现在开始应视为架构禁区：

1. 在 orchestrator 内新增 agent-specific 编排分支
2. 在 orchestrator 内新增 runtime probing / delivery check / gate 逻辑
3. 在 leaf agent 内读取 `workflow.plan / audio_route / activation_pool`
4. 在 leaf agent 内 patch LLM 产出的 tool calls
5. 继续把 control flags 当成 leaf agent 的隐式 API
6. 用兼容性事实伪造掩盖真实交付边界
7. 在没有 control-plane 的前提下先做 quick mode `HITL`

## 12. 分阶段迁移路线

### Phase 0: 冻结旧模式

- 冻结 orchestrator 内新的 agent-specific 分支
- 冻结 agent 新增对 `workflow.plan/audio_route` 的读取
- 冻结新的 orchestrator 内 gate/probing 逻辑

退出条件：

- 新代码不再扩散错误边界

### Phase 1: 抽离 Evaluator

- 先把 runtime probing 和 delivery check 从 orchestrator 移出
- orchestrator 改为消费 `GateResult`

退出条件：

- orchestrator 不再直接 `ffprobe`

### Phase 2: 去掉 Agent 侧 control-plane 泄漏

- 先整改 `video_generator`
- 以 `ExecutionContract` 替代 `workflow.plan/audio_route`

退出条件：

- `video_generator` 不再读取 legacy orchestration keys

### Phase 3: 插入 Runtime Kernel

- 在 `tasks/task_queue` 与 orchestrator 之间插入 `single-episode runtime kernel`
- 先打通 `script gate`

退出条件：

- 出现真实的 `waiting_gate -> decision -> resume`

### Phase 4: 接入 Quick / Project 共用内核

- quick mode 接入 kernel
- project mode 的 episode 也接入同一 kernel

退出条件：

- quick/project 不再是两套 episode runtime

### Phase 5: 清理 Legacy 协议

- 删除 `workflow.plan/audio_route` 的 live 依赖
- 删除 orchestrator 内 legacy route/fallback 逻辑

退出条件：

- live runtime 不再依赖旧协议

## 13. 实施前置原则

在进入编码前，以下原则应作为硬约束：

1. `orchestrator` 不直接做交付检查
2. `gate` 只产出事实与判断，不做调度
3. `control-plane` 是唯一持有 `pause/resume/retry/replan/budget/lineage` 的层
4. `leaf agent` 的唯一控制面入口是 `ExecutionContract`
5. quick mode `HITL` 必须建立在 runtime kernel 之上，而不是 UI 补丁

## 14. 当前建议的第一刀

第一刀不要先改所有 agent。  
优先顺序应是：

1. 落 runtime 表和 `EpisodeRuntimeKernel`
2. 改 `tasks.py` 和 `task_queue.py` 接入 kernel
3. 先实现 `script gate`
4. 再清理 `orchestrator` 中的 probing/gate 逻辑
5. 再整改 `video_generator`

原因：

- 如果先改 leaf agents，但没有新的 control-plane 宿主，最终还是会回退到旧 orchestrator 里塞逻辑。
- 先把 runtime kernel 插进去，后续 `HITL`、scene revise、project 复用才有统一宿主。
