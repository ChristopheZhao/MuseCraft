# MAS Orchestrator 重构专项审查清单

日期：2026-03-08

状态：Phase 0 审查清单

用途：作为 `PLAN-20260308-003` 的 Phase 0 审查输入，用于冻结错误边界、识别高风险文件、约束后续重构实现。

关联文档：

- [MAS 编排边界解耦与单 Episode Runtime Kernel 重构计划](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260308-003.md)
- [MAS Orchestrator 边界专题讨论纪要](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_boundary_discussion_minutes_20260308.md)
- [MAS Orchestrator 重构边界与技术设计草案](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_refactor_boundary_and_technical_design_20260308.md)

## 1. 审查目标

本清单不评估“代码风格”，只审以下问题：

- 是否把 `planner / control-plane / gate-evaluator / leaf-agent` 职责混写
- 是否继续扩散错误边界
- 是否存在阻断 quick mode `HITL` 与 project mode 复用的结构性问题
- 是否存在会阻断从偏预定义 MAS 迁向更自主 MAS 的耦合点

## 2. 风险分级

### P0

- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py)
- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py)
- [tasks.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/tasks.py)
- [task_queue.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py)

### P1

- [video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py)
- [quality_checker.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/quality_checker.py)
- [episode_orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/episode_orchestrator.py)
- [story_plan.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/core/story_plan.py)
- [workflow_state.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/core/workflow_state.py)

### P2

- 其余 live agents 横扫确认无同类问题

## 3. 禁止继续扩散的模式

从本清单生效起，以下模式视为架构禁区：

1. 在 orchestrator 内新增 agent-specific 编排分支
2. 在 orchestrator 内新增 runtime probing、delivery check、gate 逻辑
3. 在 leaf-agent 内读取 `workflow.plan / workflow.audio_route / activation_pool / standby_pool`
4. 在 leaf-agent 内解析上游 plan 再恢复自己的执行参数
5. 在 ACT 阶段 patch LLM 产出的 `tool_calls`
6. 用 loose flags 或 ad hoc request 字段在 agent 内自行做模式路由
7. 没有独立 control-plane 的前提下直接做 quick mode `HITL`

## 3.1 反伪去规则化审核

本专题增加一轮显式架构审核，专门识别“表面去规则化、实则强规则内聚”的方案。

以下情况应判定为“不通过”：

1. 只是把全局变量切换成 orchestrator 内部变量、局部常量或 helper 返回值，但决策语义仍由代码分支主导
2. 只是把 `if/else` 从配置读取层搬到 `_build_*plan()`、`_decide_*()`、`_should_run_*()` 等内部方法里
3. 表面删除了外部开关，但 orchestrator 仍显式维护 `active_pool / standby_pool / trigger_after / route / fallback target`
4. leaf-agent 不再读原字段名，但继续通过另一组内部字段、`input_data` flag 或 shared memory key 获取同一控制语义
5. gate 没有独立出来，只是把 gate 判断包装成 orchestrator 内部 helper

本轮架构审核的核心问题只有一个：

`职责边界是否真的发生了迁移，而不是控制变量换了存放位置。`

审核通过至少要满足：

1. 原本属于 gate/evaluator 的事实检查已真正移出 orchestrator
2. 原本属于 control-plane 的 runtime 状态和命令已真正有独立宿主
3. 原本属于 leaf-agent 的执行约束已通过显式 contract 暴露，而不是继续靠隐式协议读取
4. 新增一个 agent/gate/provider 时，不要求继续修改 orchestrator 的特化分支
5. 评审者能够指出“这条控制语义现在归哪一层拥有”，而不是只能说“它已经不在全局变量里了”

## 4. 角色边界审查

### 4.1 Orchestrator

检查点：

- 是否只保留有限骨架、capability catalog 消费、planner 输出消费、gate 结果消费
- 是否仍直接做 `ffprobe`、音轨检查、文件存在性检查
- 是否仍直接维护 `active_pool / standby_pool / trigger_after / route`
- 是否仍按具体 agent 类型写业务 if/else

当前反例：

- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1331)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1579)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1848)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1941)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L2061)

### 4.2 Control-Plane

检查点：

- 是否存在独立 `workflow_session / node / attempt / gate / decision`
- runtime 状态是否来自一等 store，而不是临时 new orchestrator 拼出来
- `pause / resume / revise / retry / replan / cancel` 是否有明确宿主
- quick/project 是否能共用单 `episode` runtime kernel

当前反例：

- [tasks.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/tasks.py#L343)
- [task_queue.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py#L124)
- [task_queue.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py#L145)

### 4.3 Gate / Evaluator

检查点：

- 交付检查是否已独立输出结构化 `GateResult`
- gate 是否只产出事实、原因和建议，而不直接改执行队列
- system gate 与 human gate 是否统一 contract
- `quality_checker` 是否仍只是 terminal-only，而非可复用 evaluator

当前反例：

- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1941)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L2030)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1655)
- [quality_checker.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/quality_checker.py#L161)

### 4.4 Leaf Agent

检查点：

- 是否只消费业务事实和显式 `ExecutionContract`
- 是否读取了 control-plane 内部协议
- 是否在 ACT 前 patch `tool_calls`
- 是否把 fallback/gate/reroute 决策写进 agent

当前反例：

- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L324)
- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L357)
- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L378)
- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L423)
- [video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py#L68)

## 5. 协议与 Contract 审查

检查点：

- 是否还存在未经 adapter 的共享内存隐式协议
- `workflow.plan/audio_route` 是否仍被普通 agent 读取
- 是否已经区分 `ExecutionIntent / ExecutionContract / GateResult`
- 是否存在继续把 control-plane flags 暴露给 agent 的实现

当前重点：

- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L324)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L2252)
- [memory_views.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py#L165)

## 6. Fallback / Replan 审查

检查点：

- fallback 是否基于通用 contract gap，而不是 case-specific 补丁
- replan 是否仍按具体 agent 类型写死
- standby 激活是否仍耦合于特定业务路径

当前反例：

- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1579)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1626)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1651)

## 7. Quick / Project 复用审查

检查点：

- quick mode 是否建立在 `single-episode runtime kernel` 上
- project mode 是否只是 episode session 的外层调度
- 是否还存在第二套 episode runtime state machine

当前重点：

- [tasks.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/tasks.py#L97)
- [episode_orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/episode_orchestrator.py#L479)
- [story_plan.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/core/story_plan.py#L600)

## 8. 测试与回归审查

检查点：

- 是否能围绕 contract、gate result、runtime state 做分层测试
- 是否还必须依赖整链场景快照证明行为
- 是否存在“修一个分支就要补一堆场景快照”的回归特征

本专题建议补充的回归方向：

- runtime 状态机
- gate contract
- `video_generator` 去编排化
- quick mode `script gate`
- project mode 复用单 `episode` kernel

## 9. Phase 0 退出条件

Phase 0 视为完成，需要同时满足：

- 已形成禁区清单并冻结错误边界
- 已形成 P0/P1/P2 文件分级
- 已形成《runtime/control-plane 设计细化稿》
- 已完成一轮“反伪去规则化”架构审核并通过
- 团队确认下一阶段先切 `runtime kernel`，不再回到 orchestrator 继续堆逻辑

## 10. 使用方式

后续每次进入相关代码前，先用本清单做一次自检：

1. 改动落在哪一层
2. 是否跨层泄漏
3. 是否引入新的隐式协议
4. 是否扩散了禁区模式
5. 是否符合 Phase 0 之后的目标边界
