# Temporal POC（必须）

目的
- 将 Temporal 作为“可持久化工作流引擎”引入，验证长时运行、断点续跑、信号/查询与可观测性；不改现有 Agent/Tools 业务逻辑。

不逆规范/不逆迁移原则
- 容器透明：Workflow 仅包装 `OrchestratorAgent.execute(...)`；ReAct 决策依旧在 Orchestrator/Agents 内完成。
- Tools-First：所有 I/O 仍经工具层（FC）；POC 只替换“容器”，不改工具与提示。
- 状态外置：阶段产物写入 `artifacts` 时间线；facts 仅为指针/摘要；POC 读取 artifacts（最新即真）。

无 Docker 落地方案（开发环境）
1) 安装 Temporal CLI（Linux）
   - `curl -L https://temporal.download/cli/linux -o temporal && chmod +x temporal && sudo mv temporal /usr/local/bin/temporal`
2) 启动开发服（含 UI）
   - `temporal server start-dev --db-filename /tmp/temporal.db --ui-port 8233`
   - gRPC: 7233；UI: http://localhost:8233
3) 安装 Python SDK
   - `pip install temporalio`
4) 新增最小骨架（新增目录，不动现有 Agent/Tools）
   - `backend/app/workflows/video_generation_workflow.py`
     - `@workflow.defn class VideoGenerationWorkflow: @workflow.run async def run(self, task_id: int) -> dict`：内部只调用一个 Activity：`run_orchestrator(task_id)`。
   - `backend/scripts/temporal_worker.py`
     - 连接 `localhost:7233`，注册 `VideoGenerationWorkflow` 与 `run_orchestrator` Activity，监听 `task_queue="video-generation"`。
   - `@activity.defn async def run_orchestrator(task_id: int) -> dict`
     - 创建 DB session，实例化 `OrchestratorAgent`，调用 `await orchestrator.execute(...)`，返回结果。
5) API 灰度开关（仅路由层）
   - `settings.USE_TEMPORAL`（默认 false）
   - true：Temporal Client `start_workflow(VideoGenerationWorkflow.run, task.id, id=f"video-gen-{task.id}", task_queue="video-generation")`
   - false：现有 Celery `queue_task(task.id)` 保持不变

POC 验收清单
- 断点续跑：Worker 重启后，Workflow 能从最近 await 继续（Orchestrator 结果一致）。
- 暂停/恢复：使用 Temporal Signal/Query 实现暂停/查询进度，恢复后继续。
- 长时定时：使用 Continue-As-New 防状态膨胀（> 30 分钟流程仍稳定）。
- 可观测性：UI 可查看 Workflow/Activity 历史、重试轨迹与失败原因。

回滚/灰度
- 通过 `USE_TEMPORAL` 开关灰度（10%→50%→100%）；失败一键回到 Celery 容器。

时间计划
- 第 1 天：CLI + dev server + SDK 就绪；起 Worker，连通性验证。
- 第 2~3 天：最小 Workflow/Activity 骨架与 API 开关；单场景流程跑通。
- 第 4~5 天：多场景/组合工具路径跑通；完成 POC 验收清单。

风险与注意
- 开发服基于本地文件（SQLite）仅限 POC；生产需换到托管 DB/Temporal Cloud。
- 仍须保证 `artifacts` 单写与“最新产物即真”，以保证容器替换不影响业务结果。

