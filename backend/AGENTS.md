# 后端 Agent 状态边界

本文件补充[根指令](../AGENTS.md)。现行职责入口见[文档中心](../docs/README.md)，不再引用已不存在的 PHASE_2 设计。

## 内循环、交付与运行时

- Agent 内循环记录本轮动作、观察、反思和待执行意图，支撑下一轮规划。它不拥有 workflow/session/node/attempt/gate 的权威终态。
- 模型的结束意图可以请求停止循环；专业 Agent 的报告如实区分 completed、partial、failed。报告接纳、控制面处置和成功提升遵循[PLAN-069](../docs/plans/active/PLAN-20260808-069.md)。
- 媒体交付完成必须依据已验收的交付事实。文件路径、URL、工具成功或 Agent 私有 completed 集合都不能单独授权完成、跳过或发布。
- 计划场景集合来自已发布的场景输入；successful/remaining 由已验收事实派生的 progress read-model 提供。Agent 使用它规划，投影本身不能写回第二套完成真相。
- runtime/session/node/attempt/gate/decision 状态由 MAS control plane 独占；最终成片可见性与当前 execution/attempt 的 finalize receipt、权威终态协调。
- 具体边界见[规划/执行/交付/进度合同](../docs/architecture/planner_execution_output_progress_boundary_freeze_20260402.md)。

## 记忆、恢复与跨 Agent 事实

- Agent scope 是可丢弃工作区；MAS Shared WM 是受控共享事实表面。长期 Memory 是持久化/复用能力，不是 runtime 控制面。
- 迭代动作与观察通过既有适配器记录。工具产物可以在迭代内经显式验收边界写入共享事实；这不等于提前发布 Agent 最终输出或推进 runtime 终态。
- 编排通过 ContextAssembler 读取发布边界，通过 MemoryWriter 回写长期摘要。可选长期记忆不可用时显式诊断；必需交付引用、身份或权威绑定缺失时不得用旧记忆修补。
- 恢复服从当前 runtime、continuation 与交付合同，不能仅凭私有快照或“最新资产”宣布成功。
- 详细归属见[编排/上下文/记忆冻结](../docs/architecture/orchestration_context_memory_boundary_freeze_20260330.md)和[延期护栏](../docs/deferred-plans/CURRENT.md)。

## 工具与执行身份

- 外部服务经已分配工具访问；FC schema 表达能力，Prompt 不承担工具参数规则。
- 工具调用在同一 FC round 选择并执行，不维护跨阶段 planned_calls 队列。
- Native Agent 保持 ReAct 自主性；确定性 MAS stage 和应用 coordinator 的身份按[项目/runtime 边界](../docs/architecture/project_runtime_authority_boundary_20260719.md)区分，不因类名含 Agent 就赋予自主决策或存储所有权。
- Agent 通过 typed execution request/result 与外界交互，不接收 ORM entity、Session 或数据库组装职责。

## 可观测性

- 事件记录专业事实和诊断。前端只消费显式 read-model；事件或队列状态不能另行创造 runtime 成功。
- 2026-09-06：替代旧版“inner_react_state 独占所有完成判定 / 资产存在即跳过 / 迭代中禁止一切共享写入”表述；内循环控制与交付、发布、runtime 状态分层。
