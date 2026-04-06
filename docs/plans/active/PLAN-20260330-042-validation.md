# Validation Ledger: PLAN-20260330-042

## Scope
- Validate the narrow video-quality follow-up discovered after live rerun verification of the repaired image-to-video chain.
- Validate only the obvious video prompt-surface issues: weak local-event projection for legacy scene payloads, duplicated/summary-heavy action text, and over-heavy consistency prose.

## Acceptance Gates
### Pre-implementation governance
- [x] New window reviewed the plan/ledger pair before coding
- [x] Review confirms the task remains a narrow video prompt-surface remediation rather than reopening `038` or launching a second content-architecture round
- [x] Review confirms `038` may remain overall `in_progress`, but `042` does not absorb its remaining sprint scope or mutate its lifecycle status
- [x] If scope/owner/test gates changed, amendment was made before implementation
- [x] Review confirms no second video prompt mainline, no parallel scene carrier, and no fixed per-second rule engine is introduced
- [x] Review freezes the current root-cause baseline: the active rerun sample remains legacy-only payload at the scene carrier, and scene 1/2 composer prompts still show duplicated motion-beat summaries plus majority-footprint consistency prose

### Prompt-surface quality closure
- [x] Legacy scene payloads with only `motion_beats / script_text / visual_description` can still project to a readable local-event prompt
- [x] Action progression no longer contains obvious duplicate or near-duplicate phrases in the main arc
- [x] `script_text / narrative_description` no longer re-summarize the same action arc as the prompt主体
- [x] Consistency block is compressed to short locks rather than long role-card/environment prose
- [x] Optimization stays at builder/composer boundary and does not spill into agent-level decision tables

### Post-implementation closeout
- [x] Focused review confirms the change improves the obvious rerun quality issues without expanding to upstream scene/script redesign
- [x] Rerun evidence for at least scene 1 or scene 2 shows prompt readability improvement and no regression in chain success

## Automated Checks
- [x] Legacy-motion-beats projection regression
- [x] Scene-2 prompt surface regression
- [x] Consistency-compression regression
- [x] No-second-mainline regression

## Manual Checks
- [x] Prompt review for scene 1/2 reads like a local-event clip rather than a dynamic scene card
- [x] Mid/late frames for scene 1/2 no longer obviously collapse the protagonist into a tiny background figure due to over-broad prompting
- [x] Review confirms no upstream contract rewrite or image/runtime spillover was introduced

## QC Rules
- This plan owns only the post-rerun obvious video-quality follow-up.
- `038` may remain overall `in_progress`, but its remaining scope and lifecycle status must not be reopened, absorbed, or mutated by this plan.
- If implementation truly requires scene/script schema work, stop and amendment this plan instead of expanding implicitly.
- Consistency layering remains valid; this plan may only compress its prompt footprint, not redesign ownership.
- No fixed second-by-second decision table may be introduced under the name of “time narrative optimization”.

## Evidence Log
- 2026-03-30T14:14:09Z validation ledger created together with `PLAN-20260330-042`. Initial acceptance is intentionally narrow: close the most visible rerun quality issues on the video prompt surface without reopening upstream contract design or creating a second mainline.
- 2026-03-30T14:26:57Z governance amendment aligned the ledger with the review baseline: `038` is not treated as overall completed, `042` may not absorb its remaining scope, and implementation must begin from an explicit frozen diagnosis that the current rerun sample is still legacy-only at the scene carrier while scene 1/2 composer prompts remain dominated by duplicated motion-beat summaries and oversized consistency prose.
- 2026-03-30T15:05:00Z builder/composer implementation completed inside the frozen `042` envelope. Focused regressions now cover legacy-motion-beat projection, scene-2 prompt-surface compaction, consistency compression, and fallback precedence so that `action_phases` remains primary while `motion_beats` stays fallback-only. Manual prompt review against the active rerun sample shows scene 1 consistency ratio reduced to `138/310 = 0.445` and scene 2 to `128/331 = 0.387`. Fresh provider rerun evidence is still outstanding, so post-implementation closeout remains open.
- 2026-03-30T15:08:11Z scene 2 focused rerun completed successfully with `video_generation.generate_with_continuity` against the updated prompt surface. New evidence was saved under `/tmp/svm_rerun_verify/scene2_rerun_result.json`, `/tmp/svm_rerun_verify/scene2_rerun_video.mp4`, and `/tmp/svm_rerun_verify/scene2_rerun_frame_{0_5,5_0,8_5}.jpg`. Compared with the earlier `/tmp/svm_rerun_verify/scene2_frame_{0_5,5_0,8_5}.jpg`, the protagonist remains the dominant subject through mid/late frames and chain success does not regress, so the remaining closeout gates are satisfied.
