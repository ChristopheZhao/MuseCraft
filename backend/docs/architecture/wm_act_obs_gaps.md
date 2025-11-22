# WorkingMemory 与 ReAct 迭代记录的偏差与修正方案

## 正确目标
- **OBS/ACT 都要落 WM**：每轮结束，将 `{action: ..., observation: ...}` 追加到工作记忆（私域 WM），跨轮可复用；MAS WM 只暴露结构化事实（`scene_outputs.*` 等）。
- **受控容量**：迭代历史/事件用 deque+上限，必要时摘要/裁剪，避免提示膨胀。
- **统一钩子**：Base/ReactAgent 负责统一写入，Agent 不再各自拼写；上下文读取也统一从 WM 摘要。

## 当前偏差（现行代码）
- Base/ReactAgent 的 ACT/OBS 流程仅返回 `executed_calls`，未将每轮 act→obs 摘要写入 WM（`iteration_history` 缺失）。
- WorkingMemory 被当成“产物缓存”（`scene_outputs.*`），未承载迭代足迹；`iteration_artifacts` 用得少，`iteration_history` 字段不存在。
- ImageGenerator 等有 `obs_event` 构造但未写入 WM，属于孤立逻辑。

## “产物优先”现状的不足
- **失忆风险**：只有产物没有 act/obs 足迹，Agent 无法基于过往决策（成功/失败、调用过哪些工具）调整策略，容易重复调用或误判。
- **协作缺口**：下游 Agent 只能看到产物，无法获知前序步骤的异常/尝试，跨 Agent 协作缺少上下文（除产物外的状态）。
- **调试困难**：缺少结构化的迭代记录，问题诊断只能靠日志，无法从 WM 直接还原决策路径。
- **记忆价值弱化**：WM 退化为产物缓存，短期记忆的本意（跨轮可复用的迭代事实）无法发挥。

## 改进方案
1) **WM 模型扩展**：
   - 增加 `iteration_history: Deque[Dict[str, Any]]`，提供追加型接口 `append_iteration_record(action_summary, observation_summary)`，内部做 maxlen 控制，支持后续裁剪/摘要策略。
   - 保留 `iteration_artifacts` 但区分职责：artifacts 存产物，history 存 act/obs 摘要；都应通过追加型 API 写入，避免 Agent 直接 put 原始结构。
2) **统一写入钩子（Base/ReactAgent）**：
   - 在 ACT/OBS 结束后统一构造摘要（工具名/scene/成功与否/关键信息 + obs 关键字段）并写入 `self.wm` 的 history；容量受控。
   - 允许注入摘要构造函数（方便不同 Agent 增补特定字段）。
3) **上下文读取**：
   - OBSERVE 阶段从 WM 读取裁剪后的迭代历史/近期 artifacts 作为决策依据，不依赖临时变量或旧 slot。
4) **产物写回继续**：
   - `persist_scene_outputs` 继续双写（私域+MAS），但不替代迭代历史。
5) **清理孤立逻辑**：
   - 移除/合并各 Agent 内未落地的 `obs_event` 等自定义写法，改用统一钩子。

## 落地子任务列表
- **A. WorkingMemory 扩展**
  - [ ] 添加 `iteration_history` 字段（Deque + maxlen），`append_iteration_record(action_summary, observation_summary)`，`latest_iteration_history(limit)`。
  - [ ] 配置项：默认 maxlen（例如 20），可由 builder/assembler 注入。
- **B. 基类写入钩子**
  - [ ] 在 React/BaseAgent 的 ACT/OBS 流程中，统一调用写入方法（封装在基类），把每轮 act/obs 摘要落到 `self.wm`（私域）。
  - [ ] 提供摘要构造辅助（工具名、scene_number、success、关键结果/URL），便于各 Agent 复用。
- **C. Agent 接入与清理**
  - [ ] Image/Video/Audio/Voice 接入基类钩子，移除孤立 `obs_event` 构造或手写日志。
  - [ ] 确认 MAS WM 仍只承载结构化产物/事实，历史不外泄。
  - [ ] 清理当前不合理逻辑：
    - 移除将 WM 仅当作产物缓存的写法（确保 act/obs 摘要也写入 iteration_history）。
    - 移除未落地的 `obs_event`/scene_events 旧实现（仅 archive 或适配层保留），避免双轨。
    - 去除旧 slot/fact_store 兼容路径中对迭代状态的暗写，统一走新钩子。
- **D. 上下文读取**
  - [ ] 调整 OBSERVE 构建逻辑，允许读取裁剪后的迭代历史（私域）用于决策（已完成/需重试），不依赖临时缓存。
- **E. 验证与文档**
  - [ ] 更新/补充单测覆盖 history 写入/读取。
  - [ ] 文档同步，说明 WM 的产物 vs 迭代历史职责，MAS/Agent 分层。

> 本清单用于后续按阶段落地，先扩展 WM/基类钩子，再逐步接入各 Agent 并清理旧逻辑。
