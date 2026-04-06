# Scene Contract v2 Freeze (2026-03-29)

## Scope
- Freeze the Sprint 1 owner/SoT matrix and the `SceneContract v2` field direction before any prompt or consistency implementation changes.
- This document is contract-first. It does not create a new runtime carrier.

## Root Problem
- Current media generation semantics are split across `concept_plan.scenes`, `scene_overview.scenes`, `scene_scripts`, and prompt composers.
- The failure mode is not only a weak prompt. The real drift is that:
  - scenes are still planned as chapter summaries rather than filmable local events
  - script output does not yet own a duration-scalable action structure
  - consistency guidance and prompt prose can swamp actionable motion content

## Owner / SoT Matrix
| Surface | Role | Owner | Allowed semantics | Forbidden semantics |
| --- | --- | --- | --- | --- |
| `scene_info_payload.scenes_to_generate[]` persisted via `scene_info_ref` | Authoritative media-agent scene semantic carrier | control plane boundary assembly | scene-level generation input for image/video agents | parallel copy of runtime state, approval state, or QC verdicts |
| `scene_overview.scenes[]` | Read-model / overview surface | published script boundary input | compact scene overview, carry-forward visual fields, image refs | becoming a second authoritative media contract |
| `concept_plan.scenes[]` | Upstream planning source | concept planner output | episode arc, scene function, ordering | direct final video prompt semantics |
| `scene_scripts[*]` | Upstream execution source | script writer output | scene script, motion beats, narration, stage-level action detail | replacing runtime owner or prompt carrier |
| `WorkingMemory` primary slots | iterate facts / execution cache | orchestrator + memory services | execution observations, prepared tool assets | authoritative scene contract, QC authority, approval/runtime payloads |
| `plan file` / `validation ledger` / review notes | validation and governance surfaces | plan governance | generator/evaluator diagnostics, examples, acceptance notes | runtime input, published deliverables, authoritative scene carrier |

## SceneContract v2

### Semantic unit
- A scene is a `local_event`, not a chapter summary.
- A scene must be duration-scalable. It may be projected to 5s/10s/15s/20s, but the semantic structure must remain the same.

### Frozen field direction
- `opening_state`
- `event_trigger`
- `action_phases`
- `end_state`
- `global_locks_ref`
- `continuity_ref`

### Field intent
- `opening_state`: what is already visible at the start of the scene
- `event_trigger`: what changes the static opening into an active event
- `action_phases`: 2-6 relative phases of visible action; projection to exact timing happens later
- `end_state`: where the scene lands to support the next cut
- `global_locks_ref`: episode-level style/character/world locks
- `continuity_ref`: previous-scene continuation edge only

## Extension Rule
- `SceneContract v2` must evolve in place on the existing `scene_info_payload` carrier.
- Forbidden:
  - a new `scene_contract_payload`
  - a parallel runtime payload for media semantics
  - a new WorkingMemory primary slot treated as authoritative scene input

## Positive Examples

### Example A: 5s local event
- opening_state: 韩立停在秘境入口前，符文微亮，手中长剑未出鞘
- event_trigger: 入口符文忽然闪动，逼得他后撤半步
- action_phases:
  - 观察入口异动
  - 迅速收势并握紧剑柄
  - 目光锁定符文核心，准备进入
- end_state: 韩立站稳，视线集中在入口中央

### Example B: 10s combat beat
- opening_state: 韩立被压制，半跪稳住身形，剑尖擦地
- event_trigger: 胸口灵光突然收束并向全身扩散
- action_phases:
  - 稳住身形，压住退势
  - 灵光聚拢，衣袍与尘土被气流掀起
  - 金光爆开，碎石向外冲散
  - 黑袍修士被震退，镜头停在韩立抬头定格
- end_state: 韩立完成反击起势，下一场可承接压制反转

### Example C: 15s atmosphere-to-action escalation
- opening_state: 韩立独自穿行在秘境通道，四周幽蓝光影晃动
- event_trigger: 前方传来低沉震响，暗红法术光在墙面掠过
- action_phases:
  - 缓慢探索与环境异动
  - 发现异常光源并停步戒备
  - 黑袍修士现身并释放压迫性法术
  - 韩立回身拔剑，场面进入冲突前缘
- end_state: 双方对峙，下一场进入正式交锋

## Negative Examples

### Example N1: chapter-summary scene
- “通过激烈战斗突出韩立面临的挑战与成长，烘托紧张感，为后续力量爆发铺垫情感转折。”
- Rejected because it describes narrative purpose, not a filmable local event.

### Example N2: hardcoded stopwatch template
- “0-3s 观察，3-6s 蓄力，6-8s 爆发，8-10s 定格” as the only contract.
- Rejected because it locks the semantics to 10s instead of a duration-scalable structure.

## QC Output Boundary
- Generator/evaluator outputs may only land in:
  - plan file
  - validation ledger
  - explicit review notes
- They must never become:
  - runtime input payload
  - published deliverable
  - WorkingMemory primary consumption slot

## Code Anchors
- [memory_views.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py)
- [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py)
- [scene_info_reference_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/scene_info_reference_service.py)
- [workflow_state.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/core/workflow_state.py)
