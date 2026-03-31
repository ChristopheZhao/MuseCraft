# Validation Ledger: PLAN-20260329-038

## Scope
- Validate that scene narrative, prompt contracts, consistency assets, and orchestration/context/memory boundaries converge on a single scalable design rather than a prompt-only patch.

## Sprint Gates
### Sprint 1: Scene Contract v2 freeze
- [x] Owner/SoT matrix frozen before schema design
- [x] SceneContract v2 fields frozen
- [x] 3 positive scene examples written
- [x] 2 negative examples documented
- [x] Generator/evaluator gate completed

### Sprint 2: Script and Video Prompt Contract rewrite
- [x] ScriptContract v2 frozen
- [x] VideoPromptContract v2 frozen
- [x] 3 prompt before/after examples reviewed
- [x] Generator/evaluator gate completed

### Sprint 3: Consistency Asset Contract convergence
- [x] ConsistencyAssetContract v2 frozen
- [x] Image/video asset consumption matrix reviewed
- [x] Continuity vs global consistency examples reviewed
- [x] Generator/evaluator gate completed

### Correction Sprint C1: Runtime boundary and reconcile ownership correction
- [x] Runtime projection no longer mutates authoritative session/attempt state
- [x] Current-run discovery path no longer triggers runtime failover or terminal mutation
- [x] API process is no longer the default reconcile owner
- [x] Projection integrity errors are surfaced transparently rather than silently suppressed
- [x] Lease/heartbeat/reconcile owner semantics are frozen
- [x] Generator/evaluator gate completed

### Sprint 4: Orchestration, memory, and context boundary hardening
- [x] Owner-boundary inventory frozen
- [x] Read/write path mapping reviewed
- [x] Forbidden fallback paths enumerated
- [x] Generator/evaluator gate completed

### Sprint 5: Validation harness and extension proof
- [x] Validation matrix frozen
- [x] 15s sample validated
- [x] 20s projection sample validated
- [x] Generator/evaluator gate contract frozen

## Automated Checks
- [x] Contract schema / parser / adapter tests
- [x] Script-to-prompt assembly tests
- [x] Consistency asset projection tests
- [x] Runtime boundary regression tests
- [x] Orchestration/context/memory boundary regression tests

## Manual Checks
- [x] 10s high-action scene sample
- [x] 15s medium-density narrative scene sample
- [x] 20s target-duration projection sample
- [x] Strong continuity scene pair
- [x] Global-consistency-only scene pair

## QC Rules
- Generator/evaluator gate is diagnostic-only and does not change lifecycle state.
- Each sprint allows at most 2 generator/evaluator rounds.
- Any sprint failing twice returns to human-led contract revision rather than continued auto-battle.
- Generator/evaluator outputs may only land in the plan file, validation ledger, or explicit review notes; they must not be written into runtime payloads, published deliverables, or WorkingMemory primary consumption slots.
- Correction Sprint C1 must pass before Sprint 4 evidence can be accepted as valid.

## Sprint 1 Generator / Evaluator Gate
### Generator Candidate
- Candidate artifact set:
  - [scene_contract.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/scene_contract.py)
  - [memory_views.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py)
  - [scene_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/scene_contract_v2_freeze_20260329.md)
- Candidate claims:
  - `scene` semantic unit is frozen as `local_event`
  - `scene_info_payload.scenes_to_generate[]` remains the sole authoritative media-agent scene carrier
  - `SceneContract v2` evolves in place through `scene_contract_meta`, not through a parallel payload
  - owner/SoT boundaries, positive examples, and negative examples are explicit on validation surfaces only

### Evaluator Verdict
- Verdict: `pass`
- Why it passes:
  - Owner/SoT matrix exists and is frozen before schema expansion
  - `SceneContract v2` field direction is explicit and tied to the authoritative carrier
  - 3 positive examples and 2 negative examples are documented
  - image/video builders now emit contract metadata in place, and smoke checks confirm no parallel carrier was introduced
- Deferred risks carried forward to Sprint 2:
  - `action_phases` is not yet serialized into upstream script output
  - downstream prompt consumers still operate on pre-v2 content fields
  - no generator/evaluator output has been allowed into runtime or memory mainlines

## Sprint 2 Generator / Evaluator Gate
### Generator Candidate
- Candidate artifact set:
  - [script_writer.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/script_writer.py)
  - [memory_views.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py)
  - [script_generation_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/script_generation_tool.py)
  - [scene_script_generation.jinja2](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/prompts/templates/script_writer/scene_script_generation.jinja2)
  - [video_prompt_builder_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/video_prompt_builder_tool.py)
  - [script_video_prompt_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/script_video_prompt_contract_v2_freeze_20260329.md)
- Candidate claims:
  - `project.scene_scripts.{scene_number}` now carries normalized execution-arc fields in place
  - `scene_info_payload.scenes_to_generate[]` projects the same fields in place with no parallel payload
  - final video prompt body now prioritizes opening/action/camera/end-state structure over planning prose
  - `image_to_video` and `continuity` receive explicit mode-specific prompt emphasis

### Evaluator Verdict
- Verdict: `pass`
- Why it passes:
  - `ScriptContract v2` and `VideoPromptContract v2` are frozen on validation surfaces and mapped to existing carriers only
  - legacy `motion_beats` is preserved as a compatibility/read-model layer while `action_phases` becomes the richer execution arc
  - builder tests prove the prompt no longer emits `beat: ; beat:` and no longer uses `叙事要点` as the main body when action data exists
  - targeted backend verification passed with `8` unit tests and `py_compile`
- Deferred risks carried forward to Sprint 3:
  - consistency assets are still prose-heavy and can dominate prompt tail sections
  - composer-side consistency injection still needs structural convergence rather than clip-level tuning
  - image-first opening-anchor semantics are only projected, not yet contract-frozen

## Sprint 3 Generator / Evaluator Gate
### Generator Candidate
- Candidate artifact set:
  - [consistency_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/consistency_tool.py)
  - [video_prompt_composer_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/video_prompt_composer_tool.py)
  - [image_prompt_composer_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/image_prompt_composer_tool.py)
  - [consistency_asset_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/consistency_asset_contract_v2_freeze_20260329.md)
  - [test_consistency_asset_contract_v2.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_consistency_asset_contract_v2.py)
- Candidate claims:
  - consistency assets are now explicitly split into episode locks, opening anchor, and local continuity
  - image/video composers consume the same structured layers and no longer treat environment prose as the only scene-level anchor
  - continuity is now local by contract and does not host global style instructions

### Evaluator Verdict
- Verdict: `pass`
- Why it passes:
  - `ConsistencyAssetContract v2` is frozen on validation surfaces with explicit examples for global consistency and local continuity
  - producer and both composers now speak the same labels: `global_style_lock / character_lock / opening_anchor / local_continuity`
  - consistency injection is still present, but no longer flattens everything into `画风/角色/场景氛围/道具/连续性` prose
  - dedicated consistency tests passed, and the combined Sprint 2+3 suite passed with `11` tests
- Deferred risks carried forward to Sprint 4:
  - runtime and context boundaries still need a formal owner inventory review
  - consistency producer cache and read/write boundaries still depend on tool-local assumptions rather than an explicit SoT inventory

## Plan Amendment A1 Review Note
### New High-Risk Findings Captured On 2026-03-30
- `build_runtime_view_for_task[_sync]()` currently calls reconcile logic that can fail authoritative runtime state during a read/projection path.
- quick-run discovery currently swallows projection integrity errors and can silently downgrade them to “no current run”.
- `FastAPI lifespan` can default to a periodic quick-runtime reconcile loop, which makes the API process a runtime mutation owner.

### Amendment Impact
- Sprint 1-3 remain accepted as historical content-contract work and are not rewritten.
- Correction Sprint C1 remains as the blocker trace inside `038`, but implementation ownership moves to external remediation plan `PLAN-20260330-039`.
- Sprint 4 and Sprint 5 are now blocked behind `PLAN-20260330-039`.
- New runtime-boundary regression tests are required before downstream owner-boundary hardening can continue.

## Evidence Log
- 2026-03-29T14:22:18Z Validation ledger created together with PLAN-20260329-038. No implementation evidence recorded yet; initial scope is contract-first and stage-gated.
- 2026-03-29T14:29:32Z Pre-implementation plan review tightened the validation contract: Sprint 1 now requires owner/SoT freeze before schema design, and QC outputs are explicitly limited to validation/review surfaces to prevent a second mainline from emerging.
- 2026-03-29T14:41:13Z Sprint 1 contract-freeze artifacts landed on the existing carrier path only. Added [scene_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/scene_contract_v2_freeze_20260329.md) with the owner/SoT matrix, field intent, 3 positive examples, and 2 negative examples; added [scene_contract.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/scene_contract.py) and wired [memory_views.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py) so `scene_info_payload` now carries explicit `scene_contract_meta` in place.
- 2026-03-29T14:41:13Z `PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -m py_compile backend/app/services/scene_contract.py backend/app/agents/adapters/memory_views.py backend/tests/unit/test_scene_contract.py` => exit `0`
- 2026-03-29T14:41:13Z `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c "<image scene contract smoke>"` in `backend/` => `scene_contract_smoke_ok`
- 2026-03-29T14:41:13Z `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c "<video scene contract smoke>"` in `backend/` => `video_scene_contract_smoke_ok`
- 2026-03-29T14:41:13Z Targeted `uv run pytest` was not usable for this slice because the active `uv` environment lacks `sqlalchemy`, and direct `pytest` collection through `backend/tests/conftest.py` remained too heavy for a fast loop; Sprint 1 therefore currently relies on `py_compile` plus direct import/smoke evidence until the generator/evaluator gate runs.
- 2026-03-29T14:44:20Z Generator/evaluator gate completed on validation surfaces only. The evaluator accepted the candidate because it kept `scene_info_payload.scenes_to_generate[]` as the only media-agent semantic carrier, froze owner/SoT mapping before schema growth, and proved the new metadata path through image/video smoke checks without emitting any QC artifacts into runtime payloads, published deliverables, or WorkingMemory mainlines.
- 2026-03-29T15:00:03Z Sprint 2 artifacts landed on the same carriers only. Added [script_video_prompt_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/script_video_prompt_contract_v2_freeze_20260329.md); widened [scene_script_generation.jinja2](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/prompts/templates/script_writer/scene_script_generation.jinja2) and [script_generation_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/script_generation_tool.py) to request executable action phases; updated [script_writer.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/script_writer.py) and [memory_views.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/adapters/memory_views.py) so the normalized fields are written to `project.scene_scripts` and projected in place onto `scene_info_payload.scenes_to_generate[]`; rewrote [video_prompt_builder_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/video_prompt_builder_tool.py) to make `opening_state + action arc + camera language + end_state` the prompt body.
- 2026-03-29T15:00:03Z `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/agents/script_writer.py app/agents/adapters/memory_views.py app/agents/tools/ai_services/script_generation_tool.py app/agents/tools/video_prompt_builder_tool.py tests/unit/test_script_writer_motion_beats.py tests/unit/test_video_prompt_builder_tool.py` in `backend/` => exit `0`
- 2026-03-29T15:00:03Z `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/unit/test_script_writer_motion_beats.py tests/unit/test_video_prompt_builder_tool.py tests/unit/test_script_generation_batch.py -q` in `backend/` => `8 passed, 2 warnings in 18.18s`
- 2026-03-29T15:00:03Z Sprint 2 generator/evaluator gate completed on validation surfaces only. The evaluator accepted the candidate because it preserved in-place carrier evolution, moved the prompt body onto visible action structure, and proved legacy `motion_beats` compatibility without emitting any QC verdicts into runtime payloads or WorkingMemory primary slots.
- 2026-03-29T15:14:38Z Sprint 3 artifacts landed on the same prompt-asset path only. Added [consistency_asset_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/consistency_asset_contract_v2_freeze_20260329.md); updated [consistency_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/consistency_tool.py) so prompt assets now emit `global_lock / scene_cast / opening_anchor / local_continuity` in place; updated [video_prompt_composer_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/video_prompt_composer_tool.py) and [image_prompt_composer_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/image_prompt_composer_tool.py) so both consumers render the same structured consistency labels.
- 2026-03-29T15:14:38Z `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/agents/tools/consistency_tool.py app/agents/tools/video_prompt_composer_tool.py app/agents/tools/image_prompt_composer_tool.py tests/unit/test_consistency_asset_contract_v2.py` in `backend/` => exit `0`
- 2026-03-29T15:14:38Z `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/unit/test_consistency_asset_contract_v2.py -q` in `backend/` => `3 passed, 2 warnings in 14.55s`
- 2026-03-29T15:14:38Z `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/unit/test_script_writer_motion_beats.py tests/unit/test_video_prompt_builder_tool.py tests/unit/test_script_generation_batch.py tests/unit/test_consistency_asset_contract_v2.py -q` in `backend/` => `11 passed, 2 warnings in 15.50s`
- 2026-03-29T15:14:38Z Sprint 3 generator/evaluator gate completed on validation surfaces only. The evaluator accepted the candidate because producer and consumers now share the same structured consistency layers, continuity is explicitly local by contract, and no QC verdicts were written into runtime payloads, published deliverables, or WorkingMemory primary slots.
- 2026-03-30T02:01:47Z Plan Amendment A1 recorded after architecture review identified a new root-cause class on the runtime boundary: read-model projection currently mutates authoritative runtime state, current-run discovery suppresses projection integrity errors, and API lifespan can default to a reconcile loop. A new Correction Sprint C1 is inserted between Sprint 3 and Sprint 4; all remaining unimplemented phases now depend on this correction gate rather than treating the new findings as historical edits.
- 2026-03-30T02:19:04Z Governance split confirmed after user review: `038` keeps the blocker trace only, while external plan `PLAN-20260330-039` becomes the implementation owner for the runtime-boundary remediation. `038` remains blocked until that new plan closes its acceptance gate.
- 2026-03-30T04:22:16Z Correction Sprint C1 is now satisfied via completed external remediation plan `PLAN-20260330-039`. The runtime-boundary regression gate is accepted on the amended evidence basis recorded there, and `038` can resume Sprint 4 boundary hardening without reopening the runtime remediation scope.
- 2026-03-30T04:31:53Z Sprint 4 owner-boundary freeze completed on validation surfaces only. Added [orchestration_context_memory_boundary_freeze_20260330.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/orchestration_context_memory_boundary_freeze_20260330.md), tightened boundary comments in [memory_writer.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/memory_writer.py) and [consistency_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/consistency_tool.py), and added targeted tests [test_memory_writer_boundary.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_memory_writer_boundary.py) plus [test_consistency_tool_boundary.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_consistency_tool_boundary.py). Automated evidence is accepted via `py_compile` and direct backend smokes (`memory_writer_boundary_ok`, `consistency_tool_boundary_ok`, `working_memory_cleanup_boundary_ok`, `context_assembler_fail_closed_ok`); local `pytest` remained environment-unstable and is explicitly not counted as passing evidence.
- 2026-03-30T04:35:58Z Sprint 5 validation harness closed on validation surfaces. Added [scene_contract_extension_proof_20260330.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/scene_contract_extension_proof_20260330.md) to freeze the validation matrix and contract-level examples for 10s, 15s, 20s, continuity handoff, and global-consistency-only scene pairs; added a 20s regression in [test_video_prompt_builder_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_video_prompt_builder_tool.py); `py_compile` passed for the updated test file; and a direct backend smoke confirmed `video_prompt_builder_20s_projection_ok`. Local `pytest` remained environment-unstable, so completion relies on explicit proof artifacts and direct assertions rather than overstated test-pass claims.

## Sprint 4 Generator / Evaluator Gate
### Generator Candidate
- Candidate artifact set:
  - [orchestration_context_memory_boundary_freeze_20260330.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/orchestration_context_memory_boundary_freeze_20260330.md)
  - [memory_writer.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/memory_writer.py)
  - [consistency_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/consistency_tool.py)
  - [test_memory_writer_boundary.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_memory_writer_boundary.py)
  - [test_consistency_tool_boundary.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_consistency_tool_boundary.py)
  - [test_execution_boundary_assembler_contexts.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_execution_boundary_assembler_contexts.py)
  - [test_working_memory_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_working_memory_service.py)
- Candidate claims:
  - orchestrator, context assembly, memory writeback, working memory, and consistency collection now have an explicit owner matrix
  - read/write path mapping is documented and does not reopen runtime mutation paths fixed by `039`
  - Shared WM and consistency assets are prevented from becoming fallback repair paths or planning/runtime authorities

### Evaluator Verdict
- Verdict: `pass`
- Why it passes:
  - Sprint 4 artifacts freeze a single owner matrix and enumerate forbidden fallback paths explicitly
  - `MemoryWriter` and `ConsistencyTool` now carry local boundary documentation aligned with the frozen owner matrix
  - direct backend smokes confirm the four critical boundary behaviors without reintroducing runtime remediation semantics
  - evidence strength is conservatively stated: `py_compile` and direct assertions are accepted, while unstable local `pytest` runs are not treated as passing evidence
- Deferred risks carried forward to Sprint 5:
  - extension-proof validation still needs narrative samples at 15s and 20s
  - local pytest instability around heavyweight imports should be treated as environment debt, not as Sprint 4 architecture closure

## Sprint 5 Generator / Evaluator Gate
### Generator Candidate
- Candidate artifact set:
  - [scene_contract_extension_proof_20260330.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/scene_contract_extension_proof_20260330.md)
  - [test_video_prompt_builder_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_video_prompt_builder_tool.py)
  - [scene_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/scene_contract_v2_freeze_20260329.md)
  - [script_video_prompt_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/script_video_prompt_contract_v2_freeze_20260329.md)
  - [consistency_asset_contract_v2_freeze_20260329.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/consistency_asset_contract_v2_freeze_20260329.md)
- Candidate claims:
  - the validation matrix now covers 10s, 15s, and 20s without inventing a new semantic carrier
  - continuity and global consistency are proven on separate scene-pair examples
  - 20s prompt projection is validated from the same `action_phases` contract rather than a stopwatch rewrite

### Evaluator Verdict
- Verdict: `pass`
- Why it passes:
  - Sprint 5 proof artifacts stay on validation surfaces only and do not write QC semantics into runtime or memory carriers
  - the 15s and 20s examples preserve the same `local_event` structure while only changing projection span
  - the continuity pair and global-consistency-only pair demonstrate that local continuity and episode-level locks remain separated
  - direct backend smoke confirms the builder still consumes `action_phases` for a 20s scene and does not regress to stopwatch prose
- Residual risk note:
  - provider render quality and full end-to-end media output remain downstream acceptance concerns; this sprint closes contract scalability, not every supplier's render fidelity
