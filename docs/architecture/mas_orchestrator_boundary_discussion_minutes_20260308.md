# MAS Orchestrator 边界专题讨论纪要

日期：2026-03-08

状态：专题讨论初步结论纪要

用途：作为后续专项审查、架构评估与重构设计输入，不替代实施计划。

说明：

- 本文档是专题讨论纪要，不承担正式架构术语定义
- 文中出现的 `planner / control-plane / gate/evaluator / leaf-agent` 口径应与当前 canonical vocabulary 对齐理解

## 1. 讨论背景

本轮专题讨论聚焦一个核心问题：

- 当前项目的 `MAS` 中心化编排实现，是否已经把 `planner`、`control-plane`、`gate/evaluator`、`leaf-agent` 四层职责混写。
- 如果继续沿当前方式扩展，是否会阻断：
  - 新 agent 的可插拔扩展
  - quick mode 的 `HITL`
  - project mode 对单 `episode` 内核的复用
  - 从“偏预定义 MAS”迁移到“更自主 MAS”

讨论起点来自对如下实现的集中审视：

- `backend/app/agents/orchestrator.py`
- `backend/app/agents/video_generator.py`
- `backend/app/agents/video_composer.py`
- `backend/app/agents/quality_checker.py`

## 2. 参会角色

- 系统架构负责人
- 后端 / 工作流负责人
- Agent Runtime / ReAct 负责人
- 风险审查 / 代码演化负责人
- 产品 / 交互讨论结论作为输入约束沿用，不在本轮重新争论

## 3. 当前代码现象

### 3.1 Orchestrator 并未真正掌握“能力驱动编排”

当前 `orchestrator` 的主问题不是“文件太长”，而是规则先决定、`LLM` 后补说明：

- 运行前先构造 `activation_pool`，再把裁剪后的 agent 集交给 `_llm_decompose_tasks()`：
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L212)
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L254)
- 执行队列本质上仍是 `activation_pool`，并非由 `LLM` 输出的 agenda 主导：
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L260)
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L2524)
- `_build_workflow_plan()` 直接写死 `active_pool / standby_pool / actions / trigger_after`，并显式特化音频链路：
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1331)
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1373)
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1401)

结论：当前更接近“集中式规则引擎 + LLM 指令填空器”，而不是理想的中心化 `MAS orchestrator`。

### 3.2 编排层与门控层已混在一起

`orchestrator` 内部不仅在做编排，还在做交付检查、runtime probing、route/signal 拼装和 fallback 决策：

- route / signal 组装：
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1848)
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1907)
- runtime 媒体事实探测与 `ffprobe`：
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1941)
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L2030)
- `AUDIO_GENERATOR` 等特定 agent 的运行判定：
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L2061)
- 特化的 replan/fallback：
  - [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1579)

结论：当前 `orchestrator` 已同时承担 `planner + gate + fallback controller + signal builder` 多重职责。

### 3.3 Leaf Agent 已开始反向理解 control-plane 协议

`video_generator` 是当前最明显的 control-plane 语义泄漏点：

- 读取 `workflow_plan / audio_route / workflow.plan / workflow.audio_route`：
  - [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L324)
- 解析 plan 里的 action 决策：
  - [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L357)
- 在 ACT 前 patch LLM 产出的 tool calls：
  - [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L378)
  - [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L423)

结论：`video_generator` 已不再是“只执行 execution contract 的 leaf agent”，而是“半个 orchestrator”。

### 3.4 次级边界漂移已经出现

虽然不如 `video_generator` 严重，但仍有边界漂移苗头：

- `video_composer` 在 agent 内部推断 `mix_type`：
  - [video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py#L68)
- `quality_checker` 的 evaluator 角色合理，但现在仍主要服务于 terminal/final-only 场景：
  - [quality_checker.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/quality_checker.py#L161)

## 4. 多角色讨论结论

### 4.1 架构结论

- 当前问题不是某个 agent 太“笨”，而是分层失效。
- `orchestrator` 应退回到：
  - 默认阶段骨架
  - 候选 agent 调度
  - planner 输出消费
  - gate 结果消费
  - 少量 hard guard
- 不应继续承担：
  - runtime probing
  - delivery check
  - route/signal 组装
  - agent-specific fallback 分支

### 4.2 后端 / 工作流结论

- 当前仓库实际缺的是独立 `control-plane`，而不是“再加强一点 orchestrator”。
- 现状只有 `Task` 和 shared memory facts，没有：
  - `workflow_session`
  - `node`
  - `attempt`
  - `gate`
  - `decision`
- 这会直接卡住 quick mode 的 `HITL`，并让 project mode 只能复制现有耦合。

### 4.3 Agent Runtime 结论

- `video_generator` 属于 `P0` 级问题，必须优先整改。
- `video_composer` 属于次一级边界漂移，后续需要转成显式 execution contract。
- 其余 live agents 本轮未发现同等级别的 control-plane 协议泄漏。

### 4.4 风险审查结论

当前实现已经直接冲突仓库既有原则：

- `Anti-Hardcoding`
- `Non-Pipeline Autonomy`
- `Tools are execution-only`
- `ReAct Orchestrator`

参见：

- [AGENTS.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/AGENTS.md#L6)
- [AGENTS.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/AGENTS.md#L9)
- [AGENTS.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/AGENTS.md#L46)
- [AGENTS.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/AGENTS.md#L48)

## 5. 初步架构判断

本专题形成的初步判断如下：

- 理想态：中心化 `MAS orchestrator` 能基于能力目录自主编排 `subagents`。
- 现实态：由于当前高成本视频场景存在可控性、质量和副作用问题，允许保留部分预定义约束。
- 但这些预定义约束不应继续堆入 orchestrator 的业务分支。
- 更合理的做法是：
  - 把“约束、检查、放行条件”尽量放入 `policy + gate/evaluator`
  - 把“阶段骨架和运行时控制”放入 `control-plane`
  - 让 `orchestrator` 只负责规划与消费 gate 结果
  - 让 `leaf agents` 只执行显式 contract

一句话收敛：

`现阶段最合理的过渡架构是：有限骨架的中心化 orchestrator + 独立 policy/gate + 只执行 contract 的 subagents。`

## 6. 已达成共识

### 6.1 什么必须保留在 orchestrator

- 默认阶段骨架
- 候选 agent registry / capability catalog 消费
- planner 输出解析
- runtime 控制动作消费
- 少量 hard guard

### 6.2 什么必须从 orchestrator 移走

- `ffprobe` / 媒体交付 probing
- route / signal 组装
- “是否满足交付 contract”的事实判断
- 按特定 agent 类型写死的业务路由
- 特定 fallback / replan 分支

### 6.3 什么必须显式化为 control-plane

- `workflow / node / attempt / gate / decision`
- `pause / resume / revise / retry / replan`
- `active_pool / standby_pool` 等运行时控制状态
- 未来 quick mode 与 project mode 的共享单 `episode` 内核

### 6.4 什么不能再继续出现在 leaf agent

- 读取 `workflow.plan / audio_route / activation_pool`
- 解析上游 plan 中自己的 action
- 根据 control-plane 协议二次 patch tool calls
- 在 generation agent 内部承担 gate/fallback 判断

## 7. 问题分级

### P0

- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py)
- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py)

### P1

- [video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py)
- [quality_checker.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/quality_checker.py)
- [script_writer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/script_writer.py)

### P2

- 其余 live agents 做专题化横扫复核，确认是否存在第二个 `video_generator` 级问题点。

## 8. 对后续 HITL 与 MAS 演进的影响

- 如果继续把规则、fallback 和 gate 写进 orchestrator，quick mode 的 `HITL` 只能做成 one-shot 外围补丁。
- project mode 也无法真正复用单 `episode` 工作流内核。
- 未来模型能力增强时，也难以从“偏预定义 MAS”平滑迁到“更自主 MAS”。

因此本专题的一致判断是：

- 后续要提升自主性，不是先删光所有规则。
- 而是先完成 `orchestrator / control-plane / gate / leaf-agent` 的解耦。
- 只有这样，预定义约束才能逐步从“编排分支”迁移为“独立 policy / guardrail / gate”。

## 9. 后续建议

本纪要之后，建议进入以下顺序：

1. 形成专项风险审查纪要
2. 输出目标分层图
3. 列出当前代码违背点与禁止继续扩散的模式
4. 再进入正式重构方案设计

本阶段不建议：

- 继续在 `orchestrator.py` 上追加 agent-specific 分支
- 继续在 `video_generator.py` 里消费 control-plane 协议
- 在没有独立 control-plane 的前提下直接做 quick mode `HITL`
