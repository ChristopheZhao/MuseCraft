# Validation Placeholder: PLAN-20260401-044

- Plan ID: PLAN-20260401-044
- Status: completed
- Purpose:
  - Record targeted validation for scene semantics repair, prompt synthesis rebuild, image anchor repair, and mode policy changes.

## Completed Validation Streams
- `scene-contract-review`
  - Covered by the targeted suite already recorded above, especially `tests/unit/test_scene_contract.py`.
  - Current contract/path evidence:
    - `scene_info_payload.scenes_to_generate[]` still carries factual fields such as `scene_thesis`, `image_purpose`, and `frame_thesis`
    - `scene_contract_meta` remains present
    - `generation_diagnostics` is absent from both `scene_info_payload` and `context`
  - Result:
    - Contract-first mainline survived the Stage 4 boundary correction; no heuristic QC surface remains in the runtime carrier.

- `prompt-structure-review`
  - Targeted suite passed after runtime heuristic cleanup:
    - `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/unit/test_video_prompt_builder_tool.py tests/unit/test_consistency_asset_contract_v2.py tests/unit/test_image_prompt_normalization.py tests/unit/test_scene_contract.py`
    - Result: `19 passed, 5 skipped`
  - Assertions now cover:
    - `scene_thesis`-led prompt structure remains intact
    - `frame_thesis` / `image_purpose` remain on the factual contract path
    - `generation_diagnostics` and per-tool `diagnostics` metadata stay absent from payload/context surfaces

- `single-scene-script-sample-review`
  - Direct rendered sample is recorded in `/tmp/plan044_script_prompt_sample.txt`
  - The current script template/render path now visibly carries `场景主命题`、`全局叙事上下文`、`时长约束`
  - The requirement block explicitly encodes the 8s+ visible-state-change rule and the downgraded `camera_hint` role

- `image-anchor-purpose-review`
  - Historical baseline from `[mas_workflow.log](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/logs/mas/mas_workflow.log#L12167)` showed all 5 image tasks being planned as `scene_opening_anchor + full_body`.
  - Rebuilt current prompts for the same preserved workflow context were recorded to `/tmp/plan044_multiscene_validation.json`.
  - Current image-purpose distribution for scenes 1-5:
    - scene 1: `action_keyframe`
    - scene 2: `action_keyframe`
    - scene 3: `climax_peak`
    - scene 4: `action_keyframe`
    - scene 5: `action_keyframe`
  - Result:
    - The image path is no longer defaulting the whole teaser to opening-anchor stills.

- `mode-policy-regression`
  - Historical baseline from `[mas_workflow.log](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/logs/mas/mas_workflow.log#L12242)` and following lines showed scenes 1, 2, 4, and 5 being dispatched as `mode=image_to_video` after prompt composition, driven by reference images.
  - Intermediate pre-A4 evidence from `/tmp/plan044_multiscene_validation.json` showed the repaired prompt-selection layer had drifted into a new error:
    - scene strategies were `action_keyframe` / `climax_peak`
    - the execution path overrode factual image-backed inputs and resolved those scenes to `prompt_mode=text_to_video`
  - Post-A4 correction evidence:
    - current builder smoke confirms a scene carrying `image_url` now resolves to `prompt_mode=image_to_video`
    - current focused provider rerun for scene 4 also used the restored image-backed path and succeeded
  - Result:
    - the earlier strategy-based override is now treated as a regression that has been removed
    - accepted mode policy is restored to factual input mapping: `有图走图，tool 不丢图`
  - Note:
    - The pre-A4 `text_to_video` evidence remains useful as regression proof, but it is no longer the accepted current behavior after the boundary correction.

## In-Progress Validation Streams
- none

## Representative Prompt Diff
- Validation timestamp: `2026-04-01T07:35:51Z`
- Sample: scene 3 combat beat from the real run `46766c83-a414-44aa-a13f-5940e3841adb`
- Old evidence:
  - Video combined prompt from `[mas_workflow.log](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/logs/mas/mas_workflow.log#L12476)` led with `目标时长/创作重点` and still contained `镜头快速推近镜头`、`镜头镜头剧烈震动` plus a trailing `一致性要求` block; generation mode was `image_to_video`.
  - Image combined prompt from `[mas_workflow.log](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/logs/mas/mas_workflow.log#L11990)` still used append-only `一致性要求` and an opening-anchor tail after a static single-frame prompt.
- Current validation method:
  - Re-ran current prompt builders against the preserved context files:
    - `backend/storage/temp/context/video_generator_46766c83-a414-44aa-a13f-5940e3841adb.json`
    - `backend/storage/temp/context/image_generator_46766c83-a414-44aa-a13f-5940e3841adb.json`
  - Validation artifact was generated to `/tmp/plan044_validation_scene3.json` for local inspection only.
- Current video prompt evidence:
  - `prompt_mode=text_to_video`
  - `scene_strategy=climax_peak`
  - Prompt starts with `主生成目标`
  - No trailing `一致性要求`
  - No duplicated camera-noise phrases such as `镜头快速推近镜头` or `镜头镜头`
- Current image prompt evidence:
  - `image_purpose=climax_peak`
  - `frame_thesis=画面定格在能量迸发强光的最亮处，余波似乎仍在震颤`
  - Prompt root is `关键帧构图：`
  - No trailing `一致性要求`
- Validation reading:
  - The same class of action scene is no longer anchored as an opening static frame by default.
  - Prompt synthesis remains hierarchical after heuristic cleanup, so the boundary correction did not regress the earlier root-cause repairs.

## Single-Scene Script Prompt Sample
- Validation artifact:
  - `/tmp/plan044_script_prompt_sample.txt`
- Sample setup:
  - Synthetic single-scene script-generation input using the current `scene_script_generation.jinja2` template and `ScriptGenerationTool._build_context_blocks(...)`
  - Scene thesis: `黑袍修士先手压制，韩立正面迎击，局势升级为爆炸失控`
  - Target duration: `10s`
  - Story context includes narrative arc, episode context, project brief/theme, and approved script fragment
- Observed prompt properties:
  - Prompt explicitly contains `场景主命题`
  - Prompt explicitly contains `全局叙事上下文`
  - Prompt explicitly contains `时长约束`
  - Prompt requirement block explicitly demands:
    - output `scene_thesis`
    - visible `opening_state / event_trigger / end_state`
    - 8s+ scenes must have 2+ visible state changes
    - `camera_hint` is optional and cannot replace action progression
- Supporting check:
  - `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/unit/test_script_generation_batch.py -k "scene_thesis_and_story_context"`
  - Result in this environment: `1 skipped, 2 deselected`
  - Note:
    - The async test is present and aligned with the expected fields, but it was skipped because the current local pytest environment does not have the async plugin enabled.
    - Therefore the validation evidence for this stream relies on the direct rendered prompt sample rather than counting the skipped test as a pass.

## Pending Validation Streams
- none

## Prompt-Level Story Coherence Read
- Validation artifact:
  - `/tmp/plan044_multiscene_validation.json`
- Current prompt-level sequence for scenes 1-5 reads as:
  - scene 1: 韩立在山洞内聚气觉醒
  - scene 2: 新反派现身并压迫升级，形成正面对峙
  - scene 3: 双方交锋升级为爆炸失控
  - scene 4: 爆发后的命运抉择与心理收束
  - scene 5: 高潮闪回与标题收束
- Reading:
  - Compared with the earlier slideshow-like pattern, the rebuilt prompt chain is now legible as a teaser arc rather than five unrelated static visuals.
  - Scene-to-scene event order is materially clearer at the prompt level.
- Residual risk:
  - Scene 4 still reads relatively static compared with scene 3, so the “story-driven” improvement is stronger than the “fully de-close-up” improvement.
  - No new mp4 set was regenerated in this validation pass, so this stream remains open until media-level review confirms the prompt-level improvement survives actual generation.

## Historical Media Baseline Review
- Validation timestamp: `2026-04-01T08:02:29Z`
- Scope:
  - Review the currently available local mp4 artifacts under `backend/storage/temp/videos/scene_1.mp4` ... `scene_5.mp4`
  - Determine whether they can be treated as post-fix acceptance evidence
- Baseline identification:
  - File modification times are `2026-04-01 10:39:27` through `2026-04-01 10:47:41`, which line up with the historical problematic run `46766c83-a414-44aa-a13f-5940e3841adb`.
  - `[mas_workflow.log](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/logs/mas/mas_workflow.log#L12218)` through `[mas_workflow.log](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/logs/mas/mas_workflow.log#L12504)` show these videos were generated by the old chain:
    - scenes 1, 2, 4, 5 via `video_generation.generate_with_continuity(...)` with reference images
    - scene 3 via continuity from `./storage/temp/videos/scene_2.mp4`
    - upstream image planning still used `scene_opening_anchor + full_body`
  - Result:
    - The local mp4 set is historical baseline evidence for the failure mode, not post-fix acceptance media.
- Extracted media facts:
  - All five videos are `960x960`, `24fps`, `10.041667s`
  - Sampled frame extracts were stored to `/tmp/plan044_frames/scene_*_0{1,2,3}.jpg`
  - Frame hashes differ within every scene, confirming these clips are not literal single-frame stills
- Intra-scene change evidence from sampled-frame SSIM:
  - scene 1 `first_last`: `All:0.817898`
  - scene 2 `first_last`: `All:0.883350`
  - scene 3 `first_last`: `All:0.435362`
  - scene 4 `first_last`: `All:0.850825`
  - scene 5 `first_last`: `All:0.566042`
- Reading:
  - The historical media baseline is consistent with the earlier diagnosis rather than contradicting it.
  - scene 3 and scene 5 show much larger visual change, which matches the prompt/log reading that they contain stronger event or montage content.
  - scene 1, scene 2, and scene 4 remain relatively stable over sampled frames, which is consistent with the “state display / confrontation / emotional hold” bias seen in the old prompts.
- Boundary verdict:
  - This review strengthens confidence in the original failure diagnosis.
  - It does **not** close `end-to-end-story-coherence-review`, because no fresh post-fix mp4 set was produced in this validation pass.

## Post-Fix Scene 4 Provider Rerun Probe
- Validation timestamp: `2026-04-01T08:22:00Z`
- Purpose:
  - Probe whether the repaired prompt chain can survive a real provider call on the current mainline, using a focused high-risk scene rather than the full 5-scene workflow.
- Method:
  - Built the current scene 4 video prompt from `storage/temp/context/video_generator_46766c83-a414-44aa-a13f-5940e3841adb.json` through the repaired `video_prompt_builder + consistency_tool + video_prompt_composer` path.
  - Executed one real provider call through `DoubaoVideoService.generate_video(prompt=..., duration=10)` and saved the raw evidence to `/tmp/plan044_scene4_postfix_result.json`.
- Evidence:
  - Scene 4 current composed prompt length: `1638 bytes / 582 chars`
  - Nearby scenes on the same repaired chain:
    - scene 2: `1686 bytes / 598 chars`
    - scene 3: `1667 bytes / 595 chars`
    - scene 4: `1638 bytes / 582 chars`
  - Provider result:
    - task id: `cgt-20260401171612-54g2r`
    - mode: `text_to_video`
    - status: `FAILED`
    - error: `InvalidParameter: Invalid content.text`
- Reading:
  - This is not a media-quality pass/fail result; it is a provider-contract failure on the repaired prompt surface.
  - Because scene 2/3/4 prompt sizes are all in the same range, the current evidence points more toward a provider-incompatible prompt shape or text format than a scene-4-only exception.
  - The repaired chain is therefore not yet media-acceptance-ready on the current Doubao text-to-video path.
- Boundary verdict:
  - `end-to-end-story-coherence-review` remains open.
  - A new review/amendment is required before further implementation, because the blocker has moved from slideshow diagnosis into provider text-contract compatibility on the repaired prompt format.

## Provider `content.text` Shape Probe
- Validation timestamp: `2026-04-01T09:54:15Z`
- Purpose:
  - Verify whether treating the internal hierarchical prompt as Doubao `content.text` is itself sufficient to reproduce the same `Invalid content.text` failure.
- Method:
  - Sent three real create-task probes to `https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks` with model `doubao-seedance-1-5-pro-251215`.
  - Probe artifact for create responses: `/tmp/plan044_content_text_probe.json`
  - Variants:
    - `structured_with_flags`: current hierarchical scene 4 prompt + `--dur 10`
    - `structured_no_flags`: same hierarchical prompt without inline flags
    - `natural_with_flags`: flattened natural-language rewrite + `--dur 10`
- Results:
  - create-stage acceptance:
    - all three variants returned `200` and produced task ids
  - follow-up query results:
    - `structured_with_flags` -> `succeeded`
    - `structured_no_flags` -> `failed`
    - `natural_with_flags` -> `succeeded`
  - raw failed-task provider error:
    - `InvalidParameter: Invalid content.text`
- Reading:
  - The broad hypothesis “internal structured prompt serialized to `content.text` is inherently incompatible with Doubao” is falsified by the successful `structured_with_flags` task.
  - The stronger current evidence is that, on the active `contents/generations` endpoint, the same hierarchical prompt without inline generation-control suffixes can fail asynchronously with the exact same `Invalid content.text` error.
  - Therefore the open compatibility issue has narrowed from “structured prompt shape is invalid” to “provider-specific `content.text` serialization for `contents/generations` is underspecified and must be reviewed explicitly”.

## Structured Prompt i2v/t2v Comparison
- Validation timestamp: `2026-04-01T10:23:50Z`
- Purpose:
  - Determine whether the active blocker is really generic `content.text` incompatibility, or whether it is tied to the recent `text_to_video` mode selection that drops the reference image for `action_keyframe/climax_peak` scenes.
- Method:
  - Reused the exact failing scene-4 hierarchical structured prompt from `/tmp/plan044_scene4_postfix_result.json`.
  - Sent one additional real create-task probe to the same `contents/generations` endpoint with the same model, but reintroduced the original `scene_4_image.jpg` as a second `content` item.
  - Create artifact:
    - `/tmp/plan044_structured_no_flags_with_image_create.json`
  - Task id:
    - `cgt-20260401181942-gczcs`
- Results:
  - `structured_no_flags + no image`:
    - failed earlier with `InvalidParameter: Invalid content.text`
  - `same structured prompt + image_url`:
    - create accepted with `200`
    - final task status: `succeeded`
- Reading:
  - The same hierarchical structured prompt is provider-acceptable when routed through the image-backed path on the same model and endpoint.
  - This materially weakens the hypothesis that the blocker is mainly caused by prompt structure alone.
  - The evidence now points more strongly to the new mode-policy behavior that strips the reference image and converts certain scenes from `image_to_video` to `text_to_video`.
- Boundary verdict:
  - The next plan review should target mode-policy regression first.
  - `end-to-end-story-coherence-review` remains open, but the primary precondition for further implementation is no longer a generic prompt-shape rewrite; it is a review of the current i2v/t2v switching policy.

## Boundary Reading After Mode Comparison
- Validation timestamp: `2026-04-01T10:29:46Z`
- Architectural reading:
  - The i2v/t2v probe result changes the governing interpretation of the bug.
  - The execution layer had begun using semantic labels (`action_keyframe`, `climax_peak`) to override factual upstream inputs and strip `image_url`.
  - That behavior is now treated as a boundary violation rather than a valid optimization path.
- Boundary verdict:
  - `有图走图，tool 不丢图` is now the accepted execution default for the next implementation slice.
  - Any future choice to ignore an available image input must come from an explicit upstream contract decision, not from execution-tool inference.

## A4 Implementation Verification
- Validation timestamp: `2026-04-01T10:36:27Z`
- Scope:
  - Verify that the boundary correction was implemented as factual execution mapping rather than as a new compatibility shim.
- Evidence:
  - `video_generation_tool_v2._determine_generation_mode(...)` no longer accepts or uses `scene_strategy` to override image-backed requests.
  - The execution path no longer clears `final_image_input` or emits `image_mode_overridden` / `reference_image_skipped`.
  - `video_prompt_builder_tool._resolve_prompt_mode(...)` now treats `image_url` as sufficient for `image_to_video`, without semantic-label overrides.
  - `python3 -m py_compile backend/app/agents/tools/ai_services/video_generation_tool_v2.py backend/app/agents/tools/video_prompt_builder_tool.py backend/tests/unit/test_video_generation_tool.py backend/tests/unit/test_video_prompt_builder_tool.py`
  - Direct builder smoke passed with `VIDEO_PROMPT_SMOKE_OK`, confirming a scene carrying `image_url` now resolves to `prompt_mode=image_to_video`.
- Boundary verdict:
  - The A4 correction is in place on the code path and removes the previously proven-erroneous hardcoded override.
  - A full provider rerun is still valuable, but the execution boundary is now aligned with the amendment.

## Post-A4 Scene 4 Provider Recovery Probe
- Validation timestamp: `2026-04-01T11:28:30Z`
- Purpose:
  - Verify that the boundary-corrected mainline (`有图走图，tool 不丢图`) restores the real provider path for the original high-risk scene 4 sample.
- Method:
  - Rebuilt the current scene 4 prompt from `backend/storage/temp/context/video_generator_46766c83-a414-44aa-a13f-5940e3841adb.json`.
  - Confirmed current composed metadata resolves to `prompt_mode=image_to_video`.
  - Sent one real provider request through the current image-backed path and saved create-stage evidence to `/tmp/plan044_scene4_postfix_i2v_create.json`.
- Evidence:
  - task id: `cgt-20260401192830-rfdjg`
  - model: `doubao-seedance-1-5-pro-251215`
  - input shape:
    - `content.text`: current hierarchical scene 4 prompt
    - `content.image_url`: `https://multi-media-zs.oss-cn-shanghai.aliyuncs.com/images/scene_4_image.jpg`
  - provider result:
    - `status=succeeded`
    - `duration=10`
    - `generate_audio=true`
    - video URL returned by provider
- Reading:
  - The same scene 4 that previously failed after being forced onto the pure-text path now succeeds once the factual image-backed path is restored.
  - This materially strengthens the conclusion that the mainline blocker was the erroneous tool-layer mode override, not the hierarchical prompt design by itself.
- Boundary verdict:
  - A4 is not only code-correct; it is now supported by a real provider recovery sample on the restored path.
  - `end-to-end-story-coherence-review` still remains open because this is a focused scene-level probe, not a fresh full-trailer acceptance run.

## Mainline 2-4 Slice Rerun And Factual Mapping Gap
- Validation timestamp: `2026-04-01T11:46:45Z`
- Purpose:
  - Verify the repaired mainline by running a consecutive multi-scene slice (2-4) through the registered `video_generation.generate_with_continuity` tool, rather than through a one-off direct provider probe.
- Method:
  - Reused `backend/storage/temp/context/video_generator_46766c83-a414-44aa-a13f-5940e3841adb.json`
  - Executed scenes 2, 3, and 4 sequentially through the current mainline tool path
  - Saved artifacts under `/tmp/plan044_postfix_slice/`
- Evidence:
  - all three scenes succeeded:
    - scene 2: `cgt-20260401194048-njzxk`
    - scene 3: `cgt-20260401194238-5ntg9`
    - scene 4: `cgt-20260401194351-9l98v`
  - however, every scene executed with:
    - `generation_mode = text_to_video`
    - `has_reference_image = false`
    - `image_input_url = null`
  - the same `scene_info_ref` facts still contain image URLs for scenes 2/3/4:
    - scene 2 -> `scene_2_image.jpg`
    - scene 3 -> `scene_3_image.jpg`
    - scene 4 -> `scene_4_image.jpg`
- Reading:
  - A4 removed the proven-erroneous semantic override, but the mainline execution path still does not hydrate factual `image_url` from `scene_info_ref` into execution params.
  - Therefore the restored boundary is only partially complete: direct image-backed calls can now succeed, but the ordinary `scene_info_ref` path still silently drops factual image inputs by omission.
- Boundary verdict:
  - This is a new factual-input mapping gap, not a quality heuristic issue.
  - The next correction must restore `scene_info_ref -> image_url` factual execution mapping without introducing any new semantic override logic.

## A5 Implementation Verification
- Validation timestamp: `2026-04-01T12:01:42Z`
- Scope:
  - Verify that the ordinary `scene_info_ref` mainline now hydrates factual media inputs into execution params, rather than only succeeding on direct one-off provider probes.
- Evidence:
  - `video_generation_tool_v2._generate_with_continuity(...)` now resolves factual runtime inputs from `scene_info_ref` and injects:
    - `image_url`
    - `depends_on_scene` when absent from explicit params
  - direct smoke artifact:
    - `/tmp/plan044_hydrate_scene_info.json`
  - direct smoke output:
    - `has_reference_image = true`
    - `generation_mode = image_to_video`
    - `image_input_url = https://example.com/scene2.png`
    - marker: `HYDRATE_SMOKE_OK`
  - static verification:
    - `python3 -m py_compile backend/app/agents/tools/ai_services/video_generation_tool_v2.py backend/tests/unit/test_video_generation_tool.py`
- Boundary verdict:
  - The new correction is still boundary-safe: it restores factual input mapping from an existing authoritative carrier and does not reintroduce semantic override logic.

## Post-A5 Mainline 2-4 i2v Slice
- Validation timestamp: `2026-04-01T12:01:42Z`
- Purpose:
  - Verify that the ordinary mainline now runs scenes 2-4 through the expected image-backed path, not just through ad hoc probes.
- Method:
  - Reused `backend/storage/temp/context/video_generator_46766c83-a414-44aa-a13f-5940e3841adb.json`
  - Executed scenes 2, 3, and 4 sequentially through the corrected `video_generation.generate_with_continuity` mainline
  - Saved artifacts under `/tmp/plan044_postfix_slice_i2v/`
- Evidence:
  - all three scenes succeeded:
    - scene 2: `cgt-20260401195351-9gt48`
    - scene 3: `cgt-20260401195556-h94wc`
    - scene 4: `cgt-20260401195736-g5c9b`
  - all three scenes now executed with:
    - `generation_mode = image_to_video`
    - `has_reference_image = true`
    - `image_input_url = scene_2/3/4_image.jpg`
  - downloaded mp4 artifacts:
    - `/tmp/plan044_postfix_slice_i2v/media/scene_2.mp4`
    - `/tmp/plan044_postfix_slice_i2v/media/scene_3.mp4`
    - `/tmp/plan044_postfix_slice_i2v/media/scene_4.mp4`
  - extracted-frame artifact:
    - `/tmp/plan044_postfix_slice_i2v/contact_sheet.jpg`
  - sampled first-last SSIM:
    - scene 2: `All=0.630755`
    - scene 3: `All=0.579067`
    - scene 4: `All=0.676804`
- Reading:
  - The corrected mainline now matches the accepted boundary rule: factual image-backed scenes stay image-backed through ordinary execution.
  - Contact-sheet review shows scene 2 and scene 3 now read as a coherent escalation chain from confrontation into direct clash and blast payoff.
  - scene 4 remains comparatively more static and introspective, but the media still shows visible state change across the clip instead of collapsing into a pure still-frame hold.
- Boundary verdict:
  - A5 closes the factual execution-mapping gap introduced after A4.
  - `end-to-end-story-coherence-review` improves from “prompt-only” to “representative media slice verified”, but a fresh full 1-5 trailer run is still required before full closeout.

## A6 `contents/generations` Contract Cleanup
- Validation timestamp: `2026-04-02T07:17:48Z`
- Purpose:
  - Verify that the Doubao adapter now serializes `contents/generations` requests according to the provider contract instead of appending inline control suffixes to `content.text`.
- Evidence:
  - `[doubao_services.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/doubao_services.py)` now places:
    - `duration` or `frames`
    - `resolution`
    - `ratio`
    at the top level of the JSON payload for `contents/generations`
  - local payload smoke confirms:
    - `content.text` remains the original structured descriptive prompt
    - `duration=10`
    - `resolution=720p`
    - `ratio=16:9`
    - `generate_audio=true`
    - no `--dur/--rs/--rt` suffixes remain in `content.text`
- Boundary verdict:
  - The provider adapter now respects contract-first serialization without reintroducing any runtime fallback or mode override logic.

## Full 1-5 Corrected-Mainline Trailer Rerun
- Validation timestamp: `2026-04-02T07:17:48Z`
- Purpose:
  - Close `end-to-end-story-coherence-review` with a fresh full-trailer run on the corrected mainline, rather than relying on representative slices only.
- Method:
  - Reused `backend/storage/temp/context/video_generator_46766c83-a414-44aa-a13f-5940e3841adb.json`
  - Executed scenes 1-5 sequentially through the corrected `video_generation.generate_with_continuity` mainline
  - Saved result artifacts under `/tmp/plan044_full_rerun/`
- Evidence:
  - all five scenes succeeded:
    - scene 1: `cgt-20260402145948-6d7rg`
    - scene 2: `cgt-20260402150119-97nnt`
    - scene 3: `cgt-20260402150423-ms7l5`
    - scene 4: `cgt-20260402150711-mznnm`
    - scene 5: `cgt-20260402150852-lflkr`
  - summary artifact:
    - `/tmp/plan044_full_rerun/summary.json`
  - downloaded media artifacts:
    - `/tmp/plan044_full_rerun/media/scene_1.mp4`
    - `/tmp/plan044_full_rerun/media/scene_2.mp4`
    - `/tmp/plan044_full_rerun/media/scene_3.mp4`
    - `/tmp/plan044_full_rerun/media/scene_4.mp4`
    - `/tmp/plan044_full_rerun/media/scene_5.mp4`
  - contact-sheet artifact:
    - `/tmp/plan044_full_rerun/contact_sheet.jpg`
  - all five scenes executed with:
    - `generation_mode = image_to_video`
    - `has_reference_image = true`
- Reading:
  - The fresh full-trailer rerun confirms the corrected mainline no longer depends on provider-unsafe text-only fallback paths.
  - Visual review of the contact sheet reads as a coherent teaser arc:
    - scene 1: 觉醒/聚气建立主角状态
    - scene 2: 正面对峙升级
    - scene 3: 交锋与爆发兑现
    - scene 4: 相对静态但仍有可见状态变化的收束/抉择段
    - scene 5: 终局打点与标题收束
  - scene 4 remains the calmest beat, but the full sequence no longer presents as the old “静帧串联 + 特写撑时长” failure mode.
- Boundary verdict:
  - `end-to-end-story-coherence-review` is closed.
  - `PLAN-20260401-044` now has both contract-level and media-level closeout evidence.
