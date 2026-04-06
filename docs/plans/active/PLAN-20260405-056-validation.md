# Validation Ledger: PLAN-20260405-056

## Scope
- Validate the new `quality_checker` diagnostic-distortion stream without reopening `054` or `055` by default.
- Freeze the real sample first, then allow implementation only after Stage A explicitly names the owner boundary.
- Treat runtime/control-plane closure and final-video authority as existing truths unless Stage A proves otherwise.

## Review / Boundary Gate
- [x] Review confirms this is a separate follow-on from `055`, not a reopened runtime/control-plane failure
- [x] Review confirms `054` remains reference-only for `project.final_video` ownership; this stream does not move final-video authority into QC
- [x] Review confirms Stage A must freeze evidence before any implementation
- [x] Review confirms no case-specific hardcode is allowed as the first response
- [x] Review confirms QC consumer boundary is the first owner hypothesis, ahead of runtime/control-plane blame

## Stage A Gate: RCA / Owner Freeze
- [x] Freeze the real workflow/task sample:
  - workflow/task id `9587c5b5-216c-4bf4-8a37-4c9078b4e900`
  - task db id `1060`
  - workflow session id `55`
- [x] Freeze `project.final_video` evidence:
  - `summary_output.final_video_url = /files/outputs/videos/蛮荒记预告_final.mp4`
  - `summary_output.final_video_path = /mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/storage/outputs/videos/蛮荒记预告_final.mp4`
  - final file exists and `ffprobe` reports ~45.27s, h264/aac, ~17.0 MB
- [x] Freeze the actual QC-observed technical metadata:
  - QC output metadata was only `{"duration": 0}`
  - QC flagged `file not found`, `duration too short`, `file size suspiciously small`, and `format is not MP4`
- [x] Freeze the available upstream concept/timeline facts:
  - script published deliverable contains `concept_plan` and `scene_overview`
  - `scene_overview` contains 5 scenes totaling 45.0s
  - image/video temp context snapshots also contain the same `scene_overview`
- [x] Freeze the actual QC-observed content-analysis inputs by output inversion:
  - `scene_breakdown.total_scenes = 0`
  - `scene_breakdown.total_duration = 0`
  - no `Missing scenes: expected 5, got 0` issue was emitted
  - this only matches `composition_timeline=[]` and `concept_plan.scenes=[]` at QC analysis time
- [x] Freeze the actual QC prompt/input owner path:
  - live prompt is rendered from legacy `backend/config/prompts/agents/quality_checker.yaml`
  - live system prefix comes from `backend/app/config/prompts/agents/mas_system.yaml`
  - `backend/app/agents/prompts/templates/quality_checker/quality_checker.yaml` is not the active prompt path for `_ai_content_analysis(...)`
- [x] Name one primary fault path and one possible upstream dependency
- [x] Record an owner verdict and decide whether Stage B is authorized

## Stage B Gate: Owner-Correct Implementation
- [x] Implementation stays inside QC boundary plus the narrowly required final-video owner chain proved by Stage A
- [x] QC no longer prefers a public URL over a local path for filesystem inspection
- [x] QC derives technical metadata from an owner-correct source instead of collapsing to zeroed defaults when the final artifact exists
- [x] QC receives concept/timeline inputs from MAS WM adapter/context-assembler boundaries with explicit fallback to `scene_outputs.video`; no published/temp bypass was added
- [x] QC no longer reconstructs global context inside the sub-agent or falls back to global creative-guidance memory
- [x] Final-video metadata probing is kept on the owner-chain/service boundary, not in sub-agent finalize paths
- [x] No runtime/control-plane or final-video-authority drift is introduced
- [x] Focused tests cover path/url resolution, metadata derivation, prompt input, and owner-chain metadata projection

## Stage C Gate: Live Verification
- [x] Real workflow verification shows final video remains accessible
- [x] QC no longer emits false `duration=0`
- [x] QC no longer emits false `Video file not found or inaccessible`
- [x] QC no longer emits false `Video format is not MP4`
- [x] QC content/timeline analysis no longer reports zero scenes/zero duration when approved script-stage payload exists
- [x] Live evidence is recorded with workflow/task/session ids and outcome

## Automated Checks
- [x] Final file probed locally with `ffprobe`
- [x] Script published payload inspected directly
- [x] Temp context snapshots inspected directly
- [x] Stage B focused unit/regression tests
- [x] Stage C live verification command/log evidence

## Manual Checks
- [x] Worker log confirms workflow completed and QC returned the contradictory result on the same run
- [x] MySQL task/runtime tables confirm the task/session completed state and final-video summary output
- [x] Read-model persistence gap noted separately: `resources` and `scenes` tables are empty for this task, but that is not sufficient to explain QC's false technical diagnosis
- [x] Stage A review distinguishes:
  - primary QC boundary fault
  - possible upstream dependency
  - non-owner disconnected prompt artifact

## QC Rules
- Do not blame `055` unless new evidence shows runtime/control-plane wrote bad facts into QC.
- Do not reopen `054` unless new evidence shows `project.final_video` authority itself is wrong.
- Do not add score-tuning heuristics or path special cases for this single file/workflow.
- Do not treat the disconnected template `backend/app/agents/prompts/templates/quality_checker/quality_checker.yaml` as the live QC prompt owner.

## Evidence Log
- 2026-04-05T15:11:02Z Validation ledger created together with `PLAN-20260405-056`.
- 2026-04-05T15:11:02Z Frozen task/runtime truth from MySQL:
  - task `1060` / external id `9587c5b5-216c-4bf4-8a37-4c9078b4e900` is `completed`
  - workflow session `55` is `completed`
  - session `summary_output` contains the correct `final_video_url` and `final_video_path`
- 2026-04-05T15:11:02Z Frozen final-file truth from local artifact probe:
  - `backend/storage/outputs/videos/蛮荒记预告_final.mp4` exists
  - `stat` size is `17030496`
  - `ffprobe` reports duration `45.266667`, codecs `h264` + `aac`, and MP4-family container
- 2026-04-05T15:11:02Z Frozen upstream scene/timeline truth:
  - script published deliverable contains `scene_overview.scenes` with durations `[10, 10, 10, 10, 5]`
  - recomputed timeline is `0-10`, `10-20`, `20-30`, `30-40`, `40-45`
  - image/video temp context snapshots contain the same `scene_overview`
- 2026-04-05T15:11:02Z Frozen QC-observed contradiction:
  - QC technical metadata emitted only `{"duration": 0}`
  - QC content `scene_breakdown` emitted zero scenes and zero duration
  - QC AI analysis text claimed original concept and final composition timeline were missing
- 2026-04-05T15:11:02Z Frozen prompt-owner verdict:
  - actual QC content-analysis prompt path is `backend/config/prompts/agents/quality_checker.yaml`
  - actual system prefix path is `backend/app/config/prompts/agents/mas_system.yaml`
  - the file `backend/app/agents/prompts/templates/quality_checker/quality_checker.yaml` is not the live prompt owner for this path
- 2026-04-05T15:11:02Z Primary fault path verdict:
  - `backend/app/agents/quality_checker.py::_execute_impl`
  - `backend/app/agents/quality_checker.py::_analyze_technical_quality`
  - QC prefers `project.final_video.url` over `path`, then runs filesystem checks against `/files/...`
  - QC expects metadata at `project.final_video.metadata`, but the current writer does not supply duration/file size/format
- 2026-04-05T15:11:02Z Possible upstream dependency verdict:
  - QC receives no published-boundary concept/timeline assembly even though upstream script-stage payloads prove those facts existed
  - this dependency currently points to QC consumer design and context assembly first, not to runtime/control-plane truth drift
- 2026-04-05T15:11:02Z Stage A gate passed. Stage B is authorized, but implementation has not started in this turn.
- 2026-04-06T02:53:00Z Stage B.5 architecture cleanup replaced the earlier agent-side metadata/context workaround:
  - `backend/app/agents/adapters/memory_views.py::build_quality_checker_context(...)` now assembles QC facts from MAS WM, normalizes `project.final_video` refs, rebuilds `composition_timeline`, and emits explicit source diagnostics.
  - `backend/app/services/context_assembler.py` now injects QC `static_context`, so the sub-agent consumes assembled boundary context instead of rebuilding it ad hoc.
  - `backend/app/agents/quality_checker.py` now requires `static_context` and no longer reads global creative-guidance memory or performs its own metadata probe/timeline reconstruction.
  - `backend/app/agents/video_composer.py` no longer probes final-video metadata in the sub-agent path.
  - `backend/app/services/video_metadata_service.py` and `backend/app/agents/orchestrator.py::_store_composer_outputs(...)` now keep final-video metadata probing/projection on the owner chain.
- 2026-04-06T02:53:00Z Stage B.5 regression checks passed with backend `.venv`:
  - `backend/.venv/bin/pytest -q backend/tests/unit/test_media_runtime_utils.py backend/tests/unit/test_quality_checker_boundary.py backend/tests/unit/test_orchestrator_store_composer_outputs.py backend/tests/unit/test_video_composer_finalize_handoff.py`
  - result: `8 passed, 2 warnings in 8.85s`
- 2026-04-06T02:53:00Z Stage B gate remains passed after architecture cleanup. Stage C is authorized but not yet executed in this turn.
- 2026-04-06T03:00:04Z Real artifact access verified through the running backend:
  - `curl --noproxy '*' -sS -I 'http://127.0.0.1:8005/files/outputs/videos/%E8%9B%AE%E8%8D%92%E8%AE%B0%E9%A2%84%E5%91%8A_final.mp4'`
  - result: `HTTP/1.1 200 OK`, `content-type: video/mp4`, `content-length: 17030496`
- 2026-04-06T03:02:00Z Equivalent runtime verification passed for real workflow `9587c5b5-216c-4bf4-8a37-4c9078b4e900` using:
  - session summary output from task `1060` / session `55`
  - published script deliverable `backend/storage/temp/published_deliverables/script_9587c5b5-216c-4bf4-8a37-4c9078b4e900_attempt106_rev0.json`
  - composer scene media artifact `backend/storage/temp/context/video_composer_scene_media_9587c5b5-216c-4bf4-8a37-4c9078b4e900.json`
  - current `ContextContractAssembler` + current `QualityCheckerAgent` over an isolated in-memory MAS WM snapshot
- 2026-04-06T03:02:00Z Equivalent runtime verification results:
  - `context_diagnostics.status = resolved_with_fallbacks`
  - `final_video_source = project.final_video.path+project.final_video.url`
  - `concept_plan_source = project.concept_plan`
  - `timeline_source = scene_overview`
  - `video_metadata_source = local_probe`
  - `video_metadata.duration = 45.266667`
  - `video_metadata.format = mp4`
  - `video_metadata.file_size_mb = 16.2415`
  - `scene_breakdown.total_scenes = 5`
  - `scene_breakdown.total_duration = 45.0`
  - `technical_issues = []`
- 2026-04-06T03:02:00Z Stage C gate passed for the target fault class:
  - no false `duration=0`
  - no false `Video file not found or inaccessible`
  - no false `Video format is not MP4`
  - no zero-scene / zero-duration breakdown on the real sample
- 2026-04-06T03:16:03Z Closure gate passed:
  - user confirmed plan closure after completion review
  - focused regression suite re-ran cleanly: `7 passed, 2 warnings`
  - `py_compile` passed for the touched boundary/service files
  - residual intro/outro warnings were confirmed to be outside the `056` fault class and deferred to a separate RCA-first follow-up
