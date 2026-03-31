# Script / Video Prompt Contract v2 Freeze

Date: `2026-03-29`
Status: `frozen for Sprint 2`

## 1. Goal

Sprint 2 closes the gap between planning prose and executable video language.

- `script` must output a scene-level execution arc, not only chapter-summary prose.
- `video prompt` must consume `opening_state + action_phases + camera language + end_state`.
- The existing carrier remains authoritative. No parallel payload/store is allowed.

## 2. Owner / Carrier Freeze

- Runtime owner: `control_plane`
- Script authoring writeback: `project.scene_scripts.{scene_number}`
- Media-agent assembled carrier: `scene_info_payload.scenes_to_generate[]`
- Carrier evolution rule: `in_place_only`
- Forbidden:
  - `scene_script_contract_payload`
  - `video_prompt_contract_payload`
  - new WorkingMemory primary slot for prompt semantics

`project.scene_scripts` is the writer-facing store.
`scene_info_payload.scenes_to_generate[]` remains the only media-agent semantic carrier.

## 3. ScriptContract v2

Required direction:

- `script_text`
- `opening_state`
- `event_trigger`
- `action_phases[]`
- `end_state`
- `camera_language`
- `motion_beats[]` as compatibility/read-model support, not the only narrative structure

`action_phases[]` semantic rules:

- 2-4 phases by default
- each phase describes visible action, not abstract story function
- phase timing may be relative (`relative_weight`) or explicit (`start/end`)
- prompt consumers must not require a rigid stopwatch layout

## 4. VideoPromptContract v2

Final prompt body order:

1. duration
2. mode-specific guidance
3. opening state
4. event trigger
5. action arc
6. camera language
7. end state
8. optional story detail support
9. consistency block

Mode rules:

- `text_to_video`: establish the shot before action.
- `image_to_video`: focus on how the existing first frame evolves; do not restate the whole still image.
- `continuity`: explicitly continue prior tail-frame state and motion direction.

## 5. Positive Examples

### Example A: 10s combat escalation

- opening state: 韩立半跪稳住身形，剑尖擦地拖出石屑
- event trigger: 黑袍修士逼近施压，迫使韩立强行起身聚气
- action phases:
  - 起势：韩立压低重心稳住身形，衣摆被气流扯动
  - 蓄势：胸口灵光收束到全身，碎石开始轻微震动
  - 爆发：金光骤然爆开，黑袍修士被冲击逼退
- end state: 镜头停在韩立抬头定格，金光未散

### Example B: 5s quiet reveal

- opening state: 古旧静室内烛火摇晃，案前经卷半开
- event trigger: 韩立指尖触到经卷边缘，灵光顺纸页游走
- action phases:
  - 发现：符纹微亮，尘埃被光线托起
  - 反应：韩立抬眼凝视，手指停住
- end state: 经卷中心字符悬停发亮，为下场埋下承接点

### Example C: 15s atmosphere-to-action build

- opening state: 秘境回廊空旷潮湿，远处风声低沉
- event trigger: 黑袍修士从回廊尽头现身，法杖拖出暗红尾迹
- action phases:
  - 建立压迫：长廊纵深拉开距离感
  - 接近试探：法杖暗光逼近，韩立后撤半步
  - 对峙升级：双方灵力相撞，空气震颤
  - 爆发前收束：镜头停在韩立握剑定势
- end state: 空间被两股力量拉紧，留出下一场爆发入口

## 6. Negative Examples

- 章节摘要型 scene:
  - “通过激烈战斗突出韩立成长并铺垫后续转折”
  - reason: only story function, no visible event
- 秒表硬编码型 scene:
  - “0-1s A，1-2s B，2-3s C ...” as mandatory contract
  - reason: over-mechanical and not duration-scalable

## 7. Before / After Prompt Direction

Before:

- `视觉重点 + 叙事要点 + 一致性长段 prose`
- result: theme summary dominates, action execution weak

After:

- `开场状态 + 触发动作 + 动作推进 + 镜头语言 + 收束画面`
- result: the model receives visible progression first, consistency second

### Pair 1: high-action image-to-video

- before:
  - `通过激烈战斗突出韩立面临的挑战与成长，烘托紧张感，为后续力量爆发铺垫情感转折`
- after:
  - `开场是韩立半跪稳住身形，剑尖擦地拖出石屑；黑袍修士逼近施压，迫使他强行起身聚气；先稳住身形，随后灵光从胸口收束到全身，最后金光爆开把黑袍修士震退；镜头从中景缓推到爆发定格；收束在韩立抬头、金光未散的画面`

### Pair 2: continuity handoff

- before:
  - `承接上一场，延续故事高潮，强化震撼感与反击主题`
- after:
  - `延续上一场尾帧里韩立已聚气待发的状态，不重新建立人物造型；先接住上一个动作趋势，让金光继续扩散，随后地面崩裂、碎石掀起，黑袍修士被冲击逼退；镜头延续原有推进方向，最后停在韩立占据画面中心的压制姿态`

### Pair 3: quiet reveal

- before:
  - `营造神秘氛围，表现韩立发现机缘的关键节点`
- after:
  - `古旧静室内烛火摇晃，经卷半开；韩立指尖触到纸页边缘时，灵光沿符纹游走，尘埃被光线托起；先给经卷与指尖的细微反应，随后韩立抬眼凝视、手势停住；镜头保持安静近景，最后停在经卷中心字符悬停发亮，为下一场承接`

## 8. Validation Boundary

Allowed outputs:

- architecture docs
- plan file
- validation ledger
- unit/slice tests

Forbidden outputs:

- direct QC battle artifacts inside runtime payloads
- published deliverables carrying evaluator notes
- WorkingMemory primary slots storing prompt-review verdicts
