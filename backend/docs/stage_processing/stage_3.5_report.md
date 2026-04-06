# Stage 3.5 Progress Report

## 1. 概览
- **时间窗口目标**：对“视频工作流缺风格”问题进行根因排查，同时对 agent 自主化、工具记忆解耦、规则剥离等核心改造主题做信息补全。
- **上下文状态**：会话因多次调试与日志粘贴造成上下文超长，IDE 已出现明显卡顿，本轮以整理信息和定位下一阶段任务为主。

## 2. 已完成 / 现有改动总览
根据当前工作区 `git diff --stat`，本窗口延续的代码改动集中在以下几类：

1. **Agent 架构大重构（多文件）**  
   - `backend/app/agents/*.py` 大量增删，包括 `base.py`、`react_agent.py`、`video_generator.py`、`image_generator.py`、`audio_generator.py`、`video_composer.py`、`voice_synthesizer.py`、`script_writer.py`、`quality_checker.py` 等。  
   - 核心方向：引入统一的 ReAct 基类、重写执行循环、增加阶段化上下文注入、扩展工具执行摘要等。  
   - 多个 Agent 的 prompt 模板与系统 prompt (`backend/app/config/prompts/agents/*.yaml`、`style_elements_generation.jinja2`) 也同步调整，以匹配新的自主化流程。

2. **工具体系与服务层改造**  
   - `backend/app/agents/tools/` 新增/修改大量模块：包含 provider 适配、`tool_registry`、`manager`、`consistency_tool` 以及各 AI 服务工具的新版实现。  
   - 新增 `backend/app/agents/services/` 下的工具服务封装。  
   - `backend/scripts/test_fc_prompt_*.py` 等调试脚本同步调整，支持新的工具暴露方式。

3. **记忆系统解耦与上下文装载**  
   - 新增完整的 `backend/app/agents/memory/` 目录（coordinator、managers、working_memory、slots、iteration、exporter 等），配套配置文件 `backend/app/config/context_editor_schema.yaml`、`context_editor.yaml`、`observation_compression.yaml`。  
   - 引入 `backend/app/memory_utils.py`、`backend/app/core/obs_strategy.py` 等，支撑 ContextAssembler/MemoryWriter 的新架构。

4. **服务与持久化层更新**  
   - `backend/app/services/data_persistence.py`、`global_memory_service.py` 等新增或扩展，配合记忆解耦与工具调用记录。  
   - `backend/scripts/start_dev_uv.py`、`.gitignore` 等基础脚本/配置也做了相应调整。

5. **测试体系扩充**  
   - 新增/更新大量单元与集成测试（`backend/tests/unit/*`、`backend/tests/integration/*`、`backend/tests/e2e/*`）。  
   - 特别新增针对记忆协调、工具契约、React 链路等的测试文件，例如 `test_memory_coordinator.py`、`test_slot_registry.py`、`test_tool_contracts.py`、`test_image_generator_react_chain.py` 等。

6. **本窗口新增的定位工具**  
   - `backend/scripts/run_concept_agent.py`：补充运行示例、说明与环境变量清理逻辑，方便快速验证 ConceptPlanner 输出。  
   - `backend/tests/integration/test_concept_planner_live.py`：新增真实 LLM 集成测试，最小 stub 执行 Agent 并断言风格区块存在。  
   - `backend/docs/stage_processing/stage_3.5_report.md`：撰写本阶段进展总结，便于后续窗口衔接。

## 3. 时间轴回溯
1. **视频 Agent 缺陷复盘**  
   - 依据历史日志复盘：ACT 阶段会重复执行 `video_prompt_builder`、`consistency_tool` 等 plan 工具，真实视频生成推迟到第 6 轮才触发；同时 `_integrate_generation_results` 出现 `SceneArtifact` 未导入报错。  
   - 当前仓库尚未合入成熟修复，依旧暴露混合工具集合；需要在后续迭代中以策略/配置方式根治，而非再靠临时过滤。
2. **ConceptPlanner 产出验证**  
   - 阅读日志确认 `intelligent_style_design` 保存成功。  
   - 调整 `backend/scripts/run_concept_agent.py`，补充示例、自动清除 `NEXT_PUBLIC_*` 变量，便于复现。  
   - 新增 `backend/tests/integration/test_concept_planner_live.py` 进行真实 LLM 集成断言（需 `LIVE_AGENT_TESTS=1`）。
3. **环境变量问题修复**  
   - pytest 早期导入 `Settings()` 导致前端 `NEXT_PUBLIC_*` 变量触发校验错误。  
   - 现已拆分前后端 `.env` 并验证通过，报告中记录根因与预防策略。
4. **当前瓶颈**  
   - ImageAgent 仍偶发拿不到风格；缺乏证据指向具体丢失环节。  
   - 会话上下文过长导致进一步调试成本过高，决定在此节点整理阶段报告。

## 3. 核心主题进度
### 3.1 Agent 自主化改造
- **现状**：视频 Agent 仍暴露 plan 与 act 混合工具，导致 LLM 在执行阶段反复调用准备类工具；仓库内暂无彻底修复。  
- **差距**：未落实“工具曝光由策略/配置决定、ReAct 自主规划执行”的目标；需要回归 `agent_tool_allocation` 与 ToolRegistry 的配置化控制，并为阶段性决策提供 declarative 策略。  
- **后续方向**：  
  1. 设计阶段化工具曝光表，由配置驱动 LLM 可见工具集合；  
  2. 为阶段策略增加测试（包括“plan-only”迭代），确保自主化流程可回归验证；  
  3. 对 video/image agent 的 ReAct 循环添加阶段完成判定 telemetry，以便定位空转。

### 3.2 工具与记忆解耦
- **现状**：ConceptPlanner 调试脚本与 live 测试均直接依赖 MAS 内的真实 Memory 服务；尚无独立的 memory adapter。  
- **差距**：脚本/测试无法在无 MAS 环境下运行，违背“工具能力独立可测”的原则。  
- **后续方向**：  
  1. 抽象 memory API（读取/写入 slot 与 shared facts），供脚本与测试通过注入 mock/真实实现切换；  
  2. 为 Memory 工具增加最小单测，确保风格数据持久化后可被独立验证；  
  3. 审查 ImageAgent 的 memory 读取流程，确认是否存在依赖具体 MAS 状态的假设。


## 4. 当前阻塞与排查线索
- **ImageAgent 风格缺失**：概念规划阶段确认写入成功，但在图像阶段消失，推测可能是 ContextAssembler/WorkingMemoryAssembler 的过滤或 workflow state 变更导致。需要进一步的单步脚本或增强日志。  
- **Live 测试依赖**：`test_concept_planner_live.py` 需真实 LLM 与密钥，暂不适合在 CI 默认执行，后续需设计专用测试配置或金丝雀策略。  
- **上下文长度问题**：当前窗口多次紧凑/截断导致性能下降，需要在新会话继续剩余排查，避免信息进一步丢失。

## 5. 下一步行动建议
1. **运行 live 测试收集证据**：在拥有模型密钥的环境执行  
   `LIVE_AGENT_TESTS=1 uv run pytest backend/tests/integration/test_concept_planner_live.py -k style_block`，保存输出以供对比。  
2. **梳理工具曝光配置**：设计阶段化工具策略，收敛为配置驱动的工具曝光，并补充测试覆盖。  
3. **定位 ImageAgent 中的记忆读取链路**：添加暂存日志或独立脚本，对比 ConceptPlanner 写入前后的 memory 内容，查明风格信息丢失点。  
4. **规划 Memory 工具化接口**：定义脚本/测试可复用的 Memory API，确保 agent 行为在“真实服务 / 本地 mock”之间可切换。  
5. **准备规则剥离方案**：整理 orchestrator 各阶段的规则清单，为后续状态驱动改造提出具体迁移步骤。

> 备注：本阶段对话上下文已多次压缩，IDE/CLI 性能下降明显，建议在新的会话继续执行上述下一步计划，以保证信息完整与工具响应速度。
- 当前排查聚焦：ImageAgent 在准备资产时读到的 `style` 为空。沿链路追踪发现 ConceptPlanner 输出同样缺失该字段，因此编写 `backend/scripts/run_concept_agent.py` 与对应 live 测试，用于验证 ConceptPlanner 是否真的是在源头就返回空 style，确认后再定位写入/读取记忆的环节。
