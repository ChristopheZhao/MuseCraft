# Supplement: PLAN-20260331-043 Progress Read-Model Design Freeze

## Purpose
- Record the design decision that supersedes the earlier duplicate-gate mainline in [PLAN-20260331-043.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260331-043.md).
- Keep design rationale, owner/host boundaries, and single-SoT mapping out of the main execution plan so the plan can stay concise.
- This note is explanatory only. Lifecycle status still belongs to the main plan, validation ledger, and [PLAN_INDEX.json](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/PLAN_INDEX.json).

## Decision
- Repeated scene work in this stream is no longer treated as an agent-level duplicate-gate problem.
- The accepted mainline is a planner-visible progress file/read-model built from existing source facts and consumed before each planning step.
- The earlier duplicate-gate path is superseded history, not a retained compatibility layer.

## Scope Clarification
- This correction slice is about planner-input continuity, not MAS-level progress authority.
- Existing MAS facts may be read as source material, but this slice must not create a new authority surface.
- The product problem being corrected is repeated planning of already-completed scenes by the image agent under long-horizon context.
- Therefore the accepted solution is a derived progress read-model shown to the planner before each PLAN step, not an execution-time duplicate gate.

## Why Duplicate Gate Was Rejected
- The observed defect is planner continuity under long-horizon context, not the lack of an execution-time reviewer.
- A duplicate gate risks becoming a compatibility layer that absorbs new semantics over time:
  - more state reads
  - fallback paths
  - retry exceptions
  - consumer-specific fields
- Once that happens, the gate stops being transitional and becomes a parallel semantic mainline.
- That absorption pattern conflicts with the repo rule that proven-wrong designs should be replaced outright rather than preserved through compatibility shims.

## Owner and Host
- This slice is not a MAS top-level gate-layer change.
- This slice is not a new agent-local semantic gate either.
- Semantic owner: planner-input / context-editing path.
- Expected implementation host: supporting capability builder consumed by [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) and/or [plan_context.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/utils/plan_context.py), then surfaced to [react_agent.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/react_agent.py) before tool-call planning.

## Single-SoT Mapping
- The system may have more than one view. What matters is whether authority stays single-owned.
- Source-of-truth mapping for this slice:
  - planned scene membership: `scene_info_ref -> scene_info_payload.scenes_to_generate[]`
  - execution-fact source: WM structured execution facts / receipts
  - artifact/reference output: `scene_outputs.*`
  - planner-visible progress file/read-model: derived projection only
- The progress file/read-model remains compatible with single SoT only if all of the following stay true:
  - it is derived from explicit source facts
  - it is rebuildable from those same source facts
  - it does not own independent completion authority
  - it does not write back planner-owned completion truth
- `scene_info_ref` is not a runtime completion surface.
- In this slice, `scene_info_ref` is the persisted boundary input reference for the scene contract consumed by downstream media agents and tools.
- The payload behind `scene_info_ref` may originate from upstream stage outputs, but it must not be rewritten by current-slice execution facts or `scene_outputs.*`.
- `scene_info_ref.scenes_to_generate[]` defines planned membership only.
- WM structured execution receipts / obs facts define execution success facts only.

## Minimum Progress Read-Model Contract
- The planner-visible surface should be concise, stable, and source-mapped.
- Minimum fields:
  - `planned_scene_numbers`
  - `successful_scene_numbers`
  - `remaining_scene_numbers`
  - `recent_execution_notes` or equivalent short receipt digest
- Field ownership:
  - `planned_scene_numbers` derives only from `scene_info_ref`
  - `successful_scene_numbers` derives only from WM structured execution receipts
  - `remaining_scene_numbers` is deterministic set subtraction from those two sources
  - `recent_execution_notes` is a compact digest of recent WM facts and remains non-authoritative

## Planner Consumption Rules
- The progress file/read-model is consumed before each `plan` step.
- Its purpose is to stabilize planner context under long histories and reduce reliance on raw audit history as the only planner surface.
- If the planner still repeats an already-successful scene after receiving this surface, the defect is treated as planner-quality drift and fixed in prompt/context/evals rather than by restoring a semantic duplicate gate.

## Explicit Non-Goals
- No new MAS runtime state machine.
- No new `BaseAgent` responsibility.
- No planner-owned completion-state writer.
- No reuse of `scene_outputs.*` as hidden completion truth.
- No retention of duplicate-gate logic as a fallback or compatibility path.

## Stop Conditions
- Stop and amend or fork a successor plan if any of these become necessary:
  - WM source facts are not structured enough to rebuild progress deterministically
  - implementation needs a new authority surface
  - implementation needs planner-owned completion writes
  - the slice expands into broader WM/source-fact normalization beyond this correction scope

## References
- [PLAN-20260331-043.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260331-043.md)
- [PLAN-20260331-043-validation.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260331-043-validation.md)
- [scene_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/scene_contract_v2_freeze_20260329.md)
- [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md)
- [mas_architecture_alignment_note_20260323.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_alignment_note_20260323.md)
