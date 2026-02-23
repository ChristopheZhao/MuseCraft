标题: Orchestrator Allocate-First 子Agent池改造计划（本轮）
状态: Draft
范围: orchestrator 分配逻辑 + composition_tool 音轨事实校验 + 回归测试

## 1. 目标
- 将本次执行从“固定顺序 + 中途大量 skip”收敛为“前置分配 active_agents + 执行期最小硬门控”。
- 不改各子 Agent 的 ReAct 迭代实现，不引入 agenda 动态调度。
- 修复 capability-only 导致的音频回归：`audio_generator` 误跳过、`preserve_audio` 误开启。

## 2. 边界（本轮不做）
- 不重构 `workflow_order` 为 agenda/task graph。
- 不调整子 Agent 内部 plan/act/reflect 流程。
- 不新增面向单一模型的硬编码分支。

## 3. 现状问题
- 主执行仍固定遍历 `workflow_order`，业务选择大量依赖 `_should_run_agent` 中途门控。
- `AUDIO_GENERATOR` 的启停受 provider capability 影响过重，缺少运行时事实校验。
- `composition_tool.preserve_audio` 默认值依赖 capability，未校验当前 clip 是否真实含音轨。

## 4. 实施方案
### 4.1 前置分配（Allocate-First）
- 在 orchestrator 启动后、主循环前新增分配步骤：
  - 输入：任务需求、provider capability、task_specs。
  - 输出：`workflow.execution_plan`（写入 MAS）：
    - `active_agents`
    - `skipped_agents`
    - `reasons`
    - `required_conditional_tasks`
- 主循环执行顺序改为：`active_workflow_order = workflow_order ∩ active_agents`。

### 4.2 执行期门控收敛
- `_should_run_agent` 保留最小硬保障：
  - 关键交付缺失
  - 明确失败补偿路径
  - 质量/完整性强约束
- 业务性“是否执行某Agent”优先前移到 allocate 阶段。

### 4.3 音频事实优先（修复回归）
- `composition_tool` 在 `compose_story_video` 前探测 scene clips 音轨事实（调用 `ffmpeg_tool.get_video_info`）：
  - `clip_audio_presence`
  - `has_audio_any`
  - `has_audio_all`
  - `first_clip_has_audio`
- `preserve_audio` 默认决策改为事实驱动（显式参数优先）。
- orchestrator 的 `AUDIO_GENERATOR` 启停改为 runtime facts 优先，capability 仅作先验。

## 5. 分提交计划
### Commit A
- `refactor(orchestrator): add allocate-first execution plan contract`
- 文件：`backend/app/agents/orchestrator.py`
- 验收：MAS 中有 `workflow.execution_plan.active_agents`。

### Commit B
- `refactor(orchestrator): execute active agent pool over workflow order`
- 文件：`backend/app/agents/orchestrator.py`
- 验收：主循环不再执行未入池 agent。

### Commit C
- `fix(composition): resolve preserve_audio by runtime clip-audio facts`
- 文件：`backend/app/agents/tools/video_composition/composition_tool.py`
- 验收：无音轨 clip 时默认不保留音轨；日志可见决策依据。

### Commit D
- `fix(orchestrator): gate audio_generator by runtime audio evidence`
- 文件：`backend/app/agents/orchestrator.py`
- 验收：provider 声称支持音频但 runtime 无可用音轨时，仍触发 audio_generator。

### Commit E
- `test(orchestration): cover allocate-first and audio-fact regressions`
- 文件：`backend/tests/unit/`（必要时 `backend/tests/integration/`）
- 验收：覆盖至少以下场景：
  - provider 覆盖能力下 voice/bgm 不入池；
  - 严格配音需求下 voice 入池；
  - capability=true 但 runtime 无音轨时触发补偿。

## 6. 验收标准
- 本次 workflow 仅执行 `active_agents`。
- 执行期业务跳过规则明显减少，门控职责收敛。
- 解决已发现音频回归，不再产出“能力上支持但结果静音”的错误路径。
- 不影响现有子 Agent ReAct 迭代逻辑。

## 7. 风险与回滚
- 风险：allocate 误判导致 agent 漏执行。
- 缓解：记录 `execution_plan.reasons` + 单测矩阵 + 一次补偿路径。
- 回滚：按提交粒度回退，优先回退 Commit B/D。
