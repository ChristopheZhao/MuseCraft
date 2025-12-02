# 数据库与记忆体系解耦重构计划

## 1) 为什么改
- 职责重叠：数据库既存储业务元数据，又被用来记录工作流轨迹（AgentExecution/进度），与 WorkingMemory/Episodic Memory 的目标重叠。
- 耦合过深：BaseAgent 直接持有 DB Session 写进度/执行日志，Agent 行为与持久化耦合，难以测试与演进。
- 概念混乱：DataPersistenceService 从 MAS WM 导出全量结果落库，数据库被当作“运行时真相”，违背记忆分层设计；数据库本是审计/流程信息的实现选项，却与 Agent 直连，未通过记忆抽象。
- 目标：厘清“记忆 vs 审计”边界——运行态/轨迹归记忆体系（WM/Episodic），数据库作为审计/业务元数据存储；数据库可以作为记忆后端的实现选项，但默认职责是审计与对外查询，Agent 不直接操作数据库。

## 2) 调研输入与方案对比
- 认知记忆分层视角：WorkingMemory（短期运行态）、Episodic Memory（完整时序轨迹）、Semantic Memory（抽象知识）。运行轨迹应落在 Episodic，WorkingMemory 仅承载当前任务信息。
- 工程落地视角：
  - 方案 A（纯记忆驱动）：WM + Episodic 承载全部运行与轨迹，DB 仅存任务元数据/资源索引（最小化）。优点：解耦彻底；挑战：前端/报表需适配新的读取路径。
  - 方案 B（过渡/双轨）：事件驱动解耦 Agent，DB 保留精简的执行摘要/进度兜底，Episodic 记录完整轨迹，WM 仅供运行态。优点：兼容当前查询/前端；挑战：需双轨开关与迁移计划。
- 选型思路：以边界清晰为终态。短期可用方案 B 平滑过渡，最终收敛到方案 A：DB 只保留元数据/审计，运行态与轨迹由记忆体系（可选 DB 后端实现）和事件流统一承载。

## 2) 问题定位与难点
- 当前状态
  - AgentExecution/进度：BaseAgent.execute 直接写 DB。
  - 结果落库：DataPersistenceService 从 MAS WM 导出快照写 Task/Scene/Resource。
  - WebSocket 推送与 DB 写入绑在一起，双轨但耦合。
  - Episodic Memory 仅有 stub，未真正记录轨迹。
- 偏差/难点
  - 需要清晰边界：WorkingMemory（短期运行态）、Episodic（轨迹）、DB（业务元数据）。
  - 进度/审计从 Agent 中抽离，需要事件总线或观察者机制。
  - 迁移期要兼容现有 API/前端进度，避免回归。
  - 持久化粒度要收敛：DB 保存什么、Episodic 保存什么、WM 保存什么。

## 3) 实现方案（从现状到目标）
- 边界定义
  - WorkingMemory（mas/agent）：短期运行事实/产物，供 ReAct/工具使用，不入 DB。
  - Episodic Memory：完整 MAS+Agent 轨迹（obs/plan/act/result/metrics），持久化到日志/对象存储/时序库。
  - Database：最小业务元数据与终态摘要（任务状态、资源索引、可选最终产物引用），不存运行轨迹。
- 事件驱动解耦
  - Agent 不再持有 DB/WS；改为发布事件（开始/进度/完成/失败、产物就绪）。
  - PersistenceListener 订阅事件，写入 DB 所需的元数据（可配置关闭）。
  - NotificationListener 订阅事件，推送 WebSocket/消息。
  - EpisodicListener 订阅事件，写入长期轨迹存储。
- 持久化路径调整
  - DataPersistenceService 从“全量导出 MAS WM 入库”改为：读取 WM/episodic 的终态摘要，写最小元数据或生成最终资源索引；可配置关闭。
  - AgentExecution 表如需保留，转由事件监听写入，或迁出到 Episodic 存储；DB 可仅保留 Task 状态与资源索引。
- 逐步替换
  - 保留双轨兜底期：事件写入 + 兼容旧 DB 写入（可配置开关）。
  - 待前端/接口完成适配后，移除 Agent 直接写 DB 的路径。

## 4) 行动清单（分阶段/优先级）
- P0 设计定稿（高优先）
  - [ ] 明确数据边界：WM vs Episodic vs DB，产出数据流图与保留字段清单。
  - [ ] 定义事件模型（进度、状态、产物、错误）和事件总线接口。
- P1 基础设施落地（高优先）
  - [ ] 实现事件总线（可先用内存发布/订阅）与标准事件结构。
  - [ ] 实现 NotificationListener（WebSocket 推送）解耦 Agent。
  - [ ] 实现 PersistenceListener，将 AgentExecution/进度/最终摘要写 DB（可配置开关）。
  - [ ] 实现 EpisodicListener，接入真实轨迹存储（或先落日志/对象存储）。
- P2 Agent 解耦（中优先）
  - [ ] BaseAgent 去除直接 DB/WS 依赖，改为发布事件；进度/执行日志不再在 Agent 内写 DB。
  - [ ] 调整 ReActAgent/各 Agent 调用链，保证不依赖 Session 对象。
- P3 持久化路径收敛（中优先）
  - [ ] 重构 DataPersistenceService：从 WM/episodic 汇总终态摘要写 DB 最小集；移除全量快照入库。
  - [ ] 评估 AgentExecution/Scene 等表：保留元数据或迁出；更新模型/迁移脚本。
- P4 前端/接口适配（中优先）
  - [ ] 前端/API 读取进度改用事件/缓存/轻量查询，减少对 AgentExecution 的依赖。
  - [ ] 验证 WebSocket 兼容性，必要时增加事件->WS 适配层。
- P5 收尾与验证（低优先）
  - [ ] 清理兼容开关，移除 Agent 内遗留 DB 写路径。
  - [ ] 回归测试：进度推送、任务状态查询、资源索引、轨迹写入/检索。
  - [ ] 文档更新：架构边界、数据流、运维指南（事件总线/存储配置）。

## 5) 风险与对策
- 外部依赖：事件总线/轨迹存储选择需权衡（可先用内存+日志作为落地）。
- 回归风险：前端进度/状态依赖旧表，需双轨过渡与开关控制。
- 数据迁移：若精简/调整 DB 模型，需迁移脚本与回滚方案。
