# MAS Architecture Deviation Inventory

日期：2026-03-23

状态：working inventory（2026-03-26 refreshed）

用途：基于已冻结的 canonical vocabulary，记录当前实现与 `single-episode harness` 四层 MAS 架构之间仍然存在的偏差、受控保留项与清理噪音。

说明：

- 本文不是新的架构定义。
- 本文只使用已冻结的 `编排层 / 控制层 / 门控层 / 治理层` 口径做差距评估。
- 本文重点区分：
  - 当前主线是否已回正
  - 哪些只是 compat debt
  - 哪些仍会把系统拉回坏架构

相关文档：

- [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md)
- [mas_architecture_alignment_note_20260323.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_alignment_note_20260323.md)
- [mas_runtime_control_plane_detailed_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_control_plane_detailed_design_20260308.md)
- [mas_runtime_contracts_detailed_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_contracts_detailed_design_20260308.md)

## 1. 判定口径

- `aligned`
  - 当前实现与 canonical 归属一致，没有发现会误导后续治理的明显偏差。
- `mostly-aligned`
  - 主体归属已正确，但仍保留局部实现噪音或少量低风险 compat 形态。
- `controlled-transition`
  - 当前不属于 active mainline blocker，但仍保留 compat bridge、legacy vocabulary 或 future drift 入口。
- `active-governance-risk`
  - 当前已落在 active path 上，会削弱 contract-first normalization、single-mainline clarity 或 authority boundary。
- `out-of-scope-retained`
  - 当前被明确排除在 `single-episode harness` 治理闭环之外的保留项；不算主线 blocker，但必须被清楚标注，避免误判为已完成统一。

## 2. 当前主线快照（2026-03-25）

按当前代码宿主理解：

- 编排层：
  - `OrchestratorAgent`
- 控制层：
  - `RuntimeSessionService`
  - `OrchestrationRuntimeController`
  - `OrchestrationControlPlane`
  - runtime substrate models
- 门控层：
  - system gate evaluators
  - human review gates consumed by control-plane
- 治理层：
  - contract vocabulary
  - diagnostics / quality / closeout rule set
  - bounded terminal summary publication
- project wrapper：
  - `EpisodeOrchestratorAgent`
  - `projects.py`
  - project state / progress services
- external scheduler：
  - task queue / worker host / API enqueue entrypoints
- supporting capabilities：
  - `ContextContractAssembler`
  - published deliverable projection / adapter
  - observation / trace adapters
  - read-only memory view builders
- leaf agents：
  - concept / script / voice / image / video / audio / composer / quality agents

这个快照说明：当前主问题已不再是“四层没定义”，而是“少量 supporting capability 和 project wrapper 还没完全收干净”。

## 3. 当前偏差清单

| 文件/区域 | 当前实际职责 | canonical 归属 | 判定 | 影响 |
|---|---|---|---|---|
| [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) | single-episode 唯一 MAS mainline；负责编排、runtime decision、leaf activation | 编排层 | `aligned` | 当前主线已固定到 `OrchestratorAgent`。 |
| [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) | 主写 `workflow_session / node / attempt / gate / decision`，生成 runtime read-model | 控制层 | `aligned` | runtime SoT 所有权已清晰。 |
| [orchestration_control_plane.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_control_plane.py) | gate collection、decision request、apply payload assembly | 控制层中的具体组件 | `mostly-aligned` | 结构已收敛，主要问题是名字仍容易被误读成整个控制层。 |
| [orchestration_runtime_controller.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_runtime_controller.py) | 应用 orchestrator runtime decision，承接 standby activation / abort / continue | 控制层中的具体组件 | `mostly-aligned` | 已承担显式 apply contract，不再像第二条编排器。 |
| [audio_delivery_gate_evaluator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/audio_delivery_gate_evaluator.py) | 读取边界事实并产出 `GateResult` | 门控层 | `mostly-aligned` | gate 逻辑已从 orchestrator 主循环拆出。 |
| [task_queue.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py)、[queued_task_execution_host.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/queued_task_execution_host.py)、[task_execution_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/task_execution_policy.py) | enqueue、worker bootstrap、execution eligibility | external scheduler | `aligned` | queue/container 已与 single-episode runtime semantics 解耦。 |
| [episode_orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/episode_orchestrator.py) | project mode 下的 multi-episode wrapper 协调 | project wrapper | `mostly-aligned` | 当前不再是第二条 single-episode mainline。 |
| [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) | canonical stage-input / execution-boundary assembler | supporting capability | `mostly-aligned` | 当前主路径已通过它组装 runtime carrier、`runtime_hints` 和 `ExecutionContract`，但仍保留少量 compat helper。 |
| [memory_views.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py) | read-only context builder / legacy WM loader | supporting capability | `active-governance-risk` | active path 中仍存在 consumer-side fail-open，尤其 `video_composer` 上下文会在 project facts 缺席时回退读 legacy `scene_outputs` bundle。 |
| [published_deliverable_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_adapter.py) | shared-WM deliverable projection bridge | supporting capability | `controlled-transition` | 当前已不是 mainline truth path，但仍保留第二套 boundary protocol 的回退入口。 |
| [execution_boundary_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/execution_boundary_assembler.py) | retired host name compatibility alias | supporting capability | `controlled-transition` | 不再承担主线职责，但保留了旧 vocabulary。 |
| [orchestration_observation_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_observation_adapter.py) | orchestration trace / observation sink | supporting capability | `controlled-transition` | 当前未见 active authority reader，但 `workflow.gates.*` / `workflow.signals.*` 命名仍会模糊 diagnostics 与 gate truth。 |
| [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) | orchestration context persistence、compat diagnostics projection | supporting capability | `mostly-aligned` | 当前已显式禁止写 runtime control prefixes，并把 `plan / activation_pool / audio_route` 压到 diagnostics-only key 下。 |
| [workflow_completion_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/workflow_completion_adapter.py) | bounded terminal summary / result persistence helper | 治理层支撑能力 | `mostly-aligned` | 已明确 `runtime_authoritative=false`，但仍保留少量 legacy terminal vocabulary。 |
| [useWebSocket.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useWebSocket.ts)、[types/index.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/types/index.ts) | websocket event handling / legacy direct message vocabulary | frontend read-model consumer | `controlled-transition` | 当前主线已走 `event.* + refresh runtime`，但 legacy vocabulary 仍保留 future drift 入口。 |
| [useTaskPolling.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useTaskPolling.ts)、[ProjectModeView.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/project/ProjectModeView.tsx)、[useProjectStore.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/store/useProjectStore.ts) | authority read-model consumers | frontend read-model consumer | `aligned` | 前端主线已停止构建第二套业务状态机。 |
| [projects.py `_schedule_project_plan(...)`](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/projects.py) | project planning 的 endpoint-local thread host | project wrapper / product job host | `out-of-scope-retained` | 它不触碰 single-episode runtime SoT，但说明 whole-system host uniformity 仍未完成；后续治理已拆到 [PLAN-20260325-024.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260325-024.md)。 |
| [mas_state.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/state/mas_state.py) | facts summary / completion summary helper | supporting capability | `aligned` | 当前只消费 canonical `scene_outputs.*` facts，并显式忽略 legacy nested `scene_outputs` bundle；该 helper 已不再承担 compat bridge。 |

## 4. 当前总评

当前代码库的状态不是“MAS 四层架构失败”，而是：

- `single-episode mainline` 已基本拉回正确位置。
- runtime SoT ownership 已基本固定在控制层。
- queue / worker / API 已基本退回 external scheduler。
- 前端 authority consumer discipline 已明显改善。

真正还没收干净的问题主要有 3 类：

1. active-path fail-open
   - supporting capability 仍在消费点补边界。
   - 当前最值得优先清理的是 `memory_views.py` 中的 legacy fallback。

2. project-level retained host
   - `project planning` 仍保留单独宿主。
   - 它不是 single-episode blocker，但会影响 whole-system host uniformity。

3. residual compatibility / diagnostics vocabulary noise
   - legacy websocket vocabulary
   - diagnostics key naming

## 5. 后续梳理顺序

后续若要继续把代码拉回更干净的 MAS 实现，建议按以下顺序：

1. 先消 active-path fail-open。
2. 再收 project wrapper / host uniformity。
3. 再清 remaining compatibility vocabulary / diagnostics noise。

这个顺序的原因是：

- 前两项直接影响架构边界。
- 后两项更多是防 future drift 的治理清洁度工作。
