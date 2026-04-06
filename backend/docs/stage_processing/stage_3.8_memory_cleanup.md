## Stage 3.8 — 共享记忆去耦与slot清理（进行中）

### 已完成
- **Agent 路径迁移到 MAS WM**
  - `script_writer`：上下文/写回改用 MAS WorkingMemory facts（`project.concept_plan`/`project.voice_plan`/`scene_overview`/`scene_scripts`），去除 shared_wm 和 slot 写入。
  - `concept_planner`：写回 MAS WM facts（concept_plan、voice_plan、scene_overview），不再使用 shared_wm。
  - `video_composer`：上下文和资产读取改用 MAS WM facts/scene_outputs，移除 shared_wm/fact_store 访问。
  - `quality_checker`：上下文/最终视频信息来源改为 MAS WM facts 和 `scene_overview`，移除 shared_wm。
  - `audio_generator`：移除 shared_wm import（保持 MAS WM 读取）。
- **工具/入口/持久化迁移**
  - BaseAgent 写 artifact、Orchestrator workflow_overview、DataPersistenceService、snapshots 全部改为 MAS WM 路径。
  - 工具层 `scene_continuity_preparation_tool.py`、`video_generation_tool_v2.py` 去掉 shared_wm 读写，保持纯执行输出。
- **OBS 精简**
  - ReActAgent `_observe` 统一返回 obs_record（iteration + action_result，3000 token 限制），去掉生产 Agent 中的 `_observe_current_state`。
- **测试迁移**
  - 集成/端到端/单测替换 `get_shared_wm` 为 MAS WorkingMemory（归档代码保留）。
- **短期存储抽象**
  - 引入 `ShortTermMemoryStore` 接口 + 默认内存后端，可通过 `short_term_store_factory` 注入其他实现；WorkingMemory/Service 仅依赖接口。
- **Slot 退役（部分完成）**
  - WorkingMemory slot API 移除，`sync_to_slots` 入口删除，workflow backend 改为轻量 dict 后端；SlotRegistry 单测删除。
- **基础层瘦身**
  - BaseAgent 去掉 shared_wm wiring，工具合约 slot 写回改为空实现。
  - WorkingMemoryService/builder 默认不再同步 slots，缓存清理不再触发 slot invalidate。
- **提交记录（最近）**
  - `4a794c9` quality_checker → MAS WM facts
  - `1c36713` video_composer → MAS WM facts
  - `513a559` concept_planner → MAS WM facts
  - `91c9d22` audio_generator 移除 shared_wm import
  - `8edb4ff` BaseAgent/WM service 去掉 slot 同步 + shared_wm wiring

### 待办/未完成
- **上下文外移**
  - ✅ context manager 默认注入 `build_mas_state_view`，ReActAgent 直接消费；后续可在编排层按需裁剪。
- **slot 接口彻底移除评估**
  - ✅ 生产路径已无 slot 调用；如需启用可选后端需新实现适配层，否则保留归档。
- **文档同步**
  - ⚠️ 本页与 `react_memory_alignment.md` 需持续刷新，注明 slot/fact_store 已退役，补充 voice_assets 迁移细节。

### 下一步建议
1) 上下文外移：由编排层/context manager 构建上下文并注入 Agent，避免在 OBS/Agent 内拼装领域上下文，必要时合并 MAS state view。
2) 评估并删除剩余 slot 接口与配置（如 `memory_slots.yaml`）后更新测试。
3) 同步文档，确认生产路径仅依赖 MAS WM facts/scene_outputs，归档代码注明 legacy。
