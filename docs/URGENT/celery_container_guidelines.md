# Celery 执行容器使用指南（不逆自主化/不逆迁移）

边界与职责
- 仅作为“执行容器”：排队 + 独立进程执行 `OrchestratorAgent.execute(...)`。
- 禁止用 Canvas/Chord 编排子阶段；ReAct 决策与重试在 Orchestrator/Agents 内部完成。

状态与幂等
- 开启单写：`ARTIFACTS_SINGLE_WRITE_MODE=true`；所有 Agent 通过 `write_shared_artifact(...)` 写入 `artifacts` 时间线。
- 消费优先读：`ORCHESTRATOR_READS_ARTIFACTS=true`；最终成片取 `artifacts.latest(kind='video', stage='compose')`。
- facts 仅为指针/摘要，严禁在容器层保存关键状态。

日志与可观测性
- 开发：`celery worker -l DEBUG`。
- 生产：`worker_hijack_root_logger=False`；Worker 初始化按 `settings.LOG_LEVEL` 设置 root/handlers。
- MAS 文件日志：设置 `MAS_LOG_DIR` 与 `MAS_LOG_LEVEL=DEBUG`；将 `agent.*`、`tool.*` logger `propagate=False`，避免被 Celery 根 logger 影响。

运行参数
- `task_acks_late=True`、`worker_prefetch_multiplier=1`（防止任务囤积）。
- `task_soft_time_limit / task_time_limit > Orchestrator/Agent timeout`（容器外层不得比业务更短）。
- 按类型拆队列（视频/音频/合成），重负载走专用队列。

生命周期
- Worker 启动时初始化工具与日志（signals.worker_process_init）；任务内不重复注册重型依赖。
- 使用 `asyncio.run(orchestrator.execute(...))`，避免手搓事件循环导致泄漏与阻塞。

禁止事项（防逆规范/逆迁移）
- 禁止将业务流程翻译到 Celery Canvas/Chord。
- 禁止在 Celery 层做业务重试/降级；仅兜底重发。
- 禁止在 Agent 内直连 I/O；严格走工具层（FC）。

迁移准备
- 将“定时等待/轮询”集中在 Timer 抽象（当前可用 `asyncio.sleep`），后续可映射 Temporal timer。
- 保持 `artifacts` 单写与“最新即真”，便于容器替换。

