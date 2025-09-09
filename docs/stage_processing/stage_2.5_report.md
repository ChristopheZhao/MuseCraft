# 阶段 2.5 变更记录（待验证）

> 说明：本报告仅用于记录本阶段已完成的设计与代码改动，当前改动尚未完成全面验证，请勿据此认定“系统可用”。

## 目标
- 解决“概念/脚本等关键信息在下游 Agent 丢失”的问题。
- 在不改变现有 Agent 代码的前提下，引入统一的“上下文回灌 + 标准化写回”机制。
- 默认提供持久化记忆能力，保证重启/异常后的记忆连续性。
- 保持解耦与可演进：记忆层为共享能力，后端/策略可替换。

## 本阶段主要改动（代码）
- 上下文装配（回灌）
  - 新增：`backend/app/services/context_assembler.py`
  - 作用：在 Orchestrator 执行 Agent 前，按任务类型汇聚必需上下文（CONCEPTUAL/EPISODIC/连续性），注入到输入数据中（`_assembled_context`）。
  - 策略（可选）：`backend/config/mas/context_policies.yaml`（无配置时走默认收敛逻辑）。

- 执行后写回（标准化）
  - 新增：`backend/app/services/memory_writer.py`
  - 作用：在 Orchestrator 执行 Agent 后，将本轮关键输出（如 Script 的 `script_text/voice_over` 等）按标准 schema 写回记忆（EPISODIC/CONCEPTUAL 等）。
  - 策略（可选）：`backend/config/mas/writer_policies.yaml`。

- 共享记忆工具（通用能力）
  - 新增：`backend/app/agents/tools/memory_tool.py`
  - 动作：`search_memories / get_recent / write_memory / get_continuity`。
  - 已注册至工具注册表：`backend/app/agents/tools/__init__.py`。

- Orchestrator 钩子（最小侵入）
  - 修改：`backend/app/agents/supervisor_orchestrator.py`
  - Before Hook：调用 `ContextAssembler`，将必需上下文注入 `input_data['_assembled_context']`。
  - After Hook：调用 `MemoryWriter`，将关键输出写回记忆。

- 默认持久化（SQLite）
  - 新增：`backend/app/agents/memory/sqlite_memory_store.py`
  - 默认将记忆后端设置为 SQLite（路径：`backend/storage/memory.sqlite`），不可用时自动回退到内存后端（Dict）。
  - 后端选择逻辑：`backend/app/services/global_memory_service.py`。

- 基础指标打点（便于后续评估）
  - 回灌：在 `context_assembler.py` 记录回灌次数/耗时/命中组件（复用 `MonitoringService`）。
  - 写回：在 `memory_writer.py` 记录写回次数/耗时/失败数。
  - 工具：在 `memory_tool.py` 记录调用次数/耗时。
  - 监控服务复用：`backend/app/services/monitoring_service.py`，新增快照导出：
    - `get_metrics_snapshot()` / `dump_metrics_to_file()` / `log_metrics_snapshot()`。

## 本阶段主要改动（配置）
- 策略文件（可选）：
  - `backend/config/mas/context_policies.yaml`
  - `backend/config/mas/writer_policies.yaml`
- 默认行为：
  - 回灌、写回默认开启（无须配置）。
  - 默认后端为 SQLite；若不可用自动回退内存后端。

## 关键设计点
- 解耦：记忆作为共享能力与统一服务（GlobalMemoryService + MemoryTool），不归属某个 Agent。
- 两条通路并存：
  - 编排层强制回灌关键上下文（保证不丢）；
  - Agent 可通过 MemoryTool 自主按需读写（受范围/一致性约束）。
- 可演进：
  - 策略可逐步外置到 YAML；
  - 后端可平滑替换（Mem0/向量/服务化）；
  - 监控与治理可逐步增强（TTL/清理/多租户/审计/配额等）。

## 尚待验证与已知风险（本阶段暂不宣称“可用”）
- 功能回归：
  - 完整链路（概念 → 脚本 → 图像/视频）是否稳定命中 `_assembled_context`。
  - 写回条目的 schema/标签是否满足下游检索。
- 持久化：
  - SQLite 默认路径与权限是否在不同环境下可用；
  - 回退策略是否覆盖异常场景。
- 性能与开销：
  - 回灌/写回带来的额外耗时与 token 预算占用。
- 策略适配：
  - YAML 策略的默认项是否需要根据实际业务进一步精细化。

## 建议的后续工作
- 验证脚本与手册：
  - 跑一条完整链路，导出 metrics 快照（`backend/storage/metrics_snapshot.json`），检查回灌/写回是否发生与耗时范围。
- 策略细化：
  - 按真实业务补充 `context_policies.yaml / writer_policies.yaml` 的取/写规则与标签词表。
-（可选）指标出入口：
  - 提供简单的管理命令或 API，便于拉取当前指标快照。
-（可选）向量/混合检索：
  - 若出现召回缺口，再评估开启（对上层透明）。

---
*注：本报告仅记录“已落地设计与代码改动”，当前改动仍处于“待验证”状态。*
