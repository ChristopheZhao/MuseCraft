# ReAct 轨迹完整性 + MAS 交付 SoT 对齐计划（含 audio_generator 重复迭代与 `last_action_result` 移除）

## 1. 背景（问题现象）

近期出现两个关联问题（并在日志中放大为“重复执行/重复生成”）：

1) `audio_generator` 在已成功生成背景音乐（BGM）后仍继续迭代（重复生成），造成额外成本与结果漂移。
2) ReAct 轨迹链路不稳定：OBS 可能丢失、或在上下文中转阶段被过滤，导致下一轮 PLAN 无法获知上一轮工具执行与产物事实。

此外还暴露出编排链路的另一个问题：

3) `quality_checker` 报错 `No video content available for quality check`，说明 `project.final_video` 未稳定交付或 orchestrator 未对“成片已产出”做门控就进入 QC。

## 2. 目标（Definition of Done）

面向 MAS 架构的目标不是“再写更多规则”，而是把事实源/交付路径对齐：

1) **ReAct 迭代 SoT = Agent WM（obs_records 轨迹）**
   - 下一轮 PLAN 能稳定看到上一轮“做了什么/结果是什么”（至少包含 URL/path 等产物索引）。
   - `build_agent_context` 只做通用搬运/可选窗口裁剪，不做字段硬编码挑选，不做“补资产/补 shared facts”。

2) **跨 Agent/全局交付 SoT = MAS WM（`scene_outputs.*` / `project.*`）**
   - 下游 agent（如 composer/QC）与 orchestrator 的调度/校验只依赖 MAS WM 的交付状态。
   - 不依赖 agent 的返回值作为全局交付事实源（agent_output 只是一份“回执”，不是 SoT）。
   - orchestrator 的“验收/重复调度/持久化 payload”均从 MAS WM 构建（facts-only）。

3) **移除 `ReActAgent` 的 `last_action_result` 作为隐式交付通道**
   - ReAct 基类不再用“上一轮 action_result 缓存”去拼装最终交付或影响退出路径。
   - 成功/失败/阻塞的输出应来自明确的合同（plan_contract）与 MAS WM 的交付事实（或显式的错误/阻塞原因）。

4) **audio_generator 不引入特例/补救式逻辑**
   - 不出现 `_extract_latest_background_music_from_obs` 这类“倒扒轨迹猜产物”的辅助函数。
   - 不在 agent 内硬编码“自动下载/自动落盘”；下载应作为 FC 可选能力由模型规划调用。

## 3. 现状与偏差分析

### 3.1 ReAct 轨迹的期望

ReAct 迭代需要一个可复用的轨迹事实链：

`{ act_1, obs_1, act_2, obs_2, ... }`

其中 `obs_i` 至少应包含：

- 当轮工具调用与成功/失败
- 产物索引（URL / 本地路径 / 关键元数据）

### 3.2 当前实现的关键偏差（已定位）

偏差 A：OBS 写入超预算时“整条不写”
- 位置：`backend/app/agents/utils/wm_obs.py:append_obs_to_wm`
- 现状（旧）：超预算直接跳过写入 → 轨迹断裂 → 下一轮 PLAN “失明”。

偏差 B：上下文中转层对 `obs_records` 做硬编码“摘要化”过滤
- 位置：`backend/app/agents/utils/context_manager.py:build_agent_context`
- 现状（旧）：白名单字段抽取，丢掉 `executed_calls.result / generation_results` 等承载产物的字段 → 下一轮 PLAN 看不到“产物是什么”。

偏差 C：交付路径 SoT 混用（agent_output ↔ MAS WM）
- 现状：部分产物（如 `scene_outputs.image/video/voice`）由 agent 在 ACT 后写入 MAS；但 BGM（`project.background_music`）却依赖 orchestrator 从 `agent_output` 写回。
- 风险：一旦出现“计划回合/空回合/收尾回合”的返回值为空（或被覆盖），MAS 就拿不到交付事实，进而下游无法消费。

偏差 D：ReAct 基类引入了 `last_action_result` 作为“隐式返回值兜底”
- 这会把“交付内容”与“控制流细节（是否执行过 noop/是否覆盖过缓存）”绑定到一起。
- 对 MAS 架构而言，这属于边界混乱：交付应由 MAS WM 统一承载，而不是由基类的内部缓存决定最终回执内容。

偏差 E：音频生成工具通常只返回 URL
- 例如 `suno_client.generate_background_music` 返回 `audio_url`，不保证 `audio_path`。
- 若下游混流要求本地路径，则必须提供“下载/落盘”能力，并且作为可选工具由 FC 规划调用（而不是 agent 内硬规则补齐）。

偏差 F：composer/QC 门控不严格
- QC 报错说明 `project.final_video` 未交付或未稳定。
- orchestrator 需要以 MAS WM 的 `project.final_video` 为门控条件：没成片就不应进入 QC；必要时应重复 composer 或中止并输出明确诊断。

## 4. 根因分析（从机制层到架构层）

根因 1：ReAct trajectory 事实链不可用（写入断链 + 消费侧过滤）
- 导致：下一轮 PLAN 无法基于事实做“复用/停止”，进而重复生成。

根因 2：交付 SoT 没有完全落在 MAS WM
- 导致：即便 agent 内部能看见轨迹事实，编排层/下游仍可能看不见交付物（因为它们只看 MAS）。

根因 3：ReAct 基类存在“控制流 → 返回值”耦合
- 导致：计划回合/收尾回合若产出空结果，可能把交付回执清空；随后 orchestrator 写回 MAS 失败或下游读取不到。

## 5. 修复思路（分阶段，先对齐 SoT 再删缓存）

### Phase 0：巩固 ReAct 轨迹链（已完成/已在执行）

目标：保证下一轮 PLAN 能看到上一轮工具结果（URL/path）。

- OBS 超预算不再整条丢弃，改为通用截断后写入，并带 meta。
- `build_agent_context` 不再做字段白名单过滤，只做通用 JSON 化（可选窗口截断）。

### Phase 1：把“交付事实”落到 MAS WM（统一 SoT）

目标：让 orchestrator/下游只读 MAS WM 就能判断“交付物是否存在”，不依赖 agent_output 的偶然字段。

建议动作：

1) 为 audio_generator 定义稳定的 MAS 交付槽位（建议二选一或组合）：
   - `project.background_music`（项目级 BGM 指针，包含 url/path/metadata）
   - `scene_outputs.audio`（若任务本质是分场景音轨，则应写入此 bucket；schema 已存在）

2) 统一“写入时机与边界”：
   - 写入发生在工具执行后、且结果已被规整为 primitives（契约边界）。
   - 不从 Agent WM 倒扒/猜测写入；写入应来自当轮工具返回的结构化结果（或由 orchestrator/写入器直接接收该结构化结果）。

3) composer 读取只依赖 MAS：
   - composer 混流读取 `project.final_video` + `project.background_music`（或 `scene_outputs.audio`）的 path/url。
   - 若只有 URL 且需要本地文件，下载/落盘通过工具能力在 composer 或 audio_generator 中由 FC 规划调用。

### Phase 2：收敛 orchestrator 与 agent 的交付接口

目标：orchestrator 不再“特判某个 agent_output 字段是否存在才写入”，而是：

- 以 MAS WM 为唯一交付 SoT（写入/读取得到一致结论）。
- agent_output 只返回：本轮状态/诊断/引用（可选），不作为 SoT。

（实现上可选择“orchestrator 统一写 MAS”或“agent 在 ACT 后写 MAS”，但必须统一并可审计，避免两套并存。）

落地形态（本轮实现）：
- 新增 `backend/app/agents/adapters/state/agent_outputs.py`：集中定义 agent→MAS key 映射与 deliverables 评估（facts-only）。
- orchestrator 的策略判定/LLM 建议输入/持久化 payload 均改为读取 MAS WM（不再消费 `agent_output.generation_results` / `agent_output.subtask_state`）。

### Phase 3：移除 `ReActAgent.last_action_result`

前提：Phase 1/2 完成后，成功交付应已在 MAS WM，基类不需要靠缓存兜底返回值。

移除点：

- 删除 `ReActAgent._execute_impl` 内对 `last_action_result` 的维护与传递。
- `_finalize_success_results/_finalize_incomplete_results` 不再接收/依赖 last_action_result。
- 对“计划回合 task_complete=true”的退出：
  - 以 plan_contract 为控制流依据退出；
  - 最终输出从 MAS WM 聚合（或返回最小成功回执），而不是拼接“上一轮 action_result”。

### Phase 4：删除 audio_generator 的补救式实现

在 Phase 1/2/3 后，下列逻辑应删掉（或迁移到通用 util/写入器）：

- `_extract_latest_background_music_from_obs`
- 覆写 `_finalize_success_results/_finalize_incomplete_results` 的“倒扒 obs 兜底”

audio_generator 应保持“plan/act/obs/reflect 最小闭环”，与 image/video/voice 对齐。

### Phase 5：补齐 composer/QC 的门控与诊断

- orchestrator 在进入 `quality_checker` 前必须验证 MAS `project.final_video` 存在。
- 若不存在：重复 composer（在预算内）或中止并输出明确根因（而不是让 QC 报错掩盖上游问题）。

## 6. 计划执行清单（按优先级）

### P0（尽快完成，稳态基础）

- [x] `append_obs_to_wm`：超预算写入改为“截断后写入”（不断链）
- [x] `build_agent_context`：移除硬编码字段过滤（保证产物细节进入下一轮 PLAN）
- [x] `_truncate_action_result`：占位符替换改为通用截断（尽量保留 url/path）

### P1（对齐 MAS SoT：audio 交付）

- [x] 明确 BGM 的 MAS 交付结构：使用 `project.background_music`（项目级 BGM 指针）
- [x] audio_generator：在工具执行结果规整后，将交付事实写入 MAS（`project.background_music` + 可选 artifacts 回执）
- [x] orchestrator：移除依赖 `agent_output.background_music` 的特判写回（改为校验 MAS SoT）

### P2（移除 last_action_result）

- [x] ReActAgent：移除 `last_action_result`（含 finalize/incomplete 分支），把“最终交付内容”迁移为“从 MAS 聚合或最小回执”
- [x] 为计划回合退出增加可审计事件记录（写入 obs_records 的 event）

### P3（删补救逻辑，回归最小 agent）

- [x] audio_generator：删除 `_extract_latest_background_music_from_obs` 与 finalize 兜底逻辑
- [ ] 检查其它 agent 是否存在类似“倒扒 WM 兜底交付”的实现，统一处理

### P4（composer/QC 稳定性）

- [x] orchestrator：进入 QC 前门控 `project.final_video`；缺失时重复 composer 或 fail fast
- [x] composer：产出必写 `project.final_video`（URL/path）并可供 QC 读取

### P5（测试与回归）

- [x] 增加单测：`obs_records` 中必须保留 tool result 的 url/path（覆盖 “超预算截断仍保留关键字段”）
- [ ] 增加单测：audio 两轮（生成 URL → 下载落盘）时，第二轮 PLAN 能看到第一轮产物 URL
- [ ] 增加单测：没有 `project.final_video` 时 orchestrator 不进入 QC
