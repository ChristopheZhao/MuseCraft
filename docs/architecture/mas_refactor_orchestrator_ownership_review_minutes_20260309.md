# MAS 重构收尾前技术复核纪要

- 日期：2026-03-09
- 主题：当前阶段是否可以收口；`orchestrator` residual ownership 是否仍阻碍 MAS 去规则中心化
- 结论：**当前阶段不能草草收尾，需在当前范围内新增 `orchestrator ownership 收口阶段`。**

说明：

- 本文档是技术复核纪要，不承担正式架构术语定义
- 对 `orchestrator / control-plane / gate` 的理解应服从后续 canonical vocabulary

## 1. 会议背景
- 已完成：
  - `video_generator` 去编排化
  - `video_composer` 显式执行边界化
  - `script gate` 最小闭环
  - quick mode 最小前端适配
  - compatibility retirement 第一轮
- 原计划曾接近“当前范围收口”
- 但在对 [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) 的 residual logic 复核后，确认 ownership 迁移并未完成

## 2. 当前实现的有效进展
- 当前实现并未偏离总目标，已完成的边界修复仍然成立：
  - [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py) 不再读取 `workflow.plan/audio_route`
  - [video_composer.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_composer.py) 主 `mix_mode` 不再由 legacy flags 推断
  - [runtime_kernel.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/runtime_kernel.py) 已具备 `script gate` runtime owner 雏形
  - quick mode 前端已达到“最小适配”目标

## 3. 当前不能收口的核心原因
### 3.1 tail-stage runtime ownership 仍在 orchestrator
- `script` 审批通过后，[runtime_kernel.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/services/runtime_kernel.py#L248) 仍通过 `orchestrator.execute()` 一把跑完整个尾段。
- 这意味着 `storyboard / scene_video / compose / quality` 目前仍不是 kernel 可见的真实 node execution boundary。

### 3.2 orchestrator 仍持有 live execution-boundary assembly
- [_build_agent_execution_contract](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1457) 仍由 orchestrator 直接组装 `ExecutionContract`。
- 这和目标边界不一致：`ExecutionContract` 应由 control-plane / assembler 负责，orchestrator 应消费 `ExecutionIntent` 与 runtime state。

### 3.3 orchestrator 仍回写 legacy-shaped control fields
- [_apply_execution_boundary_to_agent_input](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1497) 仍把 `compose_mode` 回写成 `static_context.requests.*`。
- 这说明 live path 中仍存在“把新边界翻译回旧控制语义”的兼容桥接。

### 3.4 orchestrator 仍保留 audio-specific controller 逻辑
- [_decide_replan_action](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1556) 仍显式认识 `AUDIO_GENERATOR`、`VIDEO_COMPOSER` 以及对应 runtime gap。
- 这部分不是简单的 gate result 消费，而是残留的中心化 controller 逻辑。

## 4. residual logic 分级
### P0：当前范围内必须继续收敛
- [_build_agent_execution_contract](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1457)
- [_apply_execution_boundary_to_agent_input](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1497)
- [_decide_replan_action](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1556)
- `script gate` 后尾段仍由 [orchestrator.execute](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) 托管这一点

### P1：可作为过渡 seam 暂留，但不得扩散
- [_build_workflow_plan](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1331)
- [_build_activation_pool](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1367)
- [_resolve_agent_runtime_overrides](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1437)
- [_activate_standby_agent](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1686)
- [_normalize_audio_route_payload](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1809)
- [_capture_audio_delivery_gate_observation](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1849)

## 5. 前端范围结论
- 当前前端已达到本期“最小适配”目标：
  - [HomePage.tsx](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/pages/HomePage.tsx)
  - [QuickModeWorkspace.tsx](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/components/preview/QuickModeWorkspace.tsx)
- 本期前端应冻结为：
  - runtime/session/gate 最小展示
  - `script gate` 决策提交
  - 完成态回到 review/export 的最小闭环
- 更重 HITL 工作台不属于当前范围

## 6. 统一结论
- 当前不是“计划失败”，而是“原计划少了一个关键收口阶段”
- 本期主线仍然是：
  - `hybrid subagents`
  - 高自主扩展性
  - 低规则耦合性
  - 前端最小适配
- 因此需要扩展当前计划，在 compatibility retirement 之后新增：
  - **`orchestrator ownership 收口阶段`**

## 7. 建议的计划调整
- 新增当前范围任务：
  - 收回 `script gate` 后尾段执行所有权
  - 迁出 orchestrator 内的 execution-boundary live 组装
  - 删除 execution boundary -> legacy request 的 live 回写
  - 收缩 audio-specific replan/controller/state persistence residuals
- 在完成上述收口前，不进入下一期的：
  - `storyboard gate`
  - `scene_video gate`
  - `project mode reuse`

## 8. 一句话总结
- **当前阶段不能收尾。**
- **前端已收敛。**
- **计划应扩展一个 `orchestrator ownership 收口阶段`，否则不能宣告本期 MAS 重构达成预期设计。**
