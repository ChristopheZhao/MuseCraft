# VideoAgent 两段式 ReAct 改造计划（评估稿）

> 状态：评估已完成；暂不改代码，仅记录明确的改造路径、边界与灰度方案。

## 背景与现状
- 现状：VideoGenerator 采用“一段式”执行路径（在 ACT 内通过 `run_fc_round` 完成“FC 规划+执行”）。
- 对比：Image/Audio/Voice 采用“两段式”路径（PLAN 产出 `planned_tool_calls`，ACT 仅执行计划）。
- 目标：中期统一 ReAct 迭代风格与可观测性，提升计划可见/可审计能力与断点续跑的一致性。

## 设计原则
- ReAct 自主化：OBSERVE → THINK/PLAN → ACT → REFLECT；不在 ACT 阶段做“临时兜底”改判。
- Tools-First：仅通过工具 schema 执行外部 I/O；提示保持 Prompt Neutrality。
- 记忆解耦与单写：产物写入 `artifacts` 时间线；facts 仅兼容回写（按单写开关）。
- 错误透明：仅记录诊断与事实，不在代码里做规则式 if/else 纠偏。

## 目标状态（两段式）
- PLAN：
  - 先用结构化对话产出批次决策（不含工具/参数）。
  - 若 `intent=execute`，再调用一次 FC（`llm_function_call`）产出 `planned_tool_calls`，写入 `iteration_context['planned_tool_calls']`。
  - 记录 `PLAN_DECISION(video): intent, selected_units, planned_calls`（只读日志）。
- ACT：
  - 仅在 `planned_tool_calls` 非空时执行 `execute_tool_calls`。
  - 结果规范化→持久化→写 `artifacts(kind=video, stage=video_only)`；清空 `planned_tool_calls`，避免跨轮污染。
- REFLECT：
  - 合并完成/失败集合，记录摘要；不改判模型决策。

## 迁移阶段（灰度）
- Phase 0（当前）：保持一段式；仅补只读日志（可选）：`PLAN_DECISION(video)`。
- Phase 1（灰度开关）：
  - 新增开关（默认 false）：`VIDEO_AGENT_TWO_STAGE_ENABLED`。
  - 开关开启：走两段式；关闭：保留一段式 `run_fc_round`。
  - 仅在内部/低流量任务开启，观测 planned/executed/quality 指标。
- Phase 2（收敛）：
  - 两段式稳定后默认开启；保留回退开关一段时间。

## 代码变更点（暂不实施，仅标注）
- `backend/app/agents/video_generator.py`
  - PLAN：`_think_and_plan` 路由到 `_request_planning_decision` 后，若 intent=execute，则追加 `llm_function_call` 产 `planned_tool_calls` 并入 `iteration_context`（新增）。
  - ACT：将 `run_fc_round` 替换为 `execute_tool_calls(validated_calls)`（或按开关二选一）；复用现有规范化与持久化路径。
  - 日志：`PLAN_DECISION(video)` 与 `ACT_DIAG(video)`（与 image 对齐）。

## 风险与回退
- 额外 LLM 回合：PLAN 额外一次 FC 计划调用，时延/成本小幅增加（相对视频生成可接受）。
- 工具 schema 约束需充分：两段式依赖 `video_generation.*` 参数校验清晰，否则会出现 `intent=execute` 但 `planned_tool_calls` 为空的情况（视为规划失败，显性记录，不降级）。
- 回退：开关关闭即回到一段式，代码路径简单清晰。

## 验收标准
- intent=observe/replan 回合不执行工具（executed=0），进入 REFLECT；无“硬切换为执行”。
- intent=execute 且 planned_tool_calls>0 → 正常执行并写入 `artifacts(video/video_only)`。
- “应执行但无计划”场景仅记录诊断，下一轮由 ReAct 自主纠偏；无静默降级。

## 观测与指标（只读）
- 日志：
  - `PLAN_DECISION(video): intent=…, selected=…, planned_calls=N`
  - `ACT_DIAG(video): planned=… executed=… success=…`
- 指标（可选）：
  - 计划一致性：`execute` 回合中 planned/executed 匹配度。
  - 质量与用时：两段式 vs 一段式 的成功率/耗时/成本对比。

## 测试清单（实施时）
- 单元测试：
  - intent=observe → ACT 不执行（executed_calls==[]）。
  - intent=execute + planned_tool_calls 非空 → 执行并规范化持久化。
  - intent=execute + planned_tool_calls 为空 → 显性诊断；不降级。
- 集成测试：
  - 单/多场景；含/不含前置提示生成；断点续跑与 artifacts 时间线验证。

## 时间预估
- 代码改造与单测：~0.5–1.5 天。
- 灰度观测与回收：~1–3 天（依据任务量）。

> 备注：本评估稿不修改任何执行路径；仅在 `docs/URGENT` 记录方案，方便后续按计划推进或取消。

