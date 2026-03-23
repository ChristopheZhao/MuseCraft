# MAS Architecture Alignment Note

日期：2026-03-23

状态：alignment note

用途：收敛 `single-episode harness` 的顶层架构词汇，避免后续讨论继续把“层级术语”和“具体组件名”混用。

相关实现差距清单：

- [mas_architecture_deviation_inventory_20260323.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_deviation_inventory_20260323.md)

## 1. 结论

当前仓库的主问题不是“四层 MAS 架构不合理”，而是：

- 正式架构基线已经存在，但旧文档没有充分降级
- `control-plane / 控制层` 被层名、组件名、历史文档口径重复占用
- supporting capability 与顶层层级的边界没有在讨论中保持稳定

后续讨论必须先统一词汇，再讨论具体组件或实现收口。

## 2. Canonical Vocabulary

`single-episode harness` 的顶层正式架构只有四层：

1. 编排层
2. 控制层
3. 门控层
4. 治理层

补充约束：

- `runtime substrate` 属于控制层底座，不是第五层
- `Context Assembler / Contract Assembler` 属于 harness 支撑能力，不是新的顶层层级
- `Leaf Agents` 是执行参与者，不是 harness 顶层层级

## 3. 统一口径

### 3.1 编排层

职责：

- 理解 episode 上下文
- 产出 orchestration intent / runtime decision
- 决定 agent activation / runtime replan

宿主：

- `OrchestratorAgent`

禁止：

- 主写 runtime SoT
- 持有与控制层并列的 live state machine

### 3.2 控制层

职责：

- 主写 `workflow_session / node / attempt / gate / decision`
- 推进 runtime state transition
- 承接 `pause / resume / retry / revise / replan / apply / lineage`

包含但不限于这些组件：

- `RuntimeSessionService`
- `OrchestrationRuntimeController`
- `OrchestrationControlPlane`
- runtime substrate models

说明：

- `OrchestrationControlPlane` 只是控制层中的一个组件名，不等于整个控制层

### 3.3 门控层

职责：

- 产出 `GateResult`
- 产出 human/system decision input
- 对边界事实和显式 contract 做校验

禁止：

- 直接推进 session lifecycle
- 直接调度 workflow

### 3.4 治理层

职责：

- contract 定义
- diagnostics
- quality / review / closeout criteria

禁止：

- 介入 live execution decision
- 发出 runtime live commands

## 4. Supporting Capabilities

下列对象不是新的顶层层级：

- `runtime substrate`
- `Context Assembler / Contract Assembler`
- `published deliverable adapter / projection`
- `Leaf Agents`

它们分别属于：

- 控制层底座
- harness 支撑能力
- 边界输出/投影能力
- 执行参与者

后续讨论中，不得把这些对象提升成与四层并列的“第五层/第六层”。

## 5. Normative Document Set

一级真值：

- [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md)

二级细化：

- [mas_runtime_control_plane_detailed_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_control_plane_detailed_design_20260308.md)
- [mas_runtime_contracts_detailed_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_contracts_detailed_design_20260308.md)
- [quick_mode_hitl_technical_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/quick_mode_hitl_technical_design_20260308.md)

历史参考：

- [multi-agent-communication-architecture.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/multi-agent-communication-architecture.md)
- 其他仍描述“旧 orchestrator-centered 主干实现”的前序文档

规则：

- 只有一级真值文档可以定义顶层层级术语
- 二级细化文档只能细化，不得重定义顶层层级
- 历史参考文档不得再被当成现行术语来源

## 6. Discussion Protocol

后续任何架构讨论，先回答这 3 个问题：

1. 当前讨论的是顶层层级，还是具体组件？
2. 当前讨论的是正式术语，还是历史实现快照？
3. 当前对象属于四层之一，还是属于 supporting capability？

如果这 3 个问题没先回答，不进入实现讨论。

## 7. One-Sentence Handoff

`single-episode harness` 的顶层正式架构只有四层：编排、控制、门控、治理；`runtime substrate` 属于控制层底座，`Context/Contract Assembler` 属于支撑能力，`Leaf Agents` 是执行参与者；`OrchestrationControlPlane` 只是控制层中的一个组件名，不代表整个控制层。
