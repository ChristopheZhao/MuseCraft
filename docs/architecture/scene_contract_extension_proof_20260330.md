# Scene Contract Extension Proof

- Date: `2026-03-30`
- Scope: `PLAN-20260329-038` Sprint 5
- Validation level: `contract / prompt-surface proof`, not provider-render acceptance

## Goal

Prove that the current `SceneContract v2 + ScriptContract v2 + ConsistencyAssetContract v2` stack scales from 10s to 15s and 20s without rewriting the scene semantic unit or falling back to a stopwatch-only prompt contract.

## Validation Matrix

| Check | Surface | Evidence |
| --- | --- | --- |
| 10s high-action scene sample | Scene contract + prompt body | Existing Sprint 1/2 combat examples, plus builder prompt body assertions |
| 15s medium-density narrative scene | Scene contract + script contract | Example B below |
| 20s target-duration projection | Prompt builder smoke + projection table | Example C below and `video_prompt_builder_20s_projection_ok` |
| Strong continuity scene pair | Consistency assets + continuity handoff | Example D below |
| Global-consistency-only scene pair | Consistency assets without continuity edge | Example E below |

## Example A: 10s high-action local event

- opening_state: 韩立半跪稳住身形，剑尖擦地拖出石屑
- event_trigger: 黑袍修士逼近施压，迫使韩立强行起身聚气
- action_phases:
  - 起势：韩立压低重心稳住身形，衣摆被气流扯动
  - 蓄势：胸口灵光收束到全身，碎石开始震动
  - 爆发：金光骤然爆开，黑袍修士被冲击逼退
- end_state: 镜头停在韩立抬头定格，金光未散

Why it matters:
- this sample validates that a dense local event can still be represented as `opening_state + trigger + action_phases + end_state`
- the prompt body is action-first rather than theme-first

## Example B: 15s medium-density narrative scene

- opening_state: 韩立独自穿行在秘境回廊，四周幽蓝光影晃动，空气潮湿而安静
- event_trigger: 回廊尽头传来低沉震响，暗红法术光在墙面短暂掠过
- action_phases:
  - 发现异常：韩立放慢脚步，观察回廊深处的异动
  - 压迫建立：黑袍修士现身，法杖拖出暗红尾迹，空间压迫感逐步升高
  - 对峙升级：韩立回身拔剑，双方力量在回廊中央形成拉扯
  - 爆发前收束：镜头停在韩立握剑定势、黑袍修士压迫逼近的瞬间
- end_state: 双方对峙已经成立，下一场可直接进入冲突爆发

Why it matters:
- 15s scene 允许更多环境建立和压迫升级，但语义单位仍然是一个 `local_event`
- scene 没有退化成章节摘要，也没有被强行拆成秒表脚本

## Example C: 20s target-duration projection

Semantic unit:
- 韩立在秘境回廊中从“发现威胁”走到“进入爆发前收束”的单一局部事件

Frozen semantics:
- opening_state 不变
- event_trigger 不变
- 4 个 action phases 不变
- end_state 不变

Projection proof:

| Phase | Relative weight | 15s projection | 20s projection |
| --- | --- | --- | --- |
| 建立压迫 | 3 | 约 0-4.5s | 约 0-6s |
| 接近试探 | 2 | 约 4.5-7.5s | 约 6-10s |
| 对峙升级 | 3 | 约 7.5-12s | 约 10-16s |
| 爆发前收束 | 2 | 约 12-15s | 约 16-20s |

Extension verdict:
- 延长到 20s 后，没有新增第二套语义 contract
- 增加的是 phase 占比投影，不是改写 scene 含义
- prompt builder smoke 已验证 20s 场景仍使用 `action_phases`，并未退化成 `0-3s / 3-6s / ...` 固定模板

## Example D: Strong continuity scene pair

Scene 3:
- opening_state: 韩立在回廊尽头被黑袍修士压制，脚下碎石轻微震动
- end_state: 韩立聚气待发，身体前冲势能已形成

Scene 4:
- continuity_ref: depends_on_scene = 3
- opening_anchor: 不重新建立人物造型，直接承接上一场尾帧里的前冲势能
- local_continuity:
  - previous_frame_available: true
  - transition_notes: 接住韩立聚气后的前冲趋势和镜头推进方向

Why it matters:
- continuity 只描述 scene 3 -> scene 4 的边界承接
- 它不承担全 episode 的画风一致性，也不替代当前 scene 的动作弧线

## Example E: Global-consistency-only scene pair

Scene 1:
- depends_on_scene: null
- style.global_lock: 非写实仙侠动态水墨，墨色边缘与灵光粒子统一
- characters.global_lock: 韩立固定为青年男性、深蓝灰修仙袍、长剑

Scene 5:
- depends_on_scene: null
- style.global_lock: 与 Scene 1 相同
- characters.global_lock: 与 Scene 1 相同
- opening_anchor: 韩立已进入反击后的稳定阶段，但不要求承接 Scene 4 的尾帧

Why it matters:
- 没有 continuity edge 时，global consistency 仍然成立
- global consistency 只是锁定 episode 级视觉身份，不覆盖 scene 自身动作与镜头设计

## Acceptance Notes

- This proof closes the extension question at the contract level:
  - 10s, 15s, and 20s can be represented by the same scene semantic unit
  - continuity and global consistency remain separated
  - longer durations expand phase projection, not semantic ownership
- This proof does not claim final rendered video quality is solved for every provider
- Provider render quality, style adherence, and cross-scene image/video supplier behavior remain downstream acceptance concerns outside this contract proof
