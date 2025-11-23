## Stage 3.8 — 共享记忆去耦与slot清理（进行中）

### 已完成
- **Agent 路径迁移到 MAS WM**
  - `script_writer`：上下文/写回改用 MAS WorkingMemory facts（`project.concept_plan`/`project.voice_plan`/`scene_overview`/`scene_scripts`），去除 shared_wm 和 slot 写入。
  - `concept_planner`：写回 MAS WM facts（concept_plan、voice_plan、scene_overview），不再使用 shared_wm。
  - `video_composer`：上下文和资产读取改用 MAS WM facts/scene_outputs，移除 shared_wm/fact_store 访问。
  - `quality_checker`：上下文/最终视频信息来源改为 MAS WM facts 和 `scene_overview`，移除 shared_wm。
  - `audio_generator`：移除 shared_wm import（保持 MAS WM 读取）。
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
- **工具层 shared_wm 依赖未清理**
  - `scene_continuity_preparation_tool.py`：覆盖 URL 提帧失败时仍尝试通过 shared_wm 复用场景帧，需移除，改为纯执行（提帧→上传→返回）。
  - `video_generation_tool_v2.py` 等工具仍有 shared_wm 访问，需要改为“只返回产物，写回由调用方完成”。
- **其他 shared_wm 引用**
  - `orchestrator.py`、部分长程/测试路径（如 `memory/long_term/snapshots.py`）尚未迁移。
- **slot 接口彻底移除评估**
  - WorkingMemory 的 `set_slot_value/get_slot_value` 仍存在但无主路径使用，后续可删除并更新文档/测试。
- **文档/测试同步**
  - 测试中仍有 fact_store/shared_wm 依赖需调整。

### 下一步建议
1) 清理工具层：移除工具对 shared_wm/MAS WM 的直接读写，只保留纯执行输出；调用方用 `write_shared_fact`/`persist_scene_outputs` 落盘。
2) 清理 `orchestrator.py` 等核心路径的 shared_wm 读取，统一 MAS WM facts/scene_outputs。
3) 评估并删除剩余 slot 接口与配置（如 `memory_slots.yaml`）后更新测试。
4) 同步文档/测试，确保新架构只依赖 MAS WM facts/scene_outputs。
