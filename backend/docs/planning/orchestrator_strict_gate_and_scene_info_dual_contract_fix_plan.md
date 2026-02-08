# Orchestrator 严格门控与 Scene Info 双形态契约修复计划

状态: Draft  
范围: `backend/app/agents/orchestrator.py` + Prompt/Tool schema + 相关测试

## 背景

当前链路中存在两个需要对齐的核心点：

1. 任务分解（Orchestrator plan）是 MAS 主控能力，失败后不应以“伪规划”继续执行高成本生成链路。
2. `scene_info_ref` 的目标是降低上下文体积，但 `scene_info_payload` 仍有兼容价值；两者需要被定义为显式双形态契约，而不是隐式 fallback。

## 决策（已确认）

### 1) 任务分解严格门控（Fail Fast）

- Orchestrator 的任务分解失败时，仅允许有限重试（临时错误）。
- 重试后仍失败：直接报错终止，不再用 `_build_fallback_task` 替代核心规划。
- 目的：避免基于劣质/缺失计划触发高成本视频生成，降低成本与错误放大风险。

### 2) `conditional_tasks` 改为“条件必需”

- `video_composer_bgm_mix` 仅在“确实会触发 composer BGM 混入路径”时必需。
- 不触发该路径时，不因缺少该 conditional task 失败。
- 目的：保证二次 composer 调用有预规划任务说明，同时避免对无关流程施加硬约束。

### 3) `scene_info_ref` / `scene_info_payload` 双形态显式契约

- 允许二选一输入：
  - `scene_info_ref`: 引用路径（默认优先）
  - `scene_info_payload`: 内联 payload（兼容输入）
- 同时提供时：优先使用 `scene_info_ref`。
- `scene_info_payload` 必须经过结构校验与体积上限校验，超限直接报错。
- 目的：保留兼容性，同时保持“引用优先、降 token 成本”的主路径。

## 代码改造计划

### A. Orchestrator 规划门控

文件: `backend/app/agents/orchestrator.py`

1. 为 `_llm_decompose_tasks(...)` 增加有限重试包装（仅临时错误）。
2. 删除主执行循环中对 `_build_fallback_task(...)` 的自动补齐路径。
3. 若某 agent 需执行但缺少 `task_spec`：直接抛 `AgentError`。

### B. conditional task 条件校验

文件: `backend/app/agents/orchestrator.py`

1. 提取 `requires_bgm_mix_task(...)` 判定逻辑。
2. 仅在需要走 BGM composer 分支时校验 `video_composer_bgm_mix` 存在。
3. 该分支继续仅消费预规划 task spec，不在执行期临时拼接任务。

### C. Scene Info 双形态 schema 与读取逻辑

文件:
- `backend/app/agents/tools/image_prompt_composer_tool.py`
- `backend/app/agents/tools/video_prompt_composer_tool.py`
- `backend/app/agents/tools/consistency_tool.py`
- `backend/app/agents/tools/video_prompt_builder_tool.py`
- `backend/app/agents/orchestrator.py`

改动点：

1. 动作 schema 定义为 `oneOf`：`scene_info_ref` 或 `scene_info_payload`。
2. 工具内统一入口：
   - 若 `scene_info_ref` 可用 -> 读取 ref；
   - 否则使用 `scene_info_payload`；
   - 两者都无 -> 校验失败。
3. 为 payload 增加：
   - 必填结构键校验（例如 `task_type`、`scenes_to_generate` 等按工具场景定义）
   - JSON 字节大小上限（配置化）
4. 在关键日志中输出 `context_source=ref|payload`。

### D. 错误透明性修正

文件:
- `backend/app/agents/orchestrator.py`
- `backend/app/agents/tools/video_processing/scene_continuity_preparation_tool.py`
- `backend/app/agents/tools/ai_services/video_generation_tool_v2.py`

改动点：

1. `add_bgm` 先决条件检查中的内部异常不再吞并为“资源缺失跳过”。
2. 连续性上传失败与连续性抽取失败路径保持可观测，不静默掩盖根因。

## 回归测试计划

### P0

1. 任务分解失败重试后终止（不走 fallback task）。
2. 将执行 agent 缺少 `task_spec` 时直接失败。

### P1

1. `video_composer_bgm_mix` 在需要 BGM 分支时必需；不需要时不强制。
2. `scene_info_ref/payload` 二选一输入验证：
   - 仅 ref 成功
   - 仅 payload 成功
   - ref + payload 同时存在时优先 ref
   - payload 超限失败

### P2

1. `add_bgm` 与连续性路径的错误透明性断言（日志/错误码/异常类型）。

## 验收标准

1. 核心规划失败不再触发高成本下游生成。
2. 二次 composer 调用有预规划 task 支撑，且仅在需要时校验。
3. scene info 输入契约清晰且兼容，引用优先，payload 受控。
4. 关键失败场景可定位根因，不被“缺资源”类分支掩盖。

