# 数据库耦合现状与风险

## 现状
- Orchestrator 原先在工作流末尾同步调用 `data_persistence_service.persist_from_mas_wm`，直接使用 ORM 将 Task/Scene/Resource 等写入数据库，编排层与数据库紧耦合（现已移除同步调用，改为事件发布）。
- `data_persistence` 读取 MAS WorkingMemory 快照后落库（旧路径已删除），WorkingMemory 与审计/业务数据库之间仍有直接依赖的问题已替换为事件/摘要输入。
- `backend/app/events` 仅用于状态/进度广播，未承担持久化驱动，持久化路径未接入事件监听器。
-（已修正）全局 `get_memory_services()` / `get_working_memory_service()` 回退已移除，现均依赖显式注入。

## 偏差（相对规划）
- 与《database_memory_decoupling.md》的事件驱动、记忆与审计解耦目标不符：持久化应由监听器消费事件写库，Agent/Orchestrator 不应直接落库。
- 数据边界模糊：数据库仍被当作运行时“真相”，而非仅存业务元数据/资源索引；运行轨迹应由记忆体系/事件流承载。
- 规划中的 PersistenceListener/轨迹日志监听器未落地，事件总线仅用于进度/状态广播，未驱动持久化。
- 单例路径已清理，现存主要偏差聚焦在“编排层直接落库、未事件化”。

## 风险
- 失败耦合：持久化异常直接影响编排流程，缺少重试/缓冲。
- 演进阻塞：难以替换数据库或改为异步/事件模型，测试隔离成本高。
- 边界混乱：记忆（WM/Episodic）与审计/业务数据混用，违背分层。

## 建议方向
- 将持久化改为事件驱动：Orchestrator/Agent 只发布标准事件，由独立 PersistenceListener 写库；轨迹监听器记录调试日志（默认关闭）。
- 精简 data_persistence：作为事件 sink，从事件或终态摘要写最小业务元数据/资源索引；不直接从 WM 全量入库。
- 强制依赖注入：保持无单例回退，所有持久化/记忆均通过注入服务。
- 明确数据库保留字段与禁止内容（参见 database_memory_decoupling.md），确保运行态/轨迹不落业务库。

## 例子与待改文件（非穷举）
- 同步持久化：`backend/app/agents/orchestrator.py` 曾在工作流结束调用 `persist_from_mas_wm`，现已改为事件发布。
- 持久化实现：`backend/app/services/data_persistence.py` 现仅支持事件/摘要输入，旧的 WM 快照回退已删除。
- 事件缺失：`backend/app/events` 已有持久化 sink（handle_persistence_event），轨迹日志监听器仍待完善/可选。

## 后续行动（建议）
- 定义并发布持久化相关事件（场景完成、资源生成、任务完成）；Orchestrator 改为事件发布，移除同步持久化调用。
- 为事件总线增加 PersistenceListener/可选轨迹日志监听器，消费事件写库或记录轨迹。
- 收敛 data_persistence：输入改为终态摘要或事件载荷，避免直接读取 WM 全量。
- 更新 `database_memory_decoupling.md` 的落地进度，标记单例回退已移除，将重心转向事件化和数据边界收敛。
- 事件缺失：`backend/app/events` 仅用于 WS/状态推送，缺少 PersistenceListener/轨迹日志监听器。
