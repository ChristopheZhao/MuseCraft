# Stage 3.6 报告：迭代记忆单通道收敛与 OBS 重构计划

本阶段目标：把 Agent 的“迭代记忆”读写收敛成一条可审计通道，消除多路状态，降低调试与定位成本；同时将 OBS（本轮事实观察）规范为“WM 事实 + 本轮执行事实摘要”的单一回合载荷。

## 背景与症状
- 既有实现中，Agent 同时使用 ensure/get_optional/iteration_context 等多条路径访问或携带工作状态；测试与线上日志显示：
  - ReActAgent/子 Agent 混用 `iteration_context` 承载“控制态”，并与 OBS/事实交织，导致来源不清；
  - 迭代记忆（WorkingMemory）既可在 Agent 内隐式创建，又在 Orchestrator 外部创建，生命周期不一致；
  - 事实与控制态混放，出现风格丢失、状态难以重现等问题。

## 决策与约束（关键原则）
- 迭代记忆单通道：
  - 读：`self.wm`（未初始化抛错；由 Orchestrator 统一 `create_or_get`）；
  - 写：`memory_write(apply_patch, ...)`（服务层统一审计 MEM_WRITE），或通过 WM 领域方法（同样经服务封装）。
- OBS 仅作为回合载荷：
  - 内容 = WM 事实快照 + 本轮 ACT 执行事实摘要（act_summary/react_metrics/act_log/iteration）；
  - 不写回 WM；不混入推断/话术；允许如实记录“本轮用了哪些工具/动作/参数摘要（digest）”。
- Orchestrator 统一记忆生命周期：在调度某 Agent 前 `create_or_get`，workflow 收尾 `cleanup_workflow`。
- 移除 `iteration_context`：Agent 不再持有“控制态字典/容器”；回合间仅传 obs 这一份载荷。

## 已完成改动（2025-11-06）
1) 记忆服务（CRUD + 审计）
   - 新增接口：`create_or_get/get/delete/cleanup_workflow/memory_write`。
   - 文件：`backend/app/agents/memory/iteration/service.py`

2) Orchestrator 统一创建与清理
   - 执行前 `create_or_get`、收尾 `cleanup_workflow`（新增别名以兼容）。
   - 文件：`backend/app/agents/orchestrator.py`

3) BaseAgent 收敛记忆读写
   - 读：`self.wm`；写：`memory_write(...)`；工具合约写槽改走 `memory_write`（审计）。
   - 文件：`backend/app/agents/base.py`

4) 各 Agent 改用 `self.wm`
   - Image/Video/Audio/Voice/ReAct：主要路径替换 ensure/get_optional → `self.wm`；快照从 `self.wm` 读取，取不到降级为无快照。
   - 代表性文件：
     - `backend/app/agents/image_generator.py`
     - `backend/app/agents/video_generator.py`
     - `backend/app/agents/audio_generator.py`
     - `backend/app/agents/voice_synthesizer.py`
     - `backend/app/agents/react_agent.py`

5) 测试修正
   - `backend/tests/integration/test_image_react_memory_flow.py` 读取 `agent.wm`。

## 遗留问题（必须解决）
- ReActAgent/子 Agent 仍有对 `iteration_context` 的读写（用于“控制态”）；当前仅保留一个兼容层防崩溃，不符合无状态目标。
- 部分 Agent 在 OBS 内混入控制字段（如 last_action/metrics/aug/notes）；需清理为“WM 事实 + ACT 摘要”。
- 旧接口 `ensure/get_optional` 尚未彻底移除（少量引用；archive 目录可暂缓）。

## 下一阶段（M2）：彻底移除 iteration_context 与 OBS 收敛
1) ReActAgent：改为“obs 单载荷”贯穿回合
   - `_execute_impl`：
     - OBSERVE：`obs = build_observation_from_wm(self.wm, iteration)`；
     - THINK/PLAN：用 obs 作为输入，不泄漏工具实现细节；
     - ACT：执行工具，产出 `executed_calls` → `derive_action_facts(...)`（`act_summary/react_metrics/act_log`）→ `obs = merge(obs, action_facts, iteration+1)`；
     - REFLECT：依据 `obs + action_result` 决策是否继续；不写内部状态。
   - 删除所有 `self.iteration_context[...]` 的读写（iteration_history/cumulative_results/metrics/last_action 等）。

2) 各 Agent 的 OBS 收敛
   - `_observe_current_state` 仅返回 WM 事实视图（scenes/completed/failed 等），不写 WM、不注入控制字段；
   - memref 解引用放在执行前（预处理）完成；不在 OBS 展开大字段。

3) 删除兼容层与旧接口
   - 删除 `BaseAgent.iteration_context` 兼容 getter/setter；
   - 删除 `ensure_iteration_memory/get_iteration_memory_optional`（archive 目录之外）。

## OBS 结构建议（收敛后）
- 必含：
  - `iteration: int`
  - `scenes: [{scene_number, depends_on_scene, duration, status, failure_reason?, retries?}]`
  - `completed_scene_numbers: [int]`
  - `failed_scene_numbers: [int]`
  - `act_summary: { planned_calls, executed_calls, success, fail, affected_scenes, duration_ms }`
  - `react_metrics: { planned_calls, executed, success, fail, artifacts }`
- 可选：
  - `act_log: [{ tool, action, args_digest, result_digest, scene_number?, success, duration_ms }]`
  - `timeline: [...]`（若可从 WM/Shared WM 推导）
- 不包含：
  - 推断/话术/自由文本总结；敏感密钥/完整入参；非事实性偏好。

## 审计与日志规范
- 迭代记忆写入：统一 `MEM_WRITE`（workflow/agent/op/keys/version/err）。
- 回合日志：
  - `OBS_BEFORE`（scenes/完成/失败计数）；
  - `ACT_FACTS`（act_summary/受影响场景/耗时）；
  - `OBS_AFTER`（合并后的计数）。

## CI/静态检查（M3 引入）
- 禁止新增：`iteration_context[...]`、`ensure_iteration_memory`、`get_iteration_memory_optional`；
- OBS 构建函数禁止 `memory_write`；
- （可选）对 obs 文本做关键词扫描，防止泄漏敏感密钥。

## 完成定义（DoD）
- 代码中不再有任何 `iteration_context` 的读写；
- Agent 仅用 `self.wm/memory_write` 访问迭代记忆；
- OBS 仅包含 WM 事实与本轮 ACT 摘要；
- Orchestrator 统一 `create_or_get/cleanup_workflow` 工作正常；
- 集成路径通过：Concept → Image → Video/Voice → Composer → Audio。

## 时间线与执行
- M2（移除 iteration_context + OBS 收敛）：
  - ReActAgent：2 天；
  - Image/Video/Audio/Voice 收敛：2–3 天；
  - 删除旧接口与回归：1 天。
- M3（审计增强 + CI + 文档）：1–2 天。

## 附：本阶段关键变更索引
- 记忆服务：`backend/app/agents/memory/iteration/service.py`
- 基类（wm/memory_write/合约写槽）：`backend/app/agents/base.py`
- 调度：`backend/app/agents/orchestrator.py`
- Agent（代表性）：
  - `backend/app/agents/image_generator.py`
  - `backend/app/agents/video_generator.py`
  - `backend/app/agents/audio_generator.py`
  - `backend/app/agents/voice_synthesizer.py`
  - `backend/app/agents/react_agent.py`
- 快照：`backend/app/agents/utils/progress_snapshot.py`
- 测试：`backend/tests/integration/test_image_react_memory_flow.py`

