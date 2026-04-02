# 2026-04-01 Derived Heuristic Gate Drift Thread

## Problem
- 两条不同主线在进入后期修复时，都自然漂向了“先加一个检测器/门控”：
  - `image_agent` 的重复 scene 问题，一度走向 agent-level duplicate gate，试图在 ACT 前拦截重复调用。
  - `video_agent` 的去幻灯片化问题，在 Stage 4 一度引入 `camera_term_ratio`、`opening_anchor_only_rate`、`warning_flags` 这类派生质量判断，并尝试放进 runtime/context 主链。
- 这两类设计表面上都像“更安全的修复”，但本质上都在把派生判断塞回 agent 主链：
  - 不是源事实，而是代码写死的推断或阈值裁决；
  - 不是根因修复，而是运行期补一个启发式控制层；
  - 一旦稳定落到 payload/context/log 面，下游就会自然把它消费成事实或系统判定。

## Turning Points
- `image repeat` 这条线最后确认：真正的问题不是“缺少 duplicate gate”，而是 planner 在长程上下文里没有稳定、短小、可消费的执行进度视图。主线因此改成 `planner-visible progress read-model`，并要求该视图必须：
  - derived
  - rebuildable
  - non-authoritative
  - source-mapped to a single SoT
- `video slideshow` 这条线最后确认：真正的问题不是“缺少 slideshow detector”，而是上游 `concept -> script -> image -> video` 的 scene semantics 与 prompt synthesis 已经漂向特写/镜头词主导。主线因此收回到：
  - `scene_thesis`
  - `frame_thesis`
  - `image_purpose`
  - prompt synthesis rebuild
- 两条线最后收敛到了同一个边界判断：
  - 如果问题是 planner continuity / scene semantics drift，就优先修 contract、prompt、read-model；
  - 不要在 runtime 主链引入 heuristic detector / quality gate 来替 agent 做预判。

## Decision Rules
- 当问题根因在 planner continuity、scene semantics、prompt synthesis 或上游 contract 时，优先修 source contract / planner-visible read-model，不要先加 runtime heuristic gate。
- 只有源事实可以进入 authoritative payload、agent planning context、WorkingMemory 主消费槽位；`camera_term_ratio`、`slideshow_risk`、`duplicate_risk` 这类派生判断不得进入这些主链面。
- derived projection 可以存在，但只能是 source-mapped、可重建、非 authoritative 的 read-model；它不能携带代码代写的语义裁决。
- 不要把“风险检测器”包装成日志、diagnostics 或 review receipt 后长期保留在稳定产品面；稳定化的派生判断会自然长成影子控制面。
- 如果需要定量判断或阈值验证，只允许放在 test、validation note、prompt diff evidence 或显式人工 review 面，不得反向进入 runtime 决策链。

## Why It Matters
- heuristic gate 很容易在 vibe coding 过程中继续吸附新逻辑：
  - 多读几个状态面
  - 多加一个 fallback
  - 多补一个 exception
  - 最后从过渡层长成并列主路
- 对自主 agent 来说，这类“先贴标签再让 agent 决策”的结构会削弱模型在真实上下文中的语义判断空间，也违反仓库里 `Anti-Hardcoding` 和 `Non-Pipeline Autonomy` 的原则。
- 更关键的是，这类设计会掩盖真正需要修的地方：上游 contract、prompt、context composition、planner continuity。

## Reuse
- 适用于所有“agent 决策看起来不稳，于是想先加检测器/门控”的修复场景。
- 尤其适用于：
  - 长程 ReAct/agent 工作流
  - planner continuity 问题
  - scene/prompt semantics drift
  - 想把 `diagnostics`、`warning_flags`、`risk_score` 放回 runtime/context 的场景
- 复用时先问：
  - 这是源事实，还是代码派生判断？
  - 这是 read-model，还是 semantic verdict？
  - 这是根因修复，还是运行期补丁？
