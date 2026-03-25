# MAS Architecture Deviation Inventory

日期：2026-03-23

状态：working inventory

用途：基于已对齐的 canonical vocabulary，汇总当前实现与 `single-episode harness` 四层 MAS 架构之间的主要偏差、越层点和过渡态残留，供后续讨论与治理使用。

说明：

- 本文不是新的架构定义。
- 本文只使用已冻结的 canonical vocabulary 做差距评估。
- 本文中的“偏差”既包括明确越层，也包括已知过渡态与语义噪音源。

相关文档：

- [mas_architecture_alignment_note_20260323.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_alignment_note_20260323.md)
- [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md)
- [mas_runtime_control_plane_detailed_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_control_plane_detailed_design_20260308.md)
- [mas_runtime_contracts_detailed_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_contracts_detailed_design_20260308.md)

## 1. 判定口径

- `aligned`
  - 当前实现与 canonical 归属基本一致，没有发现同层级明显偏差。
- `mostly-aligned`
  - 主体归属已基本正确，但仍有局部实现形态容易引起误解，或边界尚未完全收口。
- `explicit-cross-layer`
  - 当前实现明确承担了不应由该层承担的职责，属于显式越层。
- `transitional`
  - 当前实现可解释为过渡态，不一定立即错误，但仍保留兼容桥接、旧宿主残留或第二套语义噪音。

## 2. 当前偏差清单

| 文件/位置 | 当前实际职责 | canonical 归属 | 判定 | 备注 |
|---|---|---|---|---|
| [workflow_runtime.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/models/workflow_runtime.py) | runtime substrate models | 控制层底座 | `aligned` | 当前角色清晰。 |
| [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) | 主写 `workflow_session / node / attempt / gate / decision`，处理 `approve / revise / replan / resume` 等状态推进 | 控制层 | `aligned` | 这条主线已基本立住。 |
| [published_deliverable_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_service.py) | deliverable payload 落盘、record/ref 持久化、payload 读取 | supporting capability：边界输出 / persistence | `aligned` | 已基本退回 persistence-only。 |
| [orchestration_control_plane.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_control_plane.py) | boundary-triggered gate collection、decision request、apply payload assembly | 控制层中的具体组件 | `mostly-aligned` | 主体归属正确，但名字仍易被误读成“整个控制层”。 |
| [orchestration_runtime_controller.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_runtime_controller.py) | 控制层 apply、runtime activation、standby 激活 | 控制层中的具体组件 | `mostly-aligned` | 归属正确，但仍与 activation policy 之间存在灰区。 |
| [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) | 兼容投影写入、execution queue / standby 构造、activation_pool 投影 | supporting capability：兼容投影 / 过渡桥接 | `transitional` | 仍承载活语义，不只是纯诊断投影。 |
| [orchestrator.py:379](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L379) `_open_script_review_gate(...)` | 同时做 deliverable publish、runtime payload 写回、shared WM 投影、gate open | 应拆到控制层 + supporting capability | `explicit-cross-layer` | 这是当前最清晰的编排层 residual ownership。 |
| [orchestrator.py:1863](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1863) | 编排层按 `AUDIO_GENERATOR` 直接挑 `build_media_agent_context(...)` | supporting capability：Context/Contract Assembler | `explicit-cross-layer` | 编排层仍直接做 stage-input builder routing。 |
| [orchestrator.py:1935](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1935) | 编排层按 `IMAGE_GENERATOR` 直接挑 `build_image_generation_context(...)` | supporting capability：Context/Contract Assembler | `explicit-cross-layer` | 虽然 image 已吃正式输入，但 builder 选择仍在编排层。 |
| [orchestrator.py:1970](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1970) | 编排层按 `VIDEO_GENERATOR` 直接挑 `build_video_generation_context(...)` | supporting capability：Context/Contract Assembler | `explicit-cross-layer` | 同上。 |
| [orchestrator.py:2023](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L2023) | 编排层按 `VOICE_SYNTHESIZER` 直接挑 `build_voice_synthesis_context(...)` | supporting capability：Context/Contract Assembler | `explicit-cross-layer` | 同上。 |
| [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) | 旧式 guidance / continuity assembler | supporting capability：Context/Contract Assembler | `transitional` | 当前宿主仍不是正式的 stage-input / execution-contract assembler。 |
| [memory_views.py:164](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py#L164) `build_media_agent_context(...)` | live WM 驱动的 media context 组装 | supporting capability：projection / Context Assembler | `transitional` | 仍以 live WM 为主。 |
| [memory_views.py:426](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py#L426) `build_image_generation_context(...)` | published-deliverable-backed image formal input projection | supporting capability：projection / Context Assembler | `mostly-aligned` | 已进入正式输入模型，但仍是 per-path builder。 |
| [memory_views.py:512](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py#L512) `build_video_generation_context(...)` | published-deliverable-backed video formal input projection | supporting capability：projection / Context Assembler | `mostly-aligned` | 同上。 |
| [memory_views.py:693](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py#L693) `build_voice_synthesis_context(...)` | voice synthesis context 仍主要读 live WM | supporting capability：projection / Context Assembler | `transitional` | 仍未与 image/video 收敛到同一 stage-boundary 模型。 |
| [published_deliverable_adapter.py:96](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/published_deliverable_adapter.py#L96) | deliverable ref / payload 投影回 shared WM | supporting capability：边界输出投影 / bridge | `transitional` | 当前仍是 runtime binding 与 downstream consumption 之间的桥接层。 |
| [orchestrator.py:643](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L643) | 从 runtime payload 取 ref，再投影回 shared WM，供 downstream 回读 | 控制层绑定 + supporting capability 投影的过渡实现 | `transitional` | stage-input resolution 仍未成为显式 harness 能力。 |
| [orchestration_state_adapter.py:132](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py#L132) | 持续写 `workflow.plan`、`workflow.activation_pool` | supporting capability：兼容投影 / 诊断投影 | `transitional` | 兼容投影仍参与活跃状态链。 |
| [orchestration_state_adapter.py:326](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py#L326) | 持续写 `workflow.audio_route` | supporting capability：兼容投影 / 诊断投影 | `transitional` | 兼容投影仍未完全退场。 |
| [orchestrator.py:1401](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1401) `get_workflow_status(...)` | 回读 `workflow.activation_pool` 组装步骤状态 | 应优先消费控制层 read model | `transitional` | 说明 compatibility seam 仍在 active status path 里。 |
| [orchestration_state_adapter.py:171](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py#L171) / [orchestration_state_adapter.py:198](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py#L198) / [orchestration_state_adapter.py:214](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py#L214) | execution queue / standby / insertion policy 组装 | 编排层策略 + 控制层 apply 之间的边界灰区 | `transitional` | 不是已确认错误，但容易继续制造语义漂移。 |
| human review path in [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) 与 boundary-triggered system gate path in [orchestration_control_plane.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_control_plane.py) | 两种 gate handling 风格并存 | 门控层产出、控制层消费 | `transitional` | 语义可解释，但实现形态还没完全统一。 |
| `script_stage_runner.py` / `post_script_stage_runner.py`（已于 2026-03-25 从 `backend/app` / `backend/tests` 退役） | 旧备用 stage runner mainline 已退出活跃 app/test surface | 不应继续作为主线候选语义存在 | `mostly-aligned` | D2 第一刀已清除此类 dormant mainline 噪音。 |
| [episode_orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/episode_orchestrator.py) | 当前主要承担 project / multi-episode wrapper 协调 | 编排层外层包装 / project wrapper | `mostly-aligned` | D1 已移除 project-foundation mini-host 与旧宿主语义；剩余工作转入 Checkpoint D / final closeout audit。 |
| `workflow_manager.create_workflow()` project-foundation path（已于 2026-03-25 从 `EpisodeOrchestratorAgent` 退役） | 旧 `WorkflowState` 宿主残留已退出活跃 wrapper 路径 | 历史 `WorkflowState` 宿主残留 | `mostly-aligned` | 当前 app mainline 不再通过该路径构造 project foundation workflow。 |
| `react_orchestrator.py` / `enhanced_orchestrator.py` / `testing_framework.py`（已于 2026-03-25 从 `backend/app` / `backend/tests` 退役） | 并行 orchestrator 变体已退出活跃 app/test surface；仓库仅剩少量历史文档引用 | 历史实现 / 语义噪音源 | `mostly-aligned` | D2 第二刀已删除实现、绑定 prompt assets 与 legacy tests；剩余工作只是在 final closeout 中说明历史文档归档方式。 |

## 3. 补充观察

- 当前没有再看到 queue/worker 重新回流为 MAS runtime SoT owner 的新证据；`queue/runtime` 主边界仍保持在 `012/014/015` 之后的收口状态。
- 当前也没有再看到 leaf agents 继续直接以 `workflow.plan / workflow.audio_route / workflow.activation_pool` 作为活跃输入真值的明确证据。
- 当前偏差主要集中在：
  - `OrchestratorAgent` 的 residual ownership
  - `Context/Contract Assembler` 宿主缺位
  - compatibility seam 仍在 active path 存活
  - 少量历史文档仍保留已退役 orchestrator 名称，需要在 final closeout 中说明归档口径

## 4. 当前总评

按已对齐的 canonical vocabulary 评估，当前代码库的状态不是“整体违背 MAS 架构”，而是：

- 控制层 runtime SoT 主写已经基本立住；
- 边界输出 persistence 也已基本回到正确位置；
- 但编排层 residual ownership 仍未清干净；
- supporting capability，尤其 `Context/Contract Assembler`，还没有正式落位；
- active path 的主要偏差已显著收敛；剩余噪音主要来自少量历史文档与 final closeout 尚未完成的说明工作。

因此，当前的主问题已经从“术语没对齐”转成“术语已对齐，但实现仍保留若干过渡态与越层残余”。
