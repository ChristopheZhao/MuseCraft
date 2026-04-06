# MAS Refactor Checkpoint 2026-03-10

## Purpose
- 对 [PLAN-20260308-003.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260308-003.md) 做一次阶段性 checkpoint
- 固化当前现状、过时结论、未解决问题与后续新计划入口

说明：

- 本文档是 checkpoint 记录，不承担正式架构术语定义

## What Was Actually Achieved
- runtime kernel、script gate、quick mode 最小适配、compatibility retirement 第一轮已落地
- `video_generator` 与 `video_composer` 的显式执行边界已建立
- `audio_orchestration_policy` 已退出 live path，旧的 domain-specific preflight/activation planner 不再作为主路径设计
- 编排 trace 已开始从编排状态宿主向 observation adapter 迁移

## What Is Still Not Solved
- orchestrator 主循环仍直接串起 `report -> gate -> decision -> apply`
- runtime controller 仍持有 queue/activation/fallback spec 的代码侧控制逻辑
- protocol 仍不是严格边界，缺少显式 report 时会静默默认化
- 测试仍缺 orchestrator 主循环真实链路的端到端覆盖

## Stale Conclusions That Should No Longer Be Reused
- “`orchestrator.py:464` 仍是旧 `proceed_next / repeat_agent / halt_workflow` 主循环” 已过时
- “`ExecutionBoundaryAssembler` 还在回写 `static_context.requests`” 已过时
- “protocol 仍按 `AgentType` 伪造 `boundary_event/artifacts`” 已过时

## Why This Checkpoint Was Needed
- 当前计划已多轮迭代，存在明显 `context rot`
- 再继续在同一计划里叠补丁，会放大过渡结论和过时判断
- 更合理的做法是保留本轮成果作为 checkpoint，再开一个更窄的新计划继续收口

## Successor Plan
- [PLAN-20260310-004.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260310-004.md)

## Closure Rule
- 本 checkpoint 不是 completed 结论
- 旧计划不归档，只保留为阶段性基线和证据入口
