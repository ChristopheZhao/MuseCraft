# MAS 重构范围调整技术讨论纪要

日期：2026-03-09

状态：讨论纪要 / 范围调整输出

用途：统一本期 MAS 重构范围，明确将重 HITL 扩展移出当前计划，收敛前端改动范围，并重排后续阶段顺序。

说明：

- 本纪要是讨论收口，不替代 [AGENTS.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/AGENTS.md) 与正式技术设计
- 如与正式设计或仓库原则冲突，以原则和正式设计为准
- 顶层层级术语以 [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md) 为准

关联文档：

- [Plan: MAS 编排边界解耦与单 Episode Runtime Kernel 重构](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260308-003.md)
- [MAS 重构中期架构对齐纪要](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_refactor_midpoint_alignment_minutes_20260309.md)
- [MAS Orchestrator 重构边界与技术设计草案](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_refactor_boundary_and_technical_design_20260308.md)

## 1. 讨论目标

本次讨论聚焦 4 个问题：

- 是否应将重 HITL 扩展移出本期计划
- 当前前端改动是否已经达到“最小适配”边界
- 前端后续计划应如何收敛
- MAS 重构主线与原计划顺序应如何调整

## 2. 统一结论

### 2.1 本期不是 HITL 扩展期

会议确认：

- 本期主目标仍然是 MAS 去规则中心化重构
- `HITL` 本期仅保留 `script gate` 作为 runtime/control-plane/gate 边界验证入口
- `storyboard`、`scene_video`、更完整的 HITL 工作台与 richer review UX 移出本期

原因：

- 当前最大剩余风险仍在 MAS 主线，而不是前端体验
- compatibility retirement 尚未完成
- 若继续扩重 HITL，会把迁移期 seam 和兼容逻辑带入下一层

### 2.2 前端改动已达到最小适配边界

会议确认，当前 quick mode 前端改动已经满足本期目标：

- quick mode 已不再只是纯 one-shot processing 面板
- 前端已能消费 runtime session / active gate 状态
- `script gate` 的 `approve / revise / replan` 已可提交

参考：

- [HomePage.tsx](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/pages/HomePage.tsx)
- [QuickModeWorkspace.tsx](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/components/preview/QuickModeWorkspace.tsx)
- [useTaskPolling.ts](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/hooks/useTaskPolling.ts)
- [useWebSocket.ts](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/src/hooks/useWebSocket.ts)

本期前端后续仅允许：

- 完成 `P1-4e` 的最小 smoke/check
- 修正 script gate flow 相关的小缺陷

本期前端不再继续：

- storyboard 审核台
- scene video 审核台
- richer workspace
- project mode 的 HITL 交互复用

### 2.3 本期主线回到 MAS 去规则中心化

会议确认，本期后续主线应调整为：

1. 收口 `P1-4e`
2. 前移 compatibility retirement
3. 继续 MAS 边界硬化

这意味着：

- 前端工作到 `P1-4e` 为止
- `P2-4 / P2-5` 前移为本期主线
- `P2-1 / P2-2 / P2-3` 延后到下一期范围

## 3. 计划调整结果

调整后的当前范围：

- `P1-4e`：quick mode script gate 最小验证收口
- `P2-4`：停止新路径继续产出 composer legacy flags
- `P2-5`：删除 composer/runtime 兼容 seam，完成 compatibility retirement

调整后的下一期范围：

- `storyboard` gate
- `scene_video` gate
- project mode episode session 复用
- 更重的 HITL 工作台

## 4. 架构约束

本轮讨论再次确认以下红线不变：

- `hybrid subagents` 仍是总架构表述
- 编排层、控制层、门控层与 leaf-agent 必须继续解耦
- 前端不能反向牵引 backend 继续做 HITL 产品化
- compatibility seam 只能短期存在，且必须在计划中有 retirement 阶段
- 不允许把“前端最小适配”继续扩成新的范围中心

## 5. 下一步动作

- 更新主计划，重排后续阶段顺序
- 收口 `P1-4e`
- 完成后立即回到 `P2-4 / P2-5`
- 将更重的 HITL 与 project reuse 作为下一期单独规划
