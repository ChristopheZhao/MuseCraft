# Validation Ledger: PLAN-20260330-040

## Scope
- Validate the dedicated remediation of image-agent safety closure and image-purpose-aware still/reference prompt contract drift discovered during the 2026-03-30 rerun.
- Validate only the image-agent narrow boundary: provider-sensitive rewrite closure, explicit image purpose direction, still/reference prompt rooting, consistency compression for still images, and montage-to-still projection.

## Acceptance Gates
### Pre-implementation governance
- [x] New window reviewed the plan/ledger pair before coding
- [x] Review confirms the task remains an image-agent narrow remediation rather than generic provider safety or upstream scene/video redesign
- [x] If scope/owner/test gates changed, amendment was made before implementation
- [x] Review confirms `image_purpose / task_direction` is implemented as an in-place input evolution rather than a new parallel image workflow/mainline
- [x] Review confirms `image_purpose / task_direction` is treated as context, not as a fixed retry policy or hard-coded agent decision table

### Sensitive-error closure
- [x] Doubao `InputTextSensitiveContentDetected` is recognized by the reactive rewrite boundary after raw provider exceptions are normalized at the tool boundary
- [x] Rewrite attempts use the rewritten prompt on retry rather than replaying the same original prompt
- [x] Safety diagnostics surface provider code, rewrite attempt, and retry outcome explicitly
- [x] No agent-layer ad hoc keyword patch or silent retry loop is introduced
- [x] No fixed retry count / mandatory tool order rule is introduced into the image agent ReAct loop

### Still-image prompt contract
- [x] Image path has an explicit `image_purpose / task_direction` distinction for at least `scene_opening_anchor` and `character_reference`
- [x] `scene_opening_anchor` prompt root prefers `opening_state` / first-frame anchor
- [x] `character_reference` prompt root prefers stable identity / outfit / props constraints instead of scene narrative
- [x] `narrative_description`, camera motion, montage language, and long role cards are no longer the still-image prompt主体
- [x] Consistency injection is compressed to short static-image locks
- [x] Montage/mixed scenes project to one dominant still composition instead of video-editing prose

### Post-implementation architecture closeout
- [x] Post-implementation hardening review confirms the still/reference contract no longer depends on duplicated content-level hardcoding across `image_generation_tool` and `image_prompt_composer_tool`; this gate is satisfied only when `PLAN-20260330-041` is completed or the user explicitly waives that debt

## Automated Checks
- [x] Sensitive-error normalization / matcher regression test covers raw provider exception and normalized `ToolError` carrying `InputTextSensitiveContentDetected`
- [x] Image rewrite path regression test proves rewritten prompt is retried and telemetry is emitted
- [x] Scene 1 prompt regression proves `scene_opening_anchor` prompt is rooted in opening-state composition
- [x] Character reference regression proves tool-level `character_reference` prompt does not inherit scene summary prose
- [x] Scene 5 prompt regression proves montage/editing prose does not survive into final image prompt
- [x] Consistency-compression regression test proves image composer injects only short locks

## Manual Checks
- [x] Log review clearly shows provider-sensitive failure vs local rewrite attempt boundary
- [x] Prompt review for rerun sample reads like a single still image description, not a scene summary card
- [x] Prompt review for reference-image sample reads like a stable identity/reference brief, not a scene card
- [x] Review confirms no parallel image contract or new memory/runtime owner was introduced

## QC Rules
- This plan owns only the rerun-discovered image-agent remediation.
- `038` remains a completed content-mainline record and must not be reopened or absorbed by this plan.
- If implementation needs upstream scene/script changes or video-path changes, stop and amendment this plan instead of expanding implicitly.
- Supplier-specific differences may be normalized only at tool/prompt-safety boundaries; they must not leak into agent planning logic.
- Existing project-level character-reference generation remains a legitimate consumer of `image_generation`; this plan may align prompt contract direction for that surface but must not expand into generic project-planning redesign.
- Character-reference acceptance may be satisfied at the image tool / prompt-contract regression layer; wiring project-level character-reference callers is out of scope unless explicitly amended.

## Evidence Log
- 2026-03-30T06:56:56Z validation ledger created together with `PLAN-20260330-040`. Initial acceptance is intentionally narrow: close the provider-sensitive rewrite loop for image generation, re-root image prompts on still/reference purpose-specific composition, and keep consistency injection compressed and image-specific.
- 2026-03-30T07:16:41Z review-first amendment aligned the ledger with code evidence: provider-sensitive closure now requires boundary normalization of raw provider exceptions before rewrite classification, and `character_reference` acceptance is explicitly limited to tool/prompt-contract regression rather than project-flow redesign.
- 2026-03-30T09:11:48Z focused automated and manual evidence for the original `040` scope is now complete: targeted regressions passed, provider rerun for scenes 1/2/3/5 succeeded, and the image-agent remediation stayed inside the frozen image boundary without reabsorbing `038`.
- 2026-03-30T09:11:48Z final plan acceptance remains intentionally open because post-implementation review found duplicated content-level still/reference hardcoding across the image tool/composer boundary. That debt is now tracked by `PLAN-20260330-041`, and this ledger is not considered fully passed until that follow-up hardening is completed or explicitly waived.
- 2026-03-30T10:10:02Z `PLAN-20260330-041` completed and cleared the last architecture blocker for this ledger. The original `040` remediation now sits at `awaiting_user_confirmation`; remaining centralized lexical guards were explicitly accepted as a separate non-blocking future TODO rather than a blocker for this scope.
- 2026-03-30T10:17:56Z user confirmed final closeout. `040` is now accepted as completed because the original remediation behavior is validated, the `041` hardening blocker is cleared, and no residual blocker remains inside this plan boundary.
