# ReAct 记忆架构对齐方案

## 目标设计（应有状态）
- **记忆分层**：短期 = WorkingMemory（agent_scope / MAS scope）；长期首先聚焦 episodic memory（持久化 {act, obs} + 可选 thought 摘要），后续再扩展语义记忆。
- **协作维度**：MAS 级共享 facts/scene_outputs/state views；Agent 级作为本 Agent 的工作区与 obs_records，仅在生命周期内有效。
- **架构分层**：基础实现 → 抽象接口/适配器/上下文管理 → 应用层（Agent/工具/编排）。Agent 通过 context builder + 写回 helper 与记忆交互。
- **状态视图（SoT 观测）**：基于 MAS WM facts/scene_outputs/workflow_overview 构建的视图，仅作进度/上下文输入，不是“唯一入口”。
- **上下文构建**：由编排/context manager 在 Agent 外完成（可用/扩展 `build_agent_context`），聚合 agent_scope WM + 领域适配（scene_overview/scripts/roles 等来自 MAS WM）+ 可选状态视图。
- **OBS 职责**：只处理本轮 ACT→OBS 的即时观察/轻量校验，不拼装上下文；通过 `append_obs_to_wm` 写入 agent_scope WM。
- **写回**：工具产物/事实经 `persist_scene_outputs` / `write_shared_fact` 落 MAS WM；状态视图用 `build_mas_state_view`，Agent 级视图按需补充。
- **工具原则**：纯执行，不读写 MAS/shared_wm；调用方负责写回。
- **治理原则**：存在≠合理。与设计不符的遗留（shared_wm/fact_store/slot、Agent 内上下文拼装等）应清理，评估的只是迁移风险与应对策略。

## 进度概览
- ✅ 入口/工具/持久化已迁移到 MAS WM：orchestrator/base 写回、scene_continuity_preparation_tool 与 video_generation_tool_v2 纯输出，snapshots/persistence 读取 MAS WM。
- ✅ OBS 拆分：生产 Agent 移除 `_observe_current_state`，`_observe` 统一返回 obs_record（iteration + action_result，3000 token 限制），上下文与 OBS 解耦。
- ✅ 测试迁移：集成/端到端/单测中的 `get_shared_wm` 已替换为 MAS WorkingMemory（归档代码除外）。
- ✅ Slot 退役：WorkingMemory slot API 移除，slot registry 单测删除，WorkingMemoryService 不再暴露 `sync_to_slots`，workflow backend 改为简单 dict backend；短期存储抽象（ShortTermMemoryStore + 内存后端）可替换注入。
- ⚠️ 上下文外移：现阶段接受 Agent 内 `build_agent_context`，编排层统一注入留待后续。
- ⚠️ 文档部分仍提及旧 shared_wm 路径（stage_3.8 等需刷新）。

## 当前偏差/问题
- **上下文分层部分未外移**：ReActAgent 仍在内部调用 `build_agent_context`，但已支持注入 MAS state_view；编排层可进一步接管上下文构建与裁剪策略。
- **文档滞后**：规划/阶段文档需持续刷新，剔除 shared_wm/fact_store/slot 旧描述，补充 voice_assets/MAS state_view 的迁移现状。

## OBS 迁移指导（针对曾经覆盖 `_observe_current_state` 的 Agent）
- 目标：OBS 只产出当轮 obs_record，不拼历史/上下文，不混入 plan/context。
- 实施步骤：
  - 将自定义 `_observe_current_state` 移除；如需当轮检查，在 `_observe` 内最小化处理并返回 obs_record。
  - obs_record 结构：`{"iteration": n, "action_result": <截断后>}`，仅对 action_result 做 3000 token 限制；默认不做内容精简（可留配置开关）。
  - 循环层统一调用 `_observe` → `append_obs_to_wm` 写入 agent_scope WM；产物/事实写 MAS WM 仍用现有 helper。
  - 领域上下文由编排/context manager 注入（scene_overview/scripts/roles 等），禁止再在 OBS 内拼装。

## 修复思路
- shared_wm 清理：保持 MAS WM 单一路径，删除缺失的 `mas_shared_memory.py` 依赖；归档模块保留但不在生产路径使用。
- 工具纯执行：工具只返回产物/分析结果，由调用方写回 MAS WM。
- 持久化/快照：基于 MAS WM facts/scene_outputs 构建 snapshots 与数据库持久化。
- 上下文外移：编排层负责每轮上下文构建/注入（可复用 `context_manager.build_agent_context`），Agent 内不再自组上下文。
- Slot 退役：删除 WorkingMemory slot API、memory_slots.yaml、SlotRegistry 单测，移除 `sync_to_slots` 选项。
- 状态视图：按需在上下文构建时合并 `build_mas_state_view` 输出，避免在工具/Agent 内自行拼装。

## 行动清单
1) 入口/导入修复（P0）  
   - [x] 移除/替换 orchestrator/base 中的 shared_wm 依赖，使用 MAS WM helper 读写 artifacts/overview。  
2) 工具清理（P0）  
   - [x] `scene_continuity_preparation_tool.py` 去掉 shared_wm 回落，保持纯执行输出。  
   - [x] `video_generation_tool_v2.py` 去掉 shared_wm 读取（出度/last_frame），改为入参或 MAS facts 注入。  
3) 持久化/快照（P0）  
   - [x] `memory/long_term/snapshots.py` 改为 MAS WM facts/scene_outputs。  
   - [x] `services/data_persistence.py` 改造为 MAS WM 适配，调用方同步更新。  
4) 上下文/OBS（P1）  
   - [ ] 每轮上下文由编排层/context manager 构建并注入，Agent 内不再组装。  
   - [x] `_observe` 返回精简 obs_record（仅 action_result 3000 token 限制），统一 `append_obs_to_wm` 写入。  
   - [x] 移除 Agent 自定义 `_observe_current_state`，OBS 只做当轮轻量观察（归档代码除外）。  
5) slot/fact_store 退役（P2）  
   - [x] 删除 WorkingMemory slot API、memory_slots.yaml、SlotRegistry 单测；移除 `sync_to_slots`，workflow backend 改为 dict；短期存储抽象层引入（ShortTermMemoryStore + 内存默认实现，可替换为其他后端）。  
6) 测试/文档（P1）  
   - [x] 替换测试中的 `get_shared_wm` 依赖为 MAS WM fixture。  
   - [ ] 更新 `stage_3.8_memory_cleanup.md` 等文档记录迁移完成项与剩余风险。  
