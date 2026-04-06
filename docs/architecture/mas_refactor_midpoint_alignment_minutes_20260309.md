# MAS 重构中期架构对齐纪要

日期：2026-03-09

状态：讨论纪要 / 中期对齐输出

用途：在继续执行 `P1-3` 前，统一当前实现状态、偏差判断、术语边界和后续执行约束，避免计划偏离原目标。

说明：

- 本纪要是讨论后的派生记录，不是架构真源
- 如本纪要与 [AGENTS.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/AGENTS.md) 中的原则或后续正式技术设计冲突，应以原则与正式设计为准
- 本纪要只能总结和对齐，不应反向定义新的架构原则
- 顶层层级术语以 [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md) 为准

关联文档：

- [Plan: MAS 编排边界解耦与单 Episode Runtime Kernel 重构](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260308-003.md)
- [MAS Orchestrator 重构边界与技术设计草案](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_refactor_boundary_and_technical_design_20260308.md)
- [MAS Orchestrator 边界专题讨论纪要](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_boundary_discussion_minutes_20260308.md)

## 1. 会议目标

本次讨论不是重新定义总方向，而是对以下问题做一次统一收口：

- 当前已实现部分是否仍然符合原始重构目标
- 中途架构讨论带来的术语和边界修正，是否已同步到计划
- 哪些偏差已经修正，哪些仍是过渡 seam
- 下一步 `P1-3` 应如何执行，才能继续满足“高编排自主扩展性，低规则控制耦合性”

## 2. 当前统一架构表述

内部统一表述为：

- `hybrid subagents`

展开定义为：

- 以 `LLM-based` 自动化编排为主
- 允许少量 `policy` 约束参与决策
- `control-plane`、`gate`、`orchestration` 三层解耦
- `subagents` 仍然是 autonomous `ReAct` agents
- `HITL` 作为 gate capability 挂在 control-plane 上，而不是写进 orchestrator 或 subagent

统一边界原则：

- 编排层负责决策
- 控制层负责调度
- 门控层负责放行
- 子 agent 负责自主执行

## 3. 术语修正

本轮讨论确认，不再用 `contract-first` 概括整体架构。

原因：

- 该词容易被误解为“编排也由 contract 驱动”
- 在当前项目语境下，容易把规则从 `if/else` 搬进 contract/builder，再次形成隐式规则中心
- 该词也不是主流 agent 论文里的核心标准术语
- 这一修正必须服从仓库既有原则，尤其是 `Anti-Hardcoding`、`Non-Pipeline Autonomy`、`Tools are execution-only`、`ReAct Orchestrator`

统一表述应分层理解：

- 总架构表述仍然是 `hybrid subagents`
- 编排边界可描述为 `policy/gate-driven orchestration`
- 执行边界可描述为 `contract-bounded execution`
- 落地实现上强调 `explicit execution boundary`

解释：

- `orchestrator` 仍基于 `LLM intent + runtime state + gate result + limited policy` 做决策
- `contract` 的作用是把已经决定好的执行边界清晰传给 leaf-agent
- `contract` 不是替代编排逻辑的第二套规则中心
- `policy/gate-driven orchestration + contract-bounded execution` 是对实现边界的补充描述，不是新的总架构原则，更不是对 [AGENTS.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/AGENTS.md) 的替代

## 4. 已完成实现与对齐判断

### 4.1 已完成部分

按当前计划，以下阶段已完成：

- `P0-1` 到 `P0-6`
- `P1-0`
- `P1-1a`
- `P1-1b`
- `P1-2`

当前已经落地的关键改造包括：

- 引入 `workflow_session / workflow_node_state / workflow_node_attempt / workflow_gate / workflow_gate_decision`
- 插入 `EpisodeRuntimeKernel`
- 打通 `script gate` 的 `waiting -> decision -> resume`
- 抽离 audio delivery evaluator
- 抽离 audio orchestration policy
- 修复 `video_generator` 的 leaf-agent 边界，使其不再读取 `workflow.plan / audio_route`

### 4.2 当前符合原目标的部分

会议确认，以下方向没有偏离：

- `runtime kernel` 已开始成为真正的 control-plane 宿主
- `script gate` 已不再只是“记录决策再原样重跑”，而是有显式脚本审阅合同
- workflow-level probing 和 delivery check 已从 orchestrator 抽到 evaluator
- audio preflight / standby 的剩余规则已从 orchestrator 收到独立 policy
- `video_generator` 已从“隐式控制协议消费者”收敛为“显式执行边界消费者”

### 4.3 仍未完全闭环的部分

会议确认，当前仍是“方向已对、边界未稳”的中期状态，而不是可宣布完成解耦的稳定状态。

尚未闭环的核心点：

- `video_composer` 仍在 agent 内根据兼容字段推断主 mix 模式
- `runtime_kernel` 中仍保留 `workflow.plan / audio_route` 的兼容 seam
- 兼容 seam 目前可以接受，但必须继续只作为 compatibility/diagnostic path 存在，不能扩散为新主路径

## 5. 当前偏差与修正判断

### 5.1 已确认修正的偏差

以下偏差已经完成修正：

- `video_generator` 不再读取 `workflow.plan / audio_route`
- `video_generator` 不再在 ACT 前 patch tool calls
- orchestrator 不再自己做 audio delivery probing
- orchestrator 不再在 `_should_run_agent` 中直接做 audio gate 评估
- audio preflight / standby 特化逻辑已移入独立 policy，而不是继续堆在 orchestrator

### 5.2 当前仍需防守的偏差

以下偏差还需要持续防守：

- 不允许把兼容字段重新升级成 live 决策协议
- 不允许把规则中心从 orchestrator 搬到 runner / builder / contract assembler
- 不允许用新的 `seam` 层承载业务路由、fallback 和参与者选择

本轮讨论确认的红线：

- `builder` 只能做声明式组装，不能做业务编排
- `stage runner` 只能做阶段边界切分，不能长成第二个 orchestrator
- `ExecutionContract` 只能表达执行边界，不能偷偷承载流程脚本

## 6. P1-3 前的统一技术判断

### 6.1 当前问题定性

`video_composer` 现在的问题，不是 FC/ReAct 外形不对，而是 leaf-agent 还在做 live 控制语义判定。

当前主要问题：

- `_resolve_mix_type()` 仍根据 `add_bgm`、`add_voiceover`、`static_context.requests`、`scene_media_has_voice` 推断主模式
- `_build_mix_receipt()` 记录的是“agent 推断出的模式”，而不是“contract 已决定的模式”
- `_execute_action()` 结束后仍再次依赖这套推断逻辑决定最终写回语义

### 6.2 P1-3 的唯一头号红线

不能让 `video_composer` 重演 `video_generator` 旧路径。

也就是：

- 不能把兼容字段继续当 live 控制协议
- 不能让 agent 内部继续承担 mix/composition 主模式决策
- 不能表面上引入 contract，内部仍靠兼容字段推断

### 6.3 P1-3 的最小正确落点

进入 `P1-3` 时，必须满足以下执行目标：

- `video_composer` 改为 execution-boundary-first
- 主 `compose_mode` 只由显式 execution boundary 决定
- `add_bgm / add_voiceover / static_context.requests / scene_media_has_voice` 降级为 compatibility-only 输入
- `mix_receipt` 记录 contract 已决定的模式，而不是 agent 现场推断模式

## 7. 后续规划统一结论

会议确认，后续阶段不需要推翻总计划，但要继续沿当前修正后的边界执行：

- `P1-3`：清理 `video_composer` 的显式执行边界
- `P1-4`：quick mode 接入 runtime/workspace，且进入 `final_compose` 时仍遵守显式执行边界
- `P2-1 / P2-2`：`storyboard` 和 `scene_video` gate 的下游执行只消费 approved artifact / node contract
- `P2-3`：project mode 复用的是同一套 `hybrid subagents` 边界，不只是复用 runtime kernel

## 8. 会议结论

本轮统一结论如下：

- 当前重构主线没有偏离原目标
- 中途术语和边界修正是必要的，而且已经基本同步到计划
- 当前系统应继续被定义为 `hybrid subagents`，而不是纯规则系统，也不是完全自由 swarm
- 后续不再用 `contract-first` 概括整体架构；总架构表述仍为 `hybrid subagents`
- `policy/gate-driven orchestration` 与 `contract-bounded execution` 只作为当前实现边界描述继续保留
- 所有后续实现仍必须以 [AGENTS.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/AGENTS.md) 中的反硬编码、ReAct、自主性与工具边界原则为准
- 下一步可以继续按计划执行，但必须以 `P1-3` 的红线为边界推进，防止 `video_composer` 成为新的隐式规则中心

## 9. 下一步动作

- 进入 `P1-3`
- 先定义 `video_composer` 的显式 execution boundary
- 再把兼容字段的消费前移到 assembler / adapter
- 实现完成后，回到同一套架构审查标准下做一次对齐复核
