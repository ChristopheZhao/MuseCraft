# Validation Ledger: PLAN-20260402-046

## Scope
- Validate owner-boundary restoration for the image mainline.
- Confirm helper/adapter/composer/tool layers no longer perform semantic owner work that belongs to scene contract or consistency assets.

## Acceptance Gates
### Review / boundary gate
- [ ] Review confirms `image_purpose` and `frame_thesis` have a single accepted owner and are not re-inferred at multiple downstream layers
- [ ] Review confirms stable character traits are consumed from structured owner fields, not helper lexical guessing
- [ ] Review confirms `image_generation_tool` is execution-only and no longer owns prompt-building compatibility paths

### Stage 1 gate: owner restoration
- [ ] `memory_views` no longer invents image-mainline semantics during payload assembly
- [ ] `image_prompt_composer_tool` no longer re-infers strategy/timepoint fields or writes guessed values back into scene data
- [ ] `image_prompt_normalization.py` no longer rewrites semantic text in runtime mainline

### Stage 2 gate: runtime mainline cleanup
- [ ] runtime image generation no longer falls back to helper-driven semantic character filtering
- [ ] representative scene prompts still render coherently from explicit upstream fields
- [ ] missing owner fields surface as explicit diagnostics rather than silent helper repair

## Automated Checks
- [ ] targeted unit tests for image payload assembly / composer owner boundaries
- [ ] targeted unit tests for runtime image tool behavior without semantic helper fallback

## Manual Checks
- [ ] inspect representative scene prompt before/after cleanup and confirm semantic source is traceable to explicit owner fields
- [ ] inspect one action scene and one calm scene to confirm no helper lexical “best frame” selection remains

## QC Rules
- No compatibility shim for proven-wrong helper owner logic.
- No lexical or keyword rules that decide stable traits, frame choice, or scene strategy inside runtime helper/composer layers.
- No execution-tool prompt-building fallback that reinstates semantic owner drift.

## Evidence Log
- 2026-04-02T08:00:00Z validation ledger created together with PLAN-20260402-046 after subagent audit confirmed image-mainline owner drift.
