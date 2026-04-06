标题: Agent WM 生命周期边界问题分析与修复计划
状态: 草案
范围: orchestrator.py / base.py / react_agent.py / context_manager.py / memory_helpers.py / short_term/service.py

## 问题表述
- 在同一 workflow 内，video_composer 被调用两次（一次合片，一次 add_bgm）。
- 第二次调用出现 `build_agent_context failed: Working memory not initialised`，随后 LLM 仅判断“已有成片，无需合成”，导致 `mix_type_mismatch`。
- 误解点：该 warning 仅代表 Agent WM 缺失，和 MAS 的 static_context 无关。

## 现象链路
1) Orchestrator 在 add_bgm 分支先创建 composer 的 Agent WM。
2) 进入 BaseAgent.execute 时立刻 `reset_iteration_memory_cache(invalidate=True)`。
3) 这一步用旧的 workflow_state_id + agent_scope 删除了刚刚创建的 Agent WM。
4) ReAct 进入 build_agent_context 时读取不到 Agent WM，warning 出现，iteration_context 为空。
5) LLM 在缺少迭代上下文时倾向于判断“已有成片，无需合成”，导致 add_bgm 未执行工具调用。

## 根因分析
- 生命周期归属冲突：
  - Orchestrator 负责创建 Agent WM。
  - Agent 入口又主动 invalidate，导致刚创建的 WM 被删除。
- Scope 设计不支持多次调用：
  - Agent WM scope = agent:{workflow_id}:{agent_name}，同一 agent 在同一 workflow 内二次调用会复用或互相影响。
- “第一轮空 WM”被误实现为“WM 不存在”：
  - 第一轮本应是空的 iteration_context，但 WM 必须存在以承接 obs_records/memref。

## 偏差分析
- 设计意图：
  - MAS WM 是跨 agent 的唯一事实源，由 orchestrator 读取构建 static_context。
  - Agent WM 应为 per-call 临时工作区，仅服务本次 ReAct 迭代。
- 实现偏差：
  - Agent WM 被 create_or_get 幂等复用，缺少 per-call 边界。
  - Agent 自行 invalidate 与 orchestrator 创建职责冲突，导致不可预期的 WM 缺失。

## 修复思路
- 明确职责边界：
  - Agent WM 生命周期由 orchestrator 统一管理。
  - Agent 只清本地 cache，不做 invalidate。
- 保障 per-call 语义：
  - 每次调用前由 orchestrator reset + create，确保空 WM。
- 避免误诊：
  - add_bgm 分支增加 static_context 关键字段日志，区分“static_context 缺失”与“iteration_context 为空”。

## 行动计划清单（含优先级）
P0
1) BaseAgent.execute 只清本地 cache，不再 invalidate（移除 invalidate=True）。
2) Orchestrator 每次调用 agent 前显式 reset scope，再 create_or_get（确保空 WM）。
3) add_bgm 分支加入静态上下文关键信息日志（requests + background_music）。
4) add_bgm 分支增加上下文核验日志：确认 background_music.audio_path / audio_url 是否存在，确认 composer 的请求标志（bgm_requested）是否明确。
5) add_bgm 分支注入明确 task 指令，强调“必须混入背景音乐并输出新成片”。

P1
1) 补充文档：区分 static_context 与 iteration_context 的职责与来源，避免后续误诊。

P2
1) 增加回归验证清单：
   - 单次执行 + add_bgm 不再出现 WM not initialised。
   - composer 第二次调用能执行混音，mix_type = bgm。
   - Agent WM 空但存在，iteration_context 空不报错。

## 验证标准
- add_bgm 调用时无 `Working memory not initialised` warning。
- composer 在 add_bgm 中触发混音工具调用，MAS 中 `project.final_video_mix.mix_type` 为 `bgm`。
- 静态上下文日志显示 background_music 可用时，任务不应被判定为“无需合成”。
