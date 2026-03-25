# Single-Episode Harness Architecture 草案

日期：2026-03-11

状态：架构基线说明（2026-03-25 术语刷新）

用途：把 `single-episode` 的 agent harness architecture 提升为正式架构基线，明确全局约束、分层边界、组件归属与后续收口原则。

说明：

- 本文档服从 [AGENTS.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/AGENTS.md) 中的原则约束。
- 本文档聚焦 `single-episode` 架构，不展开 `project` 外层产品流程细节。
- 如后续实现与本文档冲突，应优先修正实现或更新正式架构，不得以当前代码现状反推架构合理性。
- 本文档同时承担顶层层级术语的 canonical vocabulary 角色；后续子设计文档只能细化，不得重定义 `编排层 / 控制层 / 门控层 / 治理层`。

关联文档：

- [MAS Orchestrator 重构边界与技术设计草案](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_refactor_boundary_and_technical_design_20260308.md)
- [MAS Runtime / Control-Plane 细化设计稿](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_control_plane_detailed_design_20260308.md)
- [Quick Mode HITL 技术设计稿](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/quick_mode_hitl_technical_design_20260308.md)
- [MAS Architecture Alignment Note](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_alignment_note_20260323.md)

## 1. 问题定义

前序设计和重构已经明确了正确方向：

- `orchestrator` 需要从 rule-centric 拉回 `llm-decision-centric`
- 控制、门控、治理需要从编排中解耦
- `quick` 与 `project` 应共享同一个 `single-episode` 内核

但当前暴露出一个更高优先级的问题：

- `single-episode` 缺少全局架构约束
- 系统中出现了两条可推进 `episode` 生命周期的 live path
- 局部重构虽然成立，但整体 single-episode engine 尚未统一

本文档的目的不是重新讨论局部实现，而是补齐 single-episode 级别的正式架构约束。

## 2. 目标与非目标

### 2.1 目标

本文档要回答 4 个问题：

1. `single-episode` 的正式架构基线是什么
2. 编排层、控制层、门控层、治理层分别负责什么
3. `runtime substrate` 在四层架构中的准确位置是什么
4. 当前实现中的双宿主问题应如何判定和收口

### 2.2 非目标

本文档不试图：

- 完成 `project` 外层产品流程的全面重构
- 规定具体模型供应商或工具实现
- 直接给出完整迁移代码方案
- 为当前错误实现保留兼容性正名

## 3. 核心术语

### 3.1 Quick Mode

`quick mode` 是单个 `episode` 的产品入口与工作台模式。

### 3.2 Project Mode

`project mode` 是多个 `episode` 的外层业务组织模式。它负责 episode 选择、共享设定注入、批量调度与结果汇总，不是另一套 `episode` 内部引擎。

### 3.3 Episode

`episode` 是 MAS、control-plane、gate、runtime session 真正发生作用的业务边界。

### 3.4 Agent Harness

`agent harness` 指围绕 agent 编排、runtime state、gate、contract、audit、quality gates 构成的整套运行框架，而不只是单个 orchestrator 的执行逻辑。

### 3.5 Single-Episode Mainline

`single-episode mainline` 指单个 `episode` 的唯一 MAS 主线。  
在本架构中，这条主线固定为编排层的 `OrchestratorAgent`，不允许再存在第二条并列的单集主线。

### 3.6 Runtime Substrate

`runtime substrate` 指控制层使用的运行时底座，包括：

- `workflow_session`
- `workflow_node_state`
- `workflow_node_attempt`
- `workflow_gate`
- `workflow_gate_decision`

它不是第五层架构，而是控制层的状态机与持久化底座，也是 single-episode 主线的配套基础设施。

### 3.7 External Scheduler

`external scheduler` 指任务队列、worker、API 调度入口等外部调度层。  
它只负责启动 single-episode engine，不参与单 `episode` 内部的编排、控制、门控、治理分层。

### 3.8 Project Wrapper

`project wrapper` 指围绕多个 `episode` 组织出来的外层产品包装，包括：

- episode 选择
- 共享设定注入
- 批量调度
- project 级进度汇总

它不是 `single-episode harness` 四层本体的一部分。
它只能复用单集引擎，不得自带另一套 per-episode runtime / control-plane / gate semantics。

### 3.9 Supporting Capability

`supporting capability` 指为 harness 提供上下文装配、contract 组装、diagnostics、projection、trace 等支撑能力的组件。

典型对象包括：

- `Context/Contract Assembler`
- published deliverable projection / adapter
- observation / trace adapter

它们不是第五层架构，只是为四层服务的支撑能力。

### 3.10 Leaf Agent

`leaf agent` 指被编排层激活、基于 `ExecutionContract` 执行具体任务的 agent。

它们是执行参与者，不是 harness 顶层层级。

## 4. 业务模式与作用域边界

`quick` 与 `project` 不是两套生成架构，而是同一套 `single-episode engine` 的两种外层包装：

- `quick` 直接进入单 `episode` 引擎
- `project` 在外层组织多个 `episode`，并复用同一个单 `episode` 引擎

这意味着：

- `project` 不得拥有另一套 per-episode runtime/control-plane
- `project` 不得重写 gate contract
- `project` 不得重写 episode 内部 revise/replan 语义
- `project wrapper` 属于 harness 之外的产品包装层，不应被误记为第五层

同时还应明确：

- `external scheduler` 在 harness 之外
- `supporting capability` 在 harness 之内、但不构成新的顶层层级
- `leaf agents` 是执行参与者，不构成新的顶层层级

## 5. 架构目标

single-episode 的目标架构是：

- 编排层以 `llm-decision` 为中心
- 控制层承载 runtime state machine 与 control command
- 门控层提供边界事实检查与 gate result
- 治理层提供 contract、诊断、质量门槛与关闭条件

四层共同构成一套统一的 `single-episode agent harness`。

## 6. 全局架构约束

以下约束属于全局硬边界：

1. 单个 `episode` 的 MAS 主线固定为 `OrchestratorAgent`
2. 不允许存在第二条并列的 single-episode 主线
3. `task queue / worker / API` 只负责启动主线，不负责在多条主线之间路由
4. 编排层必须是 `llm-decision-centric`
5. 控制层是 `workflow_session / node / attempt / gate / decision` 的主写层
6. 控制层不得长成第二个业务编排器
7. 门控层不得调度 workflow，不得改激活池
8. 治理层不得介入 live execution decision
9. `runtime substrate` 属于控制层底座，不属于治理层或编排层
10. `quick` 与 `project` 必须复用同一个 `single-episode engine`

### 6.1 Runtime SoT 主写层判定标准

以下动作属于控制层的 `runtime SoT` 主写行为：

- 推进 `workflow_session.status`
- 推进 `workflow_node_state.status`
- 创建和关闭 `workflow_node_attempt`
- 打开和关闭 `workflow_gate`
- 消费 `workflow_gate_decision` 后驱动 `resume / retry / fail / complete`

任何实现只要执行上述动作，都属于控制层的运行时主写路径。  
这条判定规则只用于识别“谁在推进 runtime SoT”，不应用来重新定义 single-episode 主线。

### 6.2 主线与主写层的关系

single-episode 主线与控制层主写层不是两条并列主线，而是一条系统中的不同职责：

- `OrchestratorAgent` 是 MAS 主线
- 控制层是主线配套的 runtime SoT 主写层
- 门控层和治理层分别提供边界判断与质量约束

因此，后续不应再把当前 `runtime kernel` 误表述为“另一条可选主线”，而应将其视为控制层实现是否越界的问题。

## 7. 四层架构定义

### 7.1 编排层

职责：

- 理解 episode 上下文
- 生成 orchestration intent
- 做 LLM runtime decision
- 决定 agent activation / runtime replan

禁止：

- 自己形成第二条 single-episode 主线
- 直接持有与控制层并列的 live runtime state machine
- 直接承担 gate state persistence

### 7.2 控制层

职责：

- 维护 `workflow_session / node / attempt / gate / decision`
- 驱动 runtime state transition
- 承载 `pause / resume / retry / apply / lineage`
- 提供 runtime view 与命令面
- 作为主线配套的 runtime SoT 主写层

禁止：

- 直接成为产品流水线编排器
- 直接承担 LLM orchestration decision
- 直接重写门控判断逻辑

### 7.3 门控层

职责：

- 接收边界事实
- 产出 gate result / decision input
- 对显式 contract 做校验

禁止：

- 调度 workflow
- 修改激活池或执行队列
- 直接驱动 session 生命周期推进

### 7.4 治理层

职责：

- contract 定义
- diagnostics
- quality gates
- review gates
- closeout criteria

禁止：

- 介入 live execution decision
- 直接驱动 runtime state transition

### 7.5 层间依赖方向

允许的依赖方向应为：

- 外部调度层 -> 编排层
- 外部调度层 -> 控制层启动命令
- 编排层 -> 控制层
- 编排层 -> 门控层
- 控制层 -> 门控层
- 治理层 -> 观察所有层

禁止的依赖方向包括：

- 外部调度层 -> 在多条单集主线之间路由
- 门控层 -> 编排层调度命令
- 门控层 -> 控制层生命周期推进
- 治理层 -> 控制层 live command
- 治理层 -> 编排层 live decision
- 控制层 -> 直接承担编排层的 LLM decision

这意味着四层不是“平铺并列的模块分类”，而是具有明确调用方向和越层禁令的正式结构。

## 8. 编排层设计定位

`OrchestratorAgent` 是当前 single-episode 的正式 MAS 主线。它应承担：

- episode 内的 LLM decision
- subagent orchestration
- runtime decision generation

它不应长期承担：

- 第二套控制层实现
- 与控制层并列的 live state machine ownership

## 9. 控制层设计定位

控制层通过 `runtime substrate` 承载运行态，其核心对象包括：

- `workflow_session`
- `workflow_node_state`
- `workflow_node_attempt`
- `workflow_gate`
- `workflow_gate_decision`

这些对象是单个 `episode` runtime 的 SoT，用来承载：

- 节点状态
- gate 等待与放行
- attempt lineage
- resume / retry / failure / completion

控制层是 single-episode 主线的配套层，不是并列主线。  
它的设计目标是支撑 orchestrator 主线，而不是替代 orchestrator 形成第二条 live path。

## 10. 门控层设计定位

门控层的职责是把边界事实转成显式 gate contract：

- subagent report
- boundary facts
- gate trigger
- decision input

门控层只能产出判断输入与结果，不得替代编排层做调度，也不得替代控制层做状态推进。

## 11. 治理层设计定位

治理层是 single-episode harness 的审计与质量护栏，主要包括：

- contract hardening
- diagnostics
- focused verification
- closeout review
- plan quality gates

治理层必须独立于 live execution path。

## 12. Runtime Substrate 的正式定位

`runtime` 在本架构中不是新的顶层层级，而是控制层的运行时底座。

它的设计目标是把一次 agent 驱动的 episode 执行提升为：

- 可暂停
- 可恢复
- 可 gate
- 可审计
- 可追踪 lineage

因此：

- `RuntimeSessionService` 属于控制层底座
- `workflow_session/node/attempt/gate/decision` 属于控制层状态机对象
- 它们不应回流给 `Task`、`WorkflowState` 或门控逻辑本身持有

## 13. Single-Episode 正式主链

single-episode 的正式主链应描述为：

`task queue / worker start -> orchestrator mainline -> orchestration decision -> agent execution -> report -> gate -> decision -> control-layer apply -> runtime state transition`

这里的关键点是：

- 外部调度层只负责启动主线
- orchestrator、control-plane、gate、runtime substrate 必须服务同一条主线
- 不能再并列出第二条可独立推进 episode 的执行路径

### 13.1 主链中的职责分工

在这条主链上：

- 编排层负责产出 intent / runtime decision
- 门控层负责把 report 和 boundary facts 收成显式 gate 输入
- 控制层负责承接 decision 并推进 runtime state transition
- 治理层负责验证、审计和关闭条件，不参与主链推进

任何组件如果同时承担“第二主线推进 + 控制层状态主写”两类职责，都应被视为高风险越层点。

## 14. 组件映射

当前仓库中的主要组件可映射为：

- 编排层：
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py)

- 控制层：
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py)
  - [orchestration_runtime_controller.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_runtime_controller.py)
  - [orchestration_control_plane.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_control_plane.py)

- 门控层：
  - [orchestration_protocol.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_protocol.py)
  - gate evaluator / decision input 相关组件

- 治理层：
  - plans / review gates / focused tests

- 外层多 episode 协调：
  - [episode_orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/episode_orchestrator.py)
  - project queued/direct path 通过显式 `EpisodeOrchestratorAgent.create_default()` 进入项目编排，不再保留独立 `dispatch` wrapper

## 15. 当前实现的架构偏差

### 15.1 已经收敛的部分

当前实现已经收敛的部分包括：

- `004` 已基本收住 orchestrator 主链中的 rule-centric runtime ownership
- protocol / control-plane / runtime-controller 的边界比旧实现清晰
- `quick/project shared episode engine` 的产品语义已经基本对齐

这些成果不应被当前双宿主问题否定。

另外，`dispatch`/`mode_router` 的历史残留已经收口：

- quick 单集主线不再通过 `dispatch` 进入 `OrchestratorAgent`
- project path 也已切到显式 `EpisodeOrchestratorAgent.create_default()`
- `backend/app/core/mode_router.py` 已删除；后续不再把 `dispatch` 当作 single-episode engine 或 project path 的正式组成部分

### 15.2 尚未收敛的部分

当前实现中最关键的架构偏差是：

- `OrchestratorAgent` 已被重构为 MAS 主线
- 但 `EpisodeRuntimeKernel` 仍以独立 live path 方式推进单集运行态

这意味着系统尚未真正统一为一个 single-episode engine。

进一步说，当前尚未收敛的是：

- runtime substrate 与 orchestrator mainline 尚未统一回同一套 harness
- `EpisodeRuntimeKernel` 尚未完成从“越界执行链”到“控制层基础设施”的迁移
- 现有 review 和计划更多覆盖了 ownership 修复，但还没有完全覆盖 single-episode 全局收口

## 16. EpisodeRuntimeKernel 专项判定

对 `EpisodeRuntimeKernel` 的判定必须基于架构，而不是基于“已有代码存在”：

- 它原始出现的动机是为 single-episode 提供 runtime/session/gate substrate
- 这个动机本身是合理的
- 但它当前并没有被正确收进控制层，反而直接推进完整产品阶段链，形成第二条 live path

因此：

- `EpisodeRuntimeKernel` 不是 single-episode 主线，也不是可选主线
- 它不能继续以“独立单 episode 执行宿主”的身份被默认保留
- 它未来只能：
  - 迁移为控制层底座组件
  - 或被退役并吸收入 orchestrator 主线配套的控制层实现

## 17. 迁移原则

后续所有改动必须遵守：

1. 不再新增第二条 per-episode live path
2. 不用 fallback 掩盖越层设计
3. 先修 architecture invariant，再做局部补丁
4. `project` 的改造遵循“由内而外”
5. 所有新增模块都必须标注所属层与禁止事项
6. 不再把 `runtime kernel` 表述为与 orchestrator 并列的主线候选

## 18. 迁移路线图

建议的后续阶段：

- Phase A：冻结 `OrchestratorAgent` 为 single-episode MAS mainline
- Phase B：统一 orchestrator 主线与 runtime substrate
- Phase C：迁移或退役 `EpisodeRuntimeKernel` 的第二主线实现
- Phase D：让 `project` 仅复用统一的 episode engine

### 18.1 每阶段完成标志

- Phase A 完成标志：
  - 已明确 `OrchestratorAgent` 是 single-episode MAS mainline
  - 已明确 `EpisodeRuntimeKernel` 不是主线候选
  - 已把四层禁止事项写入正式架构

- Phase B 完成标志：
  - 不再存在与 runtime substrate 并列的第二套 live runtime loop
  - 所有 live mutation 都统一落到 runtime SoT

- Phase C 完成标志：
  - `EpisodeRuntimeKernel` 已迁移为控制层底座或被退役
  - 不再存在以 kernel 名义推进单集主线的实现

- Phase D 完成标志：
  - `project` 只通过 episode engine 复用单集能力
  - 不再保留 project-specific per-episode runtime logic

## 19. 质量门槛与架构审查项

后续 review 必须显式检查：

- 是否形成第二条 live path
- 是否跨层越权
- 是否把 gate/control/governance 回流到编排层
- 是否让控制层长成固定产品流水线
- 是否破坏 `quick/project shared episode engine`
- 是否把 `runtime kernel` 重新包装成另一条单集主线

### 19.1 架构评审必答题

任何新模块或重构方案，都必须明确回答：

1. 该实现属于哪一层
2. 它读取和写入哪些 SoT
3. 它是否推进 `workflow_session/node/attempt/gate/decision`
4. 它是在服务 orchestrator 主线，还是在形成新的 live path
5. 它是否复用了统一的 episode engine

无法回答这 5 个问题的实现，不应进入主线。

## 20. 未决问题

当前需要继续设计的问题不再是“主线二选一”，而是：

- `EpisodeRuntimeKernel` 如何迁移进 orchestrator 主线配套的控制层底座
- 哪些 runtime/session/gate 能力应保留
- 哪些越界的产品阶段推进职责必须退役

## 21. 附录

建议配套补充：

- 术语表
- 四层依赖方向图
- 当前实现到目标架构的迁移清单
- 与现有计划的映射关系
