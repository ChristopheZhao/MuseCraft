# 2026-03-31 Handoff Without Plan Gate Thread

## Problem
- 这次主线任务本身不复杂，核心只包含三个收敛切片：
  - `plan contract precedence`
  - `execution-boundary duplicate guard`
  - `lease fresh-read + diagnostics`
- 但在切新窗口时，handoff 只给了实现方向，没有把“先立计划/冻结边界再实现”写成硬门槛。
- 结果新窗口直接编码，虽然修到了部分真实问题，但同时引入了新的架构漂移：
  - 把 image duplicate guard 落在 `BaseAgent`
  - 让执行边界读取 `iteration_view` 统计投影作为阻断依据
- 这不是复杂度失控，而是治理门缺失后，局部实现自然沿最短路径展开。

## Turning Points
- 先前已经建立了 deferred authority anchor，长期方向也被冻结，但它只约束“不要往哪里漂”，不能替代“本次实现先怎么规划”。
- handoff 和新窗口 prompt 没有明确要求先产出正式实现计划，只写了“读完后直接切三个修复切片”。
- review 时发现：
  - `react_agent.py` 的 contract precedence 修复方向基本正确
  - `runtime_session_service.py` 的 fresh-read / diagnostics 修复方向基本正确
  - 但 duplicate guard 因为没有被计划明确钉住 owner 和 truth surface，最后漂到了错误宿主和错误 truth source。

## Decision Rules
- 对任何仍含架构敏感边界的 follow-up，`handoff` 不能代替 `implementation plan`；新窗口开始编码前必须先冻结本次 owner、truth surface、禁止落点、验收项。
- deferred anchor 只能约束长期方向，不能替代本次切片计划；有 deferred guardrail 仍然要有当前 implementation gate。
- 当问题被切成多个修复切片时，计划里必须把每个切片的：
  - owner 层
  - authority source
  - forbidden surfaces
  - acceptance checks
  写清楚，否则实现会默认选最短路径。
- review 不只检查“问题是否被修到”，还要固定顺序检查：
  - owner 是否正确
  - truth surface 是否正确
  - 是否把统计/投影视图升级成行为真值
  - 是否把共享基类变成领域逻辑宿主

## Reuse
- 适用于所有“问题本身不复杂，但跨窗口继续实现”的 coding-agent 工作流。
- 尤其适用于：
  - 已有 deferred architecture guardrail
  - 当前实现仍需窄范围 follow-up
  - 用户要求切新窗口继续
- 可作为以后 handoff/prompt 生成时的硬检查：如果还没写正式 implementation plan，就不要把新窗口 prompt 写成“读完直接开始改代码”。
