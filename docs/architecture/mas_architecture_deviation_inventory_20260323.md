# MAS Architecture Deviation Inventory

日期：2026-03-23

状态：refreshed inventory（2026-03-26 Phase 4 refresh after repaired `026` Phase 3; `024` retained separately）

用途：基于已冻结的 canonical vocabulary，记录当前实现与 `single-episode harness` 四层 MAS 架构之间仍然存在的偏差、受控保留项与清理噪音；本版已吸收 `026` 的最终验证事实，并把此前 review rollback 期间的临时降级结论刷新回与实现一致的可审计状态。

说明：

- 本文不是新的架构定义。
- 本文只使用已冻结的 `编排层 / 控制层 / 门控层 / 治理层` 口径做差距评估。
- 本文当前吸收了 [PLAN-20260326-026.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/archive/2026-03/PLAN-20260326-026.md) 中已经验证完成的事实：Phase 1-4 已全部完成，其中 Phase 3 的 repaired composer contract-authority alignment 已重新验证通过。
- [PLAN-20260325-024.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260325-024.md) 的 project-wrapper host uniformity 仍是独立 retained item；本次刷新不会把它算作 `026` 已完成范围。
- `026` 的治理 closeout 已进入等待用户验收阶段，但本文记录的是实现/治理事实对齐，不替代 plan lifecycle 的最终 `completed` 决策。
- 本文重点区分：
  - 当前主线是否已回正
  - 哪些只是 compat debt
  - 哪些仍会把系统拉回坏架构

相关文档：

- [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md)
- [mas_architecture_alignment_note_20260323.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_alignment_note_20260323.md)
- [mas_runtime_control_plane_detailed_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_control_plane_detailed_design_20260308.md)
- [mas_runtime_contracts_detailed_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_contracts_detailed_design_20260308.md)
- [PLAN-20260326-026.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/archive/2026-03/PLAN-20260326-026.md)
- [PLAN-20260325-024.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260325-024.md)

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

## 2. 当前主线快照（2026-03-26）

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

这个快照说明：当前主问题已不再是“四层没定义”或“single-episode mainline 失守”；`026` 收口后，single-episode 方向上已没有 active residual authority drift，剩余工作主要是 repo-level retained host uniformity 与 controlled-transition 噪音清理。

## 3. 当前偏差清单

| 文件/区域 | 当前实际职责 | canonical 归属 | 判定 | 影响 |
|---|---|---|---|---|
| [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) | single-episode 唯一 MAS mainline；负责编排、runtime decision、leaf activation | 编排层 | `aligned` | 当前主线已固定到 `OrchestratorAgent`。 |
| [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) | 主写 `workflow_session / node / attempt / gate / decision`，生成 runtime read-model | 控制层 | `aligned` | runtime SoT 所有权已清晰，`026` Phase 1 后 GET runtime 读路径也不再 bootstrap session 或 repair default nodes。 |
| [orchestration_control_plane.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_control_plane.py) | gate collection、decision request、apply payload assembly | 控制层中的具体组件 | `mostly-aligned` | 结构已收敛，主要问题是名字仍容易被误读成整个控制层。 |
| [orchestration_runtime_controller.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_runtime_controller.py) | 应用 orchestrator runtime decision，承接 standby activation / abort / continue | 控制层中的具体组件 | `mostly-aligned` | 已承担显式 apply contract，不再像第二条编排器。 |
| [audio_delivery_gate_evaluator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/audio_delivery_gate_evaluator.py) | 读取边界事实并产出 `GateResult` | 门控层 | `mostly-aligned` | gate 逻辑已从 orchestrator 主循环拆出。 |
| [task_queue.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py)、[queued_task_execution_host.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/queued_task_execution_host.py)、[task_execution_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/task_execution_policy.py) | enqueue、worker bootstrap、execution eligibility | external scheduler | `aligned` | queue/container 已与 single-episode runtime semantics 解耦。 |
| [episode_orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/episode_orchestrator.py) | project mode 下的 multi-episode wrapper 协调 | project wrapper | `mostly-aligned` | 当前不再是第二条 single-episode mainline。 |
| [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) | canonical stage-input / execution-boundary assembler | supporting capability | `aligned` | `scene_info_ref` purity、legacy seam retirement、以及 composer contract-authority alignment 均已恢复；assembler 现在只承接显式 contract / boundary projection，不再清洗旧 vocabulary 或让 helper 侧重新拥有 authority。 |
| [memory_views.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py) | read-only context builder / canonical fact projection helper | supporting capability | `aligned` | `video_composer` static context 已改为按 `execution_contract.constraints.compose_mode` 投影输入，旧 `requests` / `has_final` 推断路径已退出 active path；该 helper 只负责事实投影，不再自判 compose/bgm/voiceover 语义。 |
| [published_deliverable_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_adapter.py) | shared-WM deliverable projection bridge | supporting capability | `controlled-transition` | 当前已不是 mainline truth path，但仍保留第二套 boundary protocol 的回退入口。 |
| [execution_boundary_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/execution_boundary_assembler.py) | retired host name compatibility alias | supporting capability | `controlled-transition` | 不再承担主线职责，但保留了旧 vocabulary。 |
| [orchestration_observation_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_observation_adapter.py) | orchestration trace / observation sink | supporting capability | `controlled-transition` | 当前未见 active authority reader，但 `workflow.gates.*` / `workflow.signals.*` 命名仍会模糊 diagnostics 与 gate truth。 |
| [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) | orchestration context persistence、compat diagnostics projection | supporting capability | `mostly-aligned` | 当前已显式禁止写 runtime control prefixes，并把 `plan / activation_pool / audio_route` 压到 diagnostics-only key 下。 |
| [workflow_completion_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/workflow_completion_adapter.py) | bounded terminal summary / result persistence helper | 治理层支撑能力 | `mostly-aligned` | 已明确 `runtime_authoritative=false`，但仍保留少量 legacy terminal vocabulary。 |
| [useWebSocket.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useWebSocket.ts)、[types/index.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/types/index.ts) | websocket event handling / runtime refresh trigger | frontend read-model consumer | `mostly-aligned` | active path 已收敛到 `event.progress` / `event.state` + refresh runtime；旧 business-state websocket vocabulary 已无 active match，剩余 direct transport/system messages 不拥有 authority truth。 |
| [useTaskPolling.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useTaskPolling.ts)、[ProjectModeView.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/project/ProjectModeView.tsx)、[useProjectStore.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/store/useProjectStore.ts) | authority read-model consumers | frontend read-model consumer | `aligned` | 前端主线已停止构建第二套业务状态机。 |
| [projects.py `_schedule_project_plan(...)`](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/projects.py) | project planning 的 endpoint-local thread host | project wrapper / product job host | `out-of-scope-retained` | 它不触碰 single-episode runtime SoT，但说明 whole-system host uniformity 仍未完成；后续治理已拆到 [PLAN-20260325-024.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260325-024.md)。 |
| [mas_state.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/state/mas_state.py) | facts summary / completion summary helper | supporting capability | `aligned` | 当前只消费 canonical `scene_outputs.*` facts，并显式忽略 legacy nested `scene_outputs` bundle；该 helper 已不再承担 compat bridge。 |

## 4. 当前总评

当前代码库的状态不是“MAS 四层架构失败”，而是：

- `single-episode mainline` 已回到正确位置。
- runtime SoT ownership 已固定在控制层，runtime read path purity 也已恢复。
- queue / worker / API 已基本退回 external scheduler。
- scene-info contract purity 与 composer contract-authority alignment 已在 `026` 中收口。
- 前端 authority consumer discipline 已明显改善。

当前 inventory 不再记录 active single-episode residual issue；剩余的是 1 个 repo-level retained item 与一组 controlled-transition 噪音：

1. project-level retained host
   - `project planning` 仍保留单独宿主。
   - 它不是 single-episode blocker，但会影响 whole-system host uniformity；继续由 [PLAN-20260325-024.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260325-024.md) 独立承接。

2. residual compatibility / diagnostics vocabulary noise
   - published deliverable projection / retired host alias / observation naming
   - diagnostics key naming
   - 一些非 authority 的 transport/system 消息仍需保持边界纪律，但已不再构成第二套业务状态机

## 5. 后续梳理顺序

后续若要继续把代码拉回更干净的 MAS 实现，建议按以下顺序：

1. 继续由 `024` 单独收 project wrapper / host uniformity。
2. 再按需要清理 remaining controlled-transition vocabulary / diagnostics noise。

这个顺序的原因是：

- `026` 的 residual purity stream 已完成实现与治理刷新，single-episode mainline 不再有 active residual authority 问题。
- `024` 仍是独立 retained 的 repo-level host 问题，不能伪装成 single-episode 已完成统一。
- compatibility / diagnostics noise 更多是防 future drift 的治理清洁度工作，应排在 retained host uniformity 之后处理。
