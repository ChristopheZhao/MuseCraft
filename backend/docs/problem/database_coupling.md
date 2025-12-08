# 数据库耦合现状与风险

## 现状
- Orchestrator 在工作流末尾同步调用 `data_persistence_service.persist_from_mas_wm`，直接使用 ORM 将 Task/Scene/Resource 等写入数据库。Agent 虽不直接持有 DB session，但编排层仍与数据库紧耦合。
- `data_persistence` 读取 MAS WorkingMemory 快照后落库，WorkingMemory 与审计/业务数据库之间仍有直接依赖，未通过事件或独立持久化服务解耦。
- `backend/app/events` 仅用于状态/进度广播，未承担持久化驱动，持久化路径未接入事件监听器。
- 部分服务仍回退全局 `get_memory_services()`，未强制依赖注入，存在隐式单例耦合。

## 偏差（相对规划）
- 与《database_memory_decoupling.md》的事件驱动、记忆与审计解耦目标不符：持久化应由监听器消费事件写库，Agent/Orchestrator 不应直接落库。
- 数据边界模糊：数据库仍被当作运行时“真相”，而非仅存业务元数据/资源索引；运行轨迹应由记忆体系/事件流承载。
- 规划中的 PersistenceListener/EpisodicListener 未落地，事件总线仅用于进度/状态广播，未驱动持久化。

## 风险
- 失败耦合：持久化异常直接影响编排流程，缺少重试/缓冲。
- 演进阻塞：难以替换数据库或改为异步/事件模型，测试隔离成本高。
- 边界混乱：记忆（WM/Episodic）与审计/业务数据混用，违背分层。

## 建议方向
- 将持久化改为事件驱动：Orchestrator/Agent 只发布标准事件，由独立 PersistenceListener 写库；EpisodicListener 记录轨迹。
- 精简 data_persistence：作为事件 sink，从事件或终态摘要写最小业务元数据/资源索引；不直接从 WM 全量入库。
- 强制依赖注入：去除 `get_memory_services()` 回退，消除隐式单例。
- 明确数据库保留字段与禁止内容（参见 database_memory_decoupling.md），确保运行态/轨迹不落业务库。

## 例子与待改文件（非穷举）
- 同步持久化：`backend/app/agents/orchestrator.py` 在工作流结束调用 `data_persistence_service.persist_from_mas_wm`，直接写 DB。
- 持久化实现：`backend/app/services/data_persistence.py` 直接使用 ORM 落库（Task/Scene/Resource），默认回退 `get_memory_services()`。
- 单例回退：`data_persistence.py`、`memory_utils.py`、`context_assembler.py`、部分工具/provider 仍存在 `get_memory_services()` 回退。
- 事件缺失：`backend/app/events` 仅用于 WS/状态推送，缺少 PersistenceListener/EpisodicListener。
