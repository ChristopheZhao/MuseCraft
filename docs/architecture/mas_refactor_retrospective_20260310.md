# MAS Refactor Retrospective 2026-03-10

## 1. Purpose
- 记录本轮 MAS 重构的过程、关键转折、阶段成果、未收口问题与后续接续方式。
- 与经验卡不同，本文件偏项目过程复盘，不追求抽象成通用规则，而是说明这次任务为什么演进成当前状态。

说明：

- 本文档是 retrospective / process record，不承担正式架构术语定义

## 2. Original Intent
- 本轮原始目标是把 short-video-maker 当前偏 `rule-centric` 的 MAS 实现拉回到更合理的 `hybrid subagents` 架构：
  - orchestrator 回到 `llm-decision-based orchestration`
  - gate 与编排层解耦
  - control-plane 持有 runtime/gate/session/node
  - leaf-agent 只消费显式执行边界
- 同时为后续 HITL 留出正确宿主，但不把本期重心放在重 HITL 产品化上。

## 3. Process Summary

### 3.1 初始问题识别
- 初期主要集中在：
  - orchestrator 持有过多规则编排、fallback、gate、state persistence 逻辑
  - `video_generator` 等 leaf-agent 读取 `workflow.plan/audio_route` 并 patch tool calls
  - quick mode 仍是 one-shot，无法承接正确的 gate/runtime

### 3.2 第一轮架构收敛
- 形成了较清晰的中期方向：
  - `hybrid subagents`
  - 本期聚焦 MAS 去规则中心化
  - quick mode 前端只做最小适配
  - HITL 重范围移出本期
- 对应沉淀了多份设计和讨论纪要，并落成了主计划：
  - [PLAN-20260308-003.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260308-003.md)

### 3.3 真实实现推进
- 本轮实现上完成了多项真实进展：
  - runtime kernel / runtime session 基础设施落地
  - `script gate` 打通
  - `video_generator` 从读取 `workflow.plan/audio_route` 的坏模式中拉出
  - `video_composer` 改成显式执行边界驱动
  - quick mode 只做最小 script gate workspace 适配
  - 兼容层完成了一轮 retirement
  - 旧的 audio domain preflight/activation planner 退出 live path

### 3.4 中期复核与范围收紧
- 在接近“看起来可以收尾”时，多轮架构复核发现：
  - orchestrator 主循环 ownership 仍未收口
  - controller 仍在代偿 queue/replan/fallback 决策
  - protocol 还不是强边界
  - 测试仍缺主循环真实链路覆盖
- 因此，本轮没有继续扩重 HITL，而是进一步把重心拉回 orchestrator ownership 收口。

### 3.5 Context Rot 信号出现
- 随着多轮“实现 -> 复核 -> 修正”推进，开始出现明显的 `context rot`：
  - 同一计划承载了太多阶段性判断和临时结论
  - 一些旧质检结论已过时，但仍容易被继续引用
  - 局部 seam cleanup 容易被误判成整体架构收口
- 这直接触发了这次 checkpoint 决策。

## 4. What Was Actually Achieved
- 这轮并不是“没有完成”，而是完成了以下有价值的阶段成果：
  - 建立了正确的目标架构语言：`hybrid subagents`
  - 明确了本期不是 HITL 产品化，而是 MAS 去规则中心化重构
  - 建立了 runtime kernel、script gate、显式执行边界和最小 quick mode 适配
  - 识别并清理了一批明显的 anti-llm-decision 实现
  - 明确了什么不算完成：局部 seam cleanup 不等于 ownership 收口

## 5. What Is Still Not Solved
- 当前仍未真正收口的点集中在：
  - orchestrator 主循环仍直接串起 `report -> gate -> decision -> apply`
  - runtime controller 仍持有 queue/activation/fallback spec 的代码侧逻辑
  - protocol 仍会在缺少显式 `orchestration_report` 时静默默认化
  - 缺少 orchestrator 主循环真实链路的 E2E 验证
- 这些问题说明当前仍未达到 `more llm decision, less hard-coding` 的收口标准。

## 6. Root-Cause Analysis
- 这轮最核心的根因不是“单点 bug”，而是：
  1. ownership 迁移没有真正完成，只做了部分 seam cleanup
  2. 历史兼容与阶段性过渡逻辑持续干扰判断
  3. 架构讨论结论虽然逐渐清晰，但实现层多次在主循环/controller/protocol 处回流
  4. 缺少主循环真实链路测试，使局部修复更容易被误判为整体收口

## 7. Why Checkpoint Instead of Forcing Closure
- 当前不适合把旧计划继续硬推到 `completed`，原因是：
  - 会把未收口问题掩盖掉
  - 会继续放大 `context rot`
  - 会让后续接手者难以分辨哪些结论仍有效、哪些已经过时
- 因此本轮选择：
  - 把旧计划做成 checkpoint 基线
  - 明确保留阶段成果
  - 再开一份更窄的新计划继续收 orchestrator 主循环 ownership

## 8. Successor Decision
- 本轮后续不再沿用“全景重构计划”继续叠加，而是切到新计划：
  - [PLAN-20260310-004.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260310-004.md)
- 新计划只聚焦：
  - orchestrator 主循环 ownership
  - runtime controller 纯 apply 化
  - protocol 强边界化
  - 主循环 E2E 验证

## 9. Related Documents
- [PLAN-20260308-003.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260308-003.md)
- [mas_refactor_checkpoint_20260310.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_refactor_checkpoint_20260310.md)
- [PLAN-20260310-004.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260310-004.md)
- [EXP-20260310-0002.json](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/experience/cards/EXP-20260310-0002.json)

## 10. Final Assessment
- 本轮不是失败，而是一个有效的阶段性收敛。
- 它最大的价值在于：
  - 把“什么才算真正的 MAS 去规则中心化收口”讲清楚了
  - 让下一轮不需要再从头讨论，而能直接聚焦 residual ownership
