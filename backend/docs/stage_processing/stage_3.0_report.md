# 阶段 3.0 升级报告（ReActAgent 自主化改造与优化）

本报告基于 Git 差异与代码走查，概述本阶段（从初始提交到当前 HEAD）的核心改动、影响范围与后续建议，便于团队同步与后续迭代。

- 基线提交：`d4e8253`（initial commit）
- 当前提交：`dbdd603`（Merge feature/mas-refactor → main）
- 变更规模：101 个文件，+27,665 / −1,427 行（git diff 统计）

## 本阶段亮点
- ReActAgent 自主化回路落地：实现 OBSERVE → THINK/PLAN → ACT → REFLECT 的单轮 FC（Function Call）驱动；首轮 plan‑only 产出结构化计划，后续轮按计划执行工具。
- 工具/FC 最小暴露与参数策略：按工具声明与策略文件生成 FC schema；引入 warn‑only 参数守卫，结合供应商能力（如视频时长枚举）进行非侵入校验。
- 记忆解耦与上下文装配：以 ContextAssembler 从 Memory 层读取上下文（overall/scene/continuity），WF 写回在 Agent 完成时统一提交，避免中期状态混层。
- LLM 角色化与策略注入：按 observe/plan/act 角色注入 LLM 句柄，策略来自 `app/config/llm_policies.yaml` 和模型能力配置。
- 供应商无关与配置化：抽象服务接口（LLM/VLM/Video），provider 能力通过配置注入；移除分支硬编码，统一走 tools 与 schema。
- 归档旧模块：旧版/示例 Agent 统一迁入 `app/agents/archive/`，模块顶部抛 `ImportError` 防止生产路径误用。

## 关键代码改动（按模块）

### Agents（核心执行层）
- 新/改：
  - `app/agents/react_agent.py`：ReAct 基类与回路，统一 `run_fc_round`、计划契约解析、进展/短 scratchpad 注入（可关闭）。
  - `app/agents/base.py`：FC schema 构建与执行轨迹/产物快照，支持自动持久化产物至 `file_storage_tool`（可配）。
  - `app/agents/image_generator.py`：迁移为 ReAct 批处理（单轮一组 FC），按场景分批与反思决策推进。
  - `app/agents/video_generator.py`：迁移为 ReAct 批处理；引入严格的计划/反思 Pydantic 契约与可执行单元校验。
  - `app/agents/script_writer.py`：简化为批量生成（BaseAgent 仍然可用），支持动态超时；后续可按需迁移至 ReAct。
  - `app/agents/utils/react_helpers.py`：跨轮结果合并（completed/failed/available_prompts）。
- 归档：
  - `app/agents/archive/*`：如 `video_generator_old.py`、`image_generator_old.py`、`function_call_agent_example.py` 等，文件头部 `raise ImportError(...)` 明确禁止生产导入。

### 工具与 FC 策略
- 工具注册/分配：
  - `app/agents/tools/tool_registry.py`、`app/agents/tools/agent_tool_allocation.py`：按 AgentType 分配工具，工具默认 `get_fc_visibility()` 为不暴露，需策略显式开放高风险动作。
- FC 参数守卫（非侵入 warn‑only）：
  - `app/agents/utils/fc_param_guard.py`：读取 `config/mas/fc_param_policies.yaml` 与 provider 能力（如 `${provider.duration_capabilities}`）进行参数合规提示，不修改工具调用。
- 供应商无关接口：
  - `app/agents/tools/ai_services/service_interfaces.py`：统一 LLM/VLM/Video 抽象，避免供应商分支；`app/agents/utils/llm_policy.py` + `app/config/llm_policies.yaml` 注入角色化 LLM 句柄。

### 记忆解耦与上下文
- `app/services/context_assembler.py`：从 `GlobalMemoryService` 与 `SceneContinuityMemory` 读取上下文；策略 `config/mas/context_policies.yaml` 可选覆盖，缺省安全降级。
- `app/services/global_memory_service.py` / `app/services/memory_writer.py`：统一回写与统计；WF 仅在 Agent 完成时写入（可通过 `settings.REACT_WRITE_WF_ON_COMPLETE_ONLY` 控制）。

### 编排与 MAS 相关
- 轻量编排：
  - `app/agents/orchestrator.py`：顺序与重复策略（policy‑first + 可选 LLM 建议）；每个 Agent 注入角色化 LLM。
- MAS 体系（设计与扩展位）：
  - `app/core/mas_*.py` 一揽子模块（orchestrator/dispatcher/decomposer/aggregator/adapter/communication 等）引入，支撑更复杂多 Agent 协作与可观测性（当前主路径仍用轻量 Orchestrator）。

### 配置与模板
- `app/core/config.py`：集中 ReAct/工具/Agent 超时、token 档位、批量大小、内容预览长度等配置项。
- `app/core/ai_config.py` + `config/ai_config.yaml`：Agent→模型/思维模式映射与可用性管理，供应商能力通过配置注入。
- Prompt 模板：`config/prompts/agents/*.yaml` 更新/新增，贴合 ReAct 回路与最小暴露原则。

### 文档与脚本
- 新设计与对齐文档：`PHASE_2_MULTI_AGENT_SYSTEM_DESIGN.md`、`MULTI_AGENT_COORDINATION_DESIGN.md`、`AGENTS.md`（原则与分层规则）。
- 开发报告与故障记录：`docs/stage_processing/stage_2_report.md`、`docs/stage_processing/HIGH_PRIORITY_LLM_FUNCTION_CALL_ISSUE.md`。
- 开发/校验脚本：`scripts/pre_commit_check.py`、`scripts/verify_multi_agent_system.py` 等。

## Git 变更概览（摘录）
- 区域统计（backend/ 下按顶层目录）：
  - app：46 文件变更（agents/core/tools/services 等）
  - archive：32 新增（旧模块归档并禁止导入）
  - config：5 新增（prompt 与策略）
  - docs：新增阶段报告与高优先级问题记录
  - scripts：3 新增（清理、预检、测试脚本）
  - 新增多份测试与集成验证文件（llm/memory/mas/continuity 等）
- 总计：101 files changed, 27665 insertions, 1427 deletions

> 注：详细文件清单与行级差异可使用：
> - `git diff --stat d4e8253..HEAD`
> - `git diff --name-status d4e8253..HEAD`
> - 聚焦 ReAct：`git diff HEAD -- app/agents/react_agent.py app/agents/base.py app/agents/image_generator.py app/agents/video_generator.py`

## 兼容性与迁移
- 旧 Agent 已归档并禁止导入；生产路径已切换到新 ReAct/工具/策略体系。
- 供应商能力与参数范围通过配置注入，不再在代码中分支或硬编码；如需扩展供应商，仅需实现接口 + 配置映射。
- ScriptWriter 仍沿用 BaseAgent 简化批处理路径（稳定可用）；如需统一 ReAct，可按现有模板迁移。

## 可观测性与运维
- 日志：统一打印 FC 计划摘要、`finish_reason`、内容预览、工具调用耗时、产物路径与错误类型。
- 进度：WebSocket 任务/Agent 进度上报与阶段事件；ContextAssembler/工具执行挂接监控指标（可扩展）。

## 风险与后续建议
- 策略最小暴露：当前 FC 暴露/参数策略偏保守（warn‑only），可基于运行数据逐步细化 per‑agent/per‑function 规则并引入阻断级别。
- ScriptWriter/ConceptPlanner 的 ReAct 统一：在稳定后考虑迁移以获得统一观测与复用（非必须）。
- MAS 主路径切换：当多 Agent 协同的复杂度与收益明确后，可逐步将主编排切换至 `app/core/mas_*` 架构。

---

如需我输出一份“按文件的变更导读（diff 要点）”或补充阶段用例与指标对比，请告知具体关注范围（Agent、Tool、Config 或测试）。

## 代码清理（本阶段执行）
- 删除备份文件：`app/agents/video_generator.py.bak`（未被任何位置引用）。
- 归档实验模块（防生产导入，文件头抛 ImportError）：
  - `app/agents/archive/react_concept_planner.py`（由 `app/agents/react_concept_planner.py` 迁入）
  - `app/agents/archive/supervisor_orchestrator.py`（由 `app/agents/supervisor_orchestrator.py` 迁入）
  - `app/agents/archive/agent_coordinator.py`（由 `app/agents/coordinator/agent_coordinator.py` 迁入）
- 脚本整理：将根目录便捷脚本迁入 `scripts/` 统一管理（不影响生产路径）
  - `extract_frame.sh` → `scripts/extract_frame.sh`
  - `extract_video_last_frame.py` → `scripts/extract_video_last_frame.py`
 - 测试归位：将 backend 根目录散落测试脚本归档至 `tests/` 体系
   - 集成测试：迁入 `tests/integration/`（API、连续性、FFmpeg、LLM 驱动、MAS 集成与记忆集成）
   - 端到端测试：`final_workflow_test.py` → `tests/e2e/test_final_workflow.py`

说明：上述三者当前未被生产代码或测试用例导入，仅在设计/分析脚本中出现文件名字符串；迁入 archive 不影响现有流程与测试。若后续需要启用，请按 ReAct/工具/配置化原则重构后再回迁生产路径。
