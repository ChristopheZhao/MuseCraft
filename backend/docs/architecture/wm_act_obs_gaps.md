# WorkingMemory 与 ReAct 迭代记录的偏差与修正方案

## 正确目标
- **OBS 只记录当轮**：仅包含当前轮的执行动作和结果（可对过长输出精简），不引入/推断状态。
- **短期 WM 存结构化信息**：Agent WM 存储当轮写入的结构化事实/产物/OBS 结果，供下一轮显式读取；MAS WM 只暴露需共享的结构化事实（`scene_outputs.*` 等）。
- **进度/状态由视图推导**：OBS 仅当轮（记录本轮 act 与结果，可对过长的 tool result 做必要精简），不做复用/筛选决策；在 Agent 迭代过程中通过应用层接口将结构化 OBS 信息写入 WM，下一轮显式从 WM 读取构建上下文，不默认“常驻即自动注入”。完成/失败等统计由状态视图基于 WM facts/产物/摘要做统计汇总，不承担决策，也不写回 WM。

## 当前偏差（现行代码）
- 现有实现仍聚焦产物写回，缺少基于 WM facts的状态视图使用，短期记忆价值未充分发挥。
- 部分 legacy 逻辑（slot/prepared_assets、obs_event/scene_events）仍存在，容易与新架构混用。

## “产物优先”现状的不足
- **失忆风险**：只把产物塞进上下文而缺少迭代过程的事件/摘要，Agent 难以基于已完成/失败的过程信息调整策略。
- **协作缺口**：下游只能看到产物，看不到前序尝试/异常的结构化摘要，协作上下文不足。
- **调试困难**：当前迭代信息未结构化落在 WM，缺少可供复用/诊断的摘要，只能依赖日志。
- **记忆价值弱化**：WM 被当作产物缓存，迭代过程和状态视图未用起来。


## record_event 现状与计划
- 现用点：BaseAgent 处理 tool_contract slot 写入时可记录事件；ReActAgent 每轮 ACT 后按 executed_calls 记事件；legacy adapters/operators 也有调用。
- 计划：状态由独立状态模块/视图统一管理，不在记忆内部实现；record_event 将被移除/停用，或仅保留过渡期极简标签，配合清理 legacy 调用。

## 改进方案
1) **保持 WM 轻量、分层清晰**：
   - 不引入新的 act/obs 序列存储；以结构化产物/事实为主（事件流 record_event 计划清理/停用），每轮的结构化obs存入WM；
   - 状态/进度由独立的状态视图模块基于迭代过程的统计记录生成；仅做统计，不做决策。
2) **统一写入/读取方式**：
   - 当轮 OBS 结构化信息通过统一接口写入 Agent WM；需要共享的产物经 `persist_scene_outputs` 规范化后仅写 MAS WM。
   - record_event 计划清理/停用；上下文构建显式从 WM（facts/产物/状态视图）读取，不自动注入历史。
3) **清理孤立/legacy 逻辑**：
   - 移除未落地的 `obs_event`/scene_events 旧实现，避免双轨。
   - 清理 slot/prepared_assets/fact_store 旧路径中对状态的写入，统一走新架构。
4) **经验教训（防止重犯）**：
   - 不再为 Agent 新增 iteration_history/自维护状态序列，状态应由 WM 事实 + 状态视图推导。
   - Agent 不直接访问具体记忆实现/slot，所有访问通过抽象接口（WM facts、记录事件、状态视图）进行。
5) **统一的迭代摘要（轻量）**：
   - 在 WM 抽象层提供受控的 OBS 写入接口（精简 act/tool_res 为标准 OBS 结果结构），由 Base/ReactAgent 统一调用，避免 Agent 自维护列表。
   - 适用于各类工具输出（不限场景），引用产物 key/URL 而非全文；状态视图可结合 facts/OBS 结果推导进度（做统计，不决策）。
   - 抽象层：WorkingMemory 仅提供追加/读取原始 OBS 结果的接口，不承担压缩/截断；裁剪/窗口策略由独立的 context manager/视图层按配置应用，对外提供统一的视图。
   - 应用层：Base/ReactAgent 在 ACT+OBS 结束后通过 helper 写入 OBS 结果到 Agent WM；下一轮迭代通过 context manager（默认不裁剪）从 Agent WM 读取并加工入上下文。
6) **Artifacts 定位**：
   - `persist_scene_outputs`/artifacts 辅助仅用于规范化工具产物并写入 MAS WM（共享引用），Agent WM 不再写入副本；实际文件由工具/存储处理，记忆只存引用/元信息。
   - 非文件类输出如需共享，应通过统一 schema 或 `write_shared_fact` 写入 MAS WM，保持作用域区分：Agent 自有产出在当轮 OBS→Agent WM 流程中已可见，跨 Agent 复用走 MAS WM。
7) **事件流取舍**：
   - 迭代统计/视图基于 WM 已写入的结构化信息，不再使用 record_event；record_event 逐步清理/停用。
## 落地子任务列表
- **A. 保持 WM 简洁**
  - [ ] 不引入新的 act/obs 序列字段；当轮 OBS 已包含结构化事实/产物，统一通过写入接口落到 WM，事件标签 record_event 计划清理/停用。
- **B. 状态视图/进度**
  - [ ] 基于 WM facts/OBS 结果做统计汇总，不在 OBS 中注入历史，不做决策。
- **C. Agent 清理**
  - [ ] 移除孤立 `obs_event`/scene_events 写法（仅 archive 保留）。
  - [ ] 清理 slot/prepared_assets/fact_store 旧路径对状态的写入，统一走新架构；确认 MAS WM 只承载结构化产物/事实。
  - [ ] 归档/替换 legacy `SceneIterationStateBuilder`，用新的基于 WM facts的 Agent 状态视图。
  - [ ] 按规划清理/停用 record_event 依赖，由统一状态模块/视图管理统计，不在记忆内部实现。
- **D. OBS 写入/上下文读取**
  - [ ] 基类/服务提供统一的 OBS 写入接口，写入 Agent WM；共享产物写 MAS WM，取消 Agent 副本。
  - [ ] 调整上下文构建：通过 context manager 显式从 Agent WM 读取所需事实/OBS 结果和状态视图。
- **E. 验证与文档**
  - [ ] 补充单测覆盖事件流/产物写回与状态视图使用。
  - [ ] 文档同步，说明 WM 角色：事实/产物/事件；状态由视图统计；OBS 仅当轮，写入由统一接口处理。

> 本清单用于按阶段落地：保持 WM 中立轻量、通过状态视图统计进度，清理 legacy slot/obs_event，避免重回自维护迭代历史的老路。


> OBS 仅维护当前轮的执行动作和执行结果（可对过长输出精简），不引入/推断状态；状态统计由独立视图基于迭代记录/WM 数据生成。
