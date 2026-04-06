# 迁移护栏（不逆自主化 / 不逆规范 / 不逆 Temporal 迁移）

目标
- 确保短期用 Celery 稳住流程的同时，不引入任何将来迁移 Temporal 会推倒重来的改造。

Do（应当）
- 单写 `artifacts`，facts 仅指针/摘要；消费者优先读 `artifacts` 最新产物。
- 所有 I/O 严格经工具层（FC）；组合工具仅封装步骤序列，不写记忆、不做发布。
- Orchestrator/Agents 维持 ReAct 决策闭环（observe → plan → act → reflect）。
- 定时/等待集中在 Timer 抽象（后续映射 Temporal timer）。
- 开关灰度：`USE_TEMPORAL` 便于并行与回退。

Don’t（禁止）
- 不把流程拆为 Celery Canvas/Chord 子任务（防止固化流水线）。
- 不在 Celery 层实现业务重试/降级；不在容器层保存关键状态。
- 不在 Agent 内直连服务端 I/O（HTTP/SDK/FFmpeg 命令行）；必须走工具层。
- 不在提示中出现工具名/参数名（Prompt Neutrality）。

验收信号（准备切 Temporal）
- 断点续跑：仅凭 `artifacts` + 快照即可恢复并继续流程。
- 可观测：可追溯阶段产物时间线与“只取最新”逻辑；日志独立于容器控制台。
- 容器透明：编排容器（Celery/Temporal）仅替换启动与进程边界，业务逻辑零修改。

