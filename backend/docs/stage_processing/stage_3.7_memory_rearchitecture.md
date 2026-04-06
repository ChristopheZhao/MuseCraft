## 记忆系统重构阶段快照（Stage 3.7）

### 背景
- 目标：让 MAS 体系的记忆层真正做到“基础实现 ↔ 抽象服务 ↔ 应用层”解耦，便于扩展和迁移。
- 当前痛点：
  - WorkingMemory 里混入了场景等领域字段，导致基础层被业务绑死。
  - `get_fact`/`MasSharedMemoryFacade` 等接口把“事实/场景”写死在抽象层。
  - 各个 Agent/工具在不同地方自行拼装字段，缺少统一的检索与上下文构造方式。

### 已完成
1. **WorkingMemoryService 瘦身**  
   - 仅负责按 scope 管理实例；不再隐式同步 “workflow scope” 或写入业务字段。
2. **MAS Helper 上移**  
   - `MasSharedMemoryFacade`/`get_shared_wm` 迁出 memory 包，改为应用层服务；WorkingMemory 只暴露中立 API。
3. **Scope/写入逻辑统一**  
   - `agent_scope/mas_scope` 改由 `agents/utils/memory_helpers.py` 管理，抽象层不再暴露业务命名。
4. **WorkingMemory 架构重置**  
   - 移除 `SceneSnapshot` 等领域字段，只保留通用存储（facts、event_streams、notes、artifacts、slots）。
   - Builder/Assembler 同步的也是这些通用结构。

### 现状 / 待办
1. **检索能力抽象**  
   - 需要在抽象层明确 `get/set/delete/list/query` 等纯粹接口，为后续向量/图等实现留出空间。
2. **视图/上下文构造**  
   - Orchestrator 侧缺乏统一的“视图构建”工具（根据 agent 策略从 MAS 工作/情景记忆取字段）；需集中到 `agents/utils/memory_views.py`（或同类模块），降低各 agent 的重复逻辑。
3. **旧业务逻辑迁移**  
   - `memory/operators/video_scene.py`、`memory/adapters/video.py` 等领域逻辑尚未删除，需要把必要部分迁到应用层（视图/工具），其余废弃。
4. **测试/文档**  
   - 需要更新相关单测/集成测试（WorkingMemory、Image React flow、MAS collaboration 等），并补充文档说明新的记忆分层和使用方式。

### 下一阶段计划
| 阶段 | 任务 | 说明 |
| ---- | ---- | ---- |
| Stage 3.7-A | 抽象接口整理 | 以 `WorkingMemory` 为中心，统一 `get/set/delete/list` 等 API，去除 `get_fact` 等业务命名；检索接口保持纯粹。 |
| Stage 3.7-B | 视图构建工具 | 在 Orchestrator 侧实现 `build_*_context` 等函数，基于 MAS 工作/情景记忆输出 Agent 所需上下文；所有 Agent 复用这些函数。 |
| Stage 3.7-C | 旧逻辑清理 + 测试 | 删除 memory 包内的领域逻辑文件，更新 Agent/工具/测试走新接口，并补充文档。 |

### 关键概念速查
- **MAS 工作记忆**：workflow 级短期存储（SoT + 最近 k 步），任务结束即释放。
- **MAS 情景记忆**：workflow 级长期轨迹（完整 {thought, act, obs}），持久化用于审计/复盘。
- **Agent 工作/情景记忆**：作用域缩小到单个 Agent，原则与 MAS 层相同。
- **检索 vs 视图**：检索=基础/抽象层提供的纯读写接口；视图=Orchestrator 根据策略拼装出来的 Agent 上下文。

> 这份快照用于后续任务接力：确保任何人接手都能快速理解记忆重构的现状、遗留问题与下一步计划。
