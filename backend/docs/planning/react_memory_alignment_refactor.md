# ReAct 记忆对齐重构计划（续）

本计划承接 `docs/planning/react_memory_alignment.md`，聚焦剩余落地差距的收束。

## 1) 背景与目标
- 设计目标：单一路径 MAS WorkingMemory + 工具纯执行 + ReAct 解耦，上下文由编排层注入，文件存储与记忆引用解耦。
- 现状：部分模块仍依赖已弃用的 slot/shared_memory_store，导致运行时崩溃或双轨记忆风险；state_view 未注入，规划阶段无法感知全局进度。
- 目标：统一 orchestrator/voice_synthesizer 的记忆写读到 MAS WM，注入 MAS state_view，保持 artifacts 引用与文件存储解耦。

## 2) 问题定位与难点
- Orchestrator 残留 slot 调用：`store_memory_slot` / `fetch_memory_slot` 仍在 `app/agents/orchestrator.py` 使用，BaseAgent 已无该接口，执行会抛错且违背单一记忆路径。
- VoiceSynthesizer 写回错误：`shared_memory_store` 已不存在，voice_assets 写回会崩溃，且未写入 MAS WM。
- state_view 缺失：ReActAgent 每轮上下文调用 `build_agent_context(..., state_view=None)`；编排层/上下文管理层未注入 `build_mas_state_view`，规划缺少全局视图。
- 难点：在不破坏现有 orchestrator 流程（Composer 复入、BGM/voiceover 调度）的前提下替换记忆接口；保持 ReActAgent 调用点不动，外部补齐 state_view。

## 3) 方案与拆解
- Orchestrator 记忆接口统一
  - 初始化/更新 workflow_overview 用 `write_shared_fact(wf_id, "workflow_overview", payload)`。
  - voice_assets 判定改为读取 MAS WM（如 `scene_outputs.voice` 或 `project.voice_assets` facts），不再使用 slot API。
  - 清理 slot 调用与相关错误处理，避免 AttributeError。
- VoiceSynthesizer 写回对齐
  - 移除 `shared_memory_store` 访问，使用 `get_mas_working_memory`/`write_shared_fact` 写 voice_assets，或通过 `persist_scene_outputs(..., kind="voice")` + artifacts 记录。
  - voice_settings 读取/写回同样走 MAS WM，保持 supplier-agnostic 元数据。
- state_view 注入
  - 在 context_manager 或 orchestrator 调用 `build_agent_context` 前构造 `state_view = build_mas_state_view(wf_id)` 并透传，ReActAgent 内部无需改动。
  - 保持 max_turn/预算占位为零侵入，后续按需要再裁剪。
- 生态一致性
  - 更新阶段/规划文档，移除 slot/fact_store 提法，明确 MAS WM 唯一路径与剩余风险。
  - 若有旁白/BGM 相关用例，补充 MAS WM 路径的单测或轻量集成覆盖。

## 4) 行动清单
- P0 功能完整性
  - [x] Orchestrator：替换 `store_memory_slot`/`fetch_memory_slot` 为 MAS WM 读写（workflow_overview、voice_assets 判定）。
  - [x] VoiceSynthesizer：移除 `shared_memory_store`，voice_assets/voice_settings 写入 MAS WM（facts + artifacts）。
- P1 上下文一致性
  - [x] context_manager/orchestrator：调用 `build_mas_state_view` 注入 state_view 后再 `build_agent_context`，验证主要 Agent 规划上下文包含 state_view。
- P2 文档与回归
  - [x] 同步 `docs/stage_processing/stage_3.8_memory_cleanup.md`、`docs/planning/react_memory_alignment.md` 的完成度与剩余风险。
  - [x] 补充 voice_assets 写回的测试覆盖（单测或轻量集成）。

里程碑：先完成 P0 避免运行时错误；P1 解锁上下文一致性；P2 收束文档与验证。***
