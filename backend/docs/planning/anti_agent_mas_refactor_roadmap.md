# 反 Agent 设计治理路线图（MAS 协作与通信）

状态：Draft  
日期：2026-03-01  
范围：`backend/app/agents/*`、`backend/app/agents/tools/*`、`backend/app/events/*`、`backend/app/core/*`

## 1. 目标

本路线图只做一件事：把“编排决策权”收敛回 orchestrator，并把门控规则收敛为执行安全边界。

目标拆解：

1. 决策单源化：音频/视频相关路由由 orchestrator 单点产出并写入 MAS SoT。
2. 通信契约强化：跨工具链路不再把根因错误降级成“empty payload”。
3. 分层清晰化：工具层执行化，避免工具内部继续承载编排策略。
4. 可演进化：从固定队列平滑演进到 activation pool，再过渡到 agenda。

## 2. 约束与原则

1. 保留必要 hard gate：`quality_checker` 前置条件、provider 不可用 fail-fast、FC schema 校验。
2. 不引入新的“强规则模式”（例如 `native_strict` 这类规则位）。
3. 兜底仅用于异常恢复事件，不作为常规 `else` 主路径。
4. 默认供应商能力稳定，主路径使用前验能力路由，不用后验探测主导编排。

## 3. 问题到改造项映射

| 问题 | 根因 | 对应改造阶段 |
|---|---|---|
| 固定队列 + 运行时跳过 | 决策前置不足 | P1 |
| 音频策略三层重复 | 决策权分散 | P1 + P2 |
| 条件任务全局硬要求 | 计划自治受限 | P1 |
| 工具错误语义丢失 | 通信契约弱化 | P0 |
| 工具层迷你编排 | 分层边界不清 | P2 |
| 动态编排能力不足 | 调度模型限制 | P3 |

## 4. P0（优先级最高）：通信契约与可观测性修复

目标：不改主业务策略，先修“错误语义丢失”和“诊断不可见”。

## P0-1 工具包装链路强制检查 `ToolOutput.success`

问题点：

- 上层包装工具直接读取 `.result`，失败时根因被覆盖为“empty payload”。

修改文件：

1. `backend/app/agents/tools/image_prompt_composer_tool.py`
2. `backend/app/agents/tools/video_prompt_composer_tool.py`
3. `backend/app/agents/tools/ai_services/voice_synth_tool.py`

改造方式：

1. 统一先判 `tool_output.success`。
2. `success=False` 时透传 `error` 与 `metadata.error_type`，不得改写为“空 payload”。
3. 保留原始工具名与 action，便于跨层追踪。

验收标准：

1. provider 不可用场景下，日志和上层错误可见原始 `error_type`。
2. 不再出现“根因失败 -> 上层 empty payload”的掩盖链路。

## P0-2 启动期 provider 注册矩阵诊断

问题点：

- provider 缺配置直到运行期才报错，定位成本高。

修改文件：

1. `backend/app/agents/tools/ai_services/service_interfaces.py`

改造方式：

1. 在服务初始化完成后打印 provider 注册矩阵（LLM/VLM/Video）。
2. 明确输出缺失关键字段（例如 `DOUBAO_IMAGE_MODEL`）。
3. 仅诊断，不自动降级行为。

验收标准：

1. 启动日志可直接判断每类 provider 是否可用。
2. 运行前即可识别 `VLM Provider ... not available` 风险。

## P0-3 决策链路统一观测字段

修改文件：

1. `backend/app/agents/orchestrator.py`
2. `backend/app/events/publisher.py`

改造方式：

1. 对音频路由决策输出统一结构化日志字段：`route_source/route_id/decision_reason`。
2. 关键 gate 决策附带 `workflow_state_id` 与 `execution_id`。

验收标准：

1. 任一步骤可通过日志重建“为何执行/跳过”的决策链。

## 5. P1：决策单源化 + Activation Pool（核心阶段）

目标：把“谁该执行”从运行时门控前移到编排前。

## P1-1 引入 `audio_route` 与 `activation_pool` 事实

修改文件：

1. `backend/app/agents/orchestrator.py`
2. `backend/app/agents/adapters/state/`（新增 route resolver）
3. `backend/app/core/video_config_manager.py`（复用能力契约）

改造方式：

1. 编排起始阶段计算 `workflow.audio_route`。
2. 基于 route 生成 `workflow.activation_pool`（不是 FIFO 队列）。
3. 主循环执行集合来自 activation pool，`workflow_order` 仅作为排序模板。

验收标准：

1. 已知 provider 原生音频能力场景下，`AUDIO_GENERATOR` 默认不进入激活池。
2. 不依赖后验音轨探测决定主路径是否编排 audio agent。

## P1-2 条件任务按 route 必需化，不做全局硬要求

修改文件：

1. `backend/app/agents/orchestrator.py`

改造方式：

1. 去除 `video_composer_bgm_mix` 全局必选逻辑。
2. 改为 `route.required_conditional_tasks` 驱动的必需校验。

验收标准：

1. route 不需要 BGM 时，缺少 `video_composer_bgm_mix` 不失败。
2. route 需要 BGM 时，缺失则 fail-fast。

## P1-3 `_should_run_agent` 收敛为硬保障

修改文件：

1. `backend/app/agents/orchestrator.py`

改造方式：

1. `_should_run_agent` 仅保留硬前置条件校验（如数据完整性）。
2. 业务编排选择权移交 route + activation pool。

验收标准：

1. 不再通过多条业务 gate 叠加“模拟编排”。

## 6. P2：工具层去策略化（执行层归位）

目标：工具只执行 orchestrator 下发决策，不再自行解释全局策略。

## P2-1 视频工具去全局策略解释

修改文件：

1. `backend/app/agents/tools/ai_services/video_generation_tool_v2.py`

改造方式：

1. `generate_audio` 由调用参数显式传入。
2. 工具仅做 provider capability 合法化（不支持则 fail-fast 或显式关闭并返回诊断）。
3. 不再在工具内读取 `VIDEO_AUDIO_STRATEGY` 作为编排决策来源。

验收标准：

1. 同一输入参数在不同运行上下文结果一致。
2. 工具不再承担编排层策略分流。

## P2-2 合成工具去全局策略解释

修改文件：

1. `backend/app/agents/tools/video_composition/composition_tool.py`

改造方式：

1. `preserve_audio` 优先显式参数。
2. 不再以 `VIDEO_AUDIO_STRATEGY` 作为主分流逻辑。
3. 探测逻辑仅用于执行安全检查，不做业务路径决策。

验收标准：

1. 合成行为可由上层 route 参数稳定控制。

## P2-3 Orchestrator 显式传递执行意图

修改文件：

1. `backend/app/agents/orchestrator.py`
2. `backend/app/agents/adapters/memory_views.py`（必要时补字段）

改造方式：

1. route 结果显式注入 `task/static_context`。
2. 下游工具全部消费显式意图字段。

验收标准：

1. 从日志可验证“orchestrator decision -> tool parameter”一跳直达。

## 7. P3（后续）：从 Activation Pool 到 Agenda

本阶段不在当前改造窗口内，沿用现有 follow-up 文档：

- [orchestrator_queue_to_agenda_followup.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/docs/planning/orchestrator_queue_to_agenda_followup.md)

目标是把“执行顺序模板”升级为“任务意图驱动调度”。

## 8. 测试与回归计划

## 单元测试

新增建议：

1. route resolver：能力与需求矩阵覆盖。
2. orchestrator activation pool：不同 provider 能力下激活集合断言。
3. conditional tasks gate：按 route 必需项断言。
4. tool wrapper error passthrough：`success=false` 时根因透传。

## 集成测试

场景矩阵：

1. provider 原生音频可用 + 需求普通：不编排 audio agent。
2. provider 原生音频可用 + 明确需要独立音频能力：按 route 编排。
3. provider 无原生音频：编排 audio agent。
4. provider 配置缺失：启动期可见诊断 + 运行期 fail-fast。

## 9. 成功判据（Done Definition）

1. 音频编排决策只在 orchestrator 产生一次并写 MAS SoT。
2. `AUDIO_GENERATOR` 是否执行由 activation pool 决定，不依赖运行时后验探测主导。
3. 工具层不再读取全局编排策略做本地分流。
4. 跨工具调用链路保留原始错误语义，不再被“empty payload”覆盖。
5. 关键 hard gate 仍保留且可观测。

## 10. 风险与回滚

主要风险：

1. 路由迁移初期可能出现激活池误判。
2. 工具去策略化后，部分历史调用缺少显式参数。

缓解方案：

1. 先落 P0 可观测性，确保决策链可追踪再推进 P1/P2。
2. 迁移期将“缺少显式参数”视为可观测告警并逐步收敛到硬约束。
3. 分阶段发布，每阶段通过单元与集成矩阵后再推进下一阶段。
