# 数据库与记忆体系解耦重构计划

## 1) 为什么改
- 职责重叠：数据库既存储业务元数据，又被用来记录工作流轨迹（AgentExecution/进度），与 WorkingMemory/Episodic Memory 的目标重叠。
- 耦合过深：BaseAgent 直接持有 DB Session 写进度/执行日志，Agent 行为与持久化耦合，难以测试与演进。
- 概念混乱：DataPersistenceService 从 MAS WM 导出全量结果落库，数据库被当作“运行时真相”，违背记忆分层设计；数据库本是审计/流程信息的实现选项，却与 Agent 直连，未通过记忆抽象。
- 目标：厘清“记忆 vs 审计”边界——数据库是一种存储介质，可作为记忆后端的实现选项，也可用于审计/对外查询；本次重构聚焦数据库承担审计/业务记录的路径，记忆与审计是不同模块，无需共用组件，Agent 不应直接操作数据库。

## 2) 调研输入与方案对比
- 认知记忆分层视角：WorkingMemory（短期运行态）、Episodic Memory（完整时序轨迹）、Semantic Memory（抽象知识）。运行轨迹应落在 Episodic，WorkingMemory 仅承载当前任务信息。
- 工程落地视角：
  - 方案 A（纯记忆驱动）：WM + Episodic 承载全部运行与轨迹，DB 仅存任务元数据/资源索引（最小化）。优点：解耦彻底；挑战：前端/报表需适配新的读取路径。
  - 方案 B（过渡/双轨）：事件驱动解耦 Agent，DB 保留精简的执行摘要/进度兜底，Episodic 记录完整轨迹，WM 仅供运行态。优点：兼容当前查询/前端；挑战：需双轨开关与迁移计划。
- 选型思路：以边界清晰为终态。短期可用方案 B 平滑过渡，最终收敛到方案 A：DB 只保留元数据/审计，运行态与轨迹由记忆体系（可选 DB 后端实现）和事件流统一承载。

## 2) 问题定位与难点
- 当前状态（已重构）
  - AgentExecution 模型/表已删除，Agent 不再直写 DB，改为发布事件（STATE/PROGRESS/ARTIFACT/ERROR）。
  - WS 推送：由 NotificationListener 订阅事件完成。
  - 事件驱动持久化：handle_persistence_event 作为 persistence sink，将状态/进度/产物写回 Task/Resource（可配置）。
  - Episodic：可选文件落盘（FileEpisodicSink），仍待完善长期轨迹后端。
- 偏差/难点
  - 需要清晰边界：WorkingMemory（短期运行态）、Episodic（轨迹）、DB（业务元数据）。
  - 进度/审计从 Agent 中抽离，需要事件总线或观察者机制。
  - 迁移期要兼容现有 API/前端进度，避免回归。
  - 持久化粒度要收敛：DB 保存什么、Episodic 保存什么、WM 保存什么。

## 3) 实现方案（从现状到目标）
- 边界定义
  - WorkingMemory（mas/agent）：短期运行事实/产物，供 ReAct/工具使用，不入 DB。
  - Episodic Memory：完整 MAS+Agent 轨迹（obs/plan/act/result/metrics），持久化到日志/对象存储/时序库。
  - Database：存储介质，可被审计/业务记录模块使用（最小业务元数据与终态摘要），也可作为记忆后端的实现；逻辑上与记忆模块解耦，不存运行轨迹。
- 事件驱动解耦
  - Agent 不再持有 DB/WS；改为发布事件（开始/进度/完成/失败、产物就绪）。
  - PersistenceListener 订阅事件，写入 DB 所需的元数据（可配置关闭）。
  - NotificationListener 订阅事件，推送 WebSocket/消息。
  - EpisodicListener 订阅事件，写入长期轨迹存储。
- 持久化路径调整
  - DataPersistenceService 从“全量导出 MAS WM 入库”改为：读取 WM/episodic 的终态摘要，写最小元数据或生成最终资源索引；可配置关闭。
  - AgentExecution 表已删除；如需审计，统一通过事件监听写入 Episodic/日志/可选的 DB 摘要表，DB 只保留 Task 状态与资源索引。
- 切换策略
  - 现状为单一路径（Agent 直写 DB），无双轨可兼容，直接切换到事件驱动主路径，移除 Agent 写 DB；如有遗留数据，统一通过迁移脚本处理。

## 4) 行动清单（分阶段/优先级）
- P0 设计定稿（高优先）
  - [ ] 明确数据边界：WM vs Episodic vs DB，产出数据流图与保留字段清单。
  - [ ] 定义事件模型（进度、状态、产物、错误）和事件总线接口。
- P1 基础设施落地（高优先）
  - [x] 事件总线（内存 pub/sub）与标准事件结构。
  - [x] NotificationListener（WebSocket 推送）解耦 Agent。
  - [x] PersistenceListener：通过 `handle_persistence_event` 写 Task 状态/进度和 Resource 产物（可配置）。
  - [ ] EpisodicListener：完善长期轨迹后端（当前文件落盘，待接入对象存储/日志）。
  - [x] 定义标准事件模型（progress/state/artifact/error），包含 task_id/workflow_id/agent/ts/payload。
  - [x] 事件流模块集中在 `app/events/`。
- P2 Agent 解耦（中优先）
  - [x] BaseAgent 去除直接 DB/WS 依赖，改为发布事件；进度/执行日志不再在 Agent 内写 DB。
  - [x] 调整 ReActAgent/各 Agent 调用链，保证不依赖 Session/AgentExecution。
  - [x] 删除旧 DB 写入路径，仅保留事件流。
- P3 持久化路径收敛（中优先）
  - [ ] 重构 DataPersistenceService：从 WM/episodic 汇总终态摘要写 DB 最小集；移除全量快照入库。
  - [x] 删除 AgentExecution 表（含 Alembic drop 迁移），清理导入。
- P4 前端/接口适配（中优先）
  - [ ] 前端/API 读取进度改用事件/缓存/轻量查询，减少对 AgentExecution 的依赖（API 已移除 AgentExecution 查询，前端待验证）。
  - [ ] 验证 WebSocket 兼容性，必要时增加事件->WS 适配层。
- P5 收尾与验证（低优先）
  - [x] 清理兼容开关，移除 Agent 内遗留 DB 写路径（AgentExecution 兼容已去除）。
  - [ ] 回归测试：进度推送、任务状态查询、资源索引、轨迹写入/检索（测试仍需更新/跳过 AgentExecution 引用）。
  - [ ] 文档更新：架构边界、数据流、运维指南（事件总线/存储配置）。

## 5) 风险与对策
- 外部依赖：事件总线/轨迹存储选择需权衡（可先用内存+日志作为落地）。
- 回归风险：前端进度/状态依赖旧表，需双轨过渡与开关控制。
- 数据迁移：若精简/调整 DB 模型，需迁移脚本与回滚方案。

## P0 设计基线与验收口径

### 数据边界与保留字段
- **WorkingMemory（短期运行态）**：仅存运行期事实/产物引用/OBS 结果，作用域为 MAS（共享）与 Agent（私有）；不入库，不存二进制文件，引用使用可解析的路径/URL/资源 ID。
- **Episodic Memory（轨迹）**：记录 {plan/act/obs/result/metrics} 全轨迹，落日志或对象存储，可替换后端；与 DB 解耦，用于诊断/追溯，不作为前端进度读取路径。
- **Database（审计/业务元数据）**：只保留业务查询/审计所需最小集，不承载运行轨迹。
  - Task：task_id/title/status/progress/current_step/error/输入输出摘要（概念/voice_plan/内容要素）/时间戳；资源索引（最终资源列表）引用 Resource。
  - Scene：scene_number/type/title/description/script_text/narrative/visual 描述/时间轴（start/duration/end）/生成参数摘要。
  - Resource：task_id/scene_id/filename/file_path|url/resource_type/mime/duration/尺寸/生成参数/是否最终产出/存储提供方；仅记录引用与元数据，不存文件。
  - AgentExecution（如保留）：仅存状态摘要（agent_type/name/version/status/start/end/duration/progress/substep/error 摘要/模型参数摘要），不存全量输入输出，不存 tool trace。
  - 不允许写入：运行时迭代序列、tool 调用明细、WM 快照全文、音视频二进制。

### 事件模型与总线约束
- **基础字段**：event_id（可选去重）、schema_version、event_kind、task_id、workflow_state_id、agent{type,name}、iteration（可选）、scene_number（可选）、timestamp（epoch ms）、payload（JSON）。
- **事件类型**：
  - progress：percentage、substep、maybe execution_order/hint。
  - state：task/agent 状态变更，包含 status/from/to、reason（可选）。
  - artifact：kind/stage/scene_number/ref（url/path/resource_id）/duration_sec/prompt_text/metadata。
  - error：error_type/message/retriable（bool）/stacktrace（可选短摘要）/failed_stage（可选）。
  - diagnostic/metric（可选）：tokens_used/cost/latency 分桶。
- **约束**：payload 仅 JSON-可序列化原语；大小上限（建议 <16KB，超过需截断+标记）；事件顺序按 timestamp+sequence 序；schema_version 变更需兼容处理；缺少能力时显式报错/降级为 info，不静默吞掉。
- **事件流定位**：Agent 仅发布事件；Listener 执行 WebSocket 推送、DB 摘要持久化、轨迹写入。总线初版可用进程内 pub/sub，可配置替换后端；错误策略需支持重试/死信/指标暴露。

### P0 验收清单
- [ ] 文档已固化 WM/Episodic/DB 边界及 DB 保留字段清单，明确禁止内容。
- [ ] 事件 schema（字段、类型、约束、大小上限、顺序/去重策略）可直接驱动 P1 开发，无歧义。
- [ ] Listener 职责划分与总线定位清晰（Agent 只发事件，监听器各司其职），并注明缺失能力时的显式降级策略。

### P3 补充：AgentExecution 去除 & 审计不落 DB
- 决策：审计不再落 DB，AgentExecution 模型/表删除；审计通过事件流→文件/对象存储/可选 DB 摘要（通过 persistence sink）承载。
- 任务完成情况：
  - [x] 删除 AgentExecution 模型/表（含 Alembic drop 迁移），清理 models/__init__ 导入。
  - [x] Agent/Orchestrator/工具不再导入或传递 AgentExecution/Session，执行上下文改为内存 run_id + execution_order。
  - [x] 事件监听器默认写文件（Episodic）/可选 DB 摘要（handle_persistence_event）；文档需注明落地介质与保留字段。
  - [ ] API/前端审计视图：基于事件存储提供只读接口（目前 API 已移除 AgentExecution 查询，前端待适配）。
