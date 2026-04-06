# Validation Ledger: PLAN-20260406-057

## Scope
- Validate the bounded semantic follow-on for QC intro/outro false positives.
- Keep the owner on QC heuristic behavior unless new evidence proves the fix must move upstream.
- Preserve all `056` closure boundaries and technical-fact repairs.

## Review / Boundary Gate
- [x] Review confirms `057` is a new semantic follow-on and not a reopened `056`
- [x] Review confirms `054` / `055` remain reference-only and out of scope
- [x] Review confirms root cause must stay owner-correct and not start with upstream hardcoding
- [x] Review confirms live QC must continue consuming MAS WM / assembler context only

## Stage A Gate: RCA / Owner Freeze
- [x] Freeze real sample:
  - workflow/task `9587c5b5-216c-4bf4-8a37-4c9078b4e900`
  - script published deliverable and composer scene-media artifacts inspected directly
- [x] Freeze `scene_type` absence:
  - `concept_plan.scenes[*].scene_type` absent in the real sample
  - `scene_overview.scenes[*].scene_type` absent in the real sample
  - `composition_timeline[*].scene_type` absent after QC context assembly
- [x] Freeze current QC trigger path:
  - unlabeled timeline entries are defaulted to `main_content`
  - `Missing introduction scene` fires when `"intro"` is absent from the derived list
  - `Missing conclusion scene` fires when `"outro"` is absent and `len(composition_timeline) > 2`
- [x] Freeze owner verdict:
  - primary owner is QC heuristic
  - upstream `scene_type` contract instability is a possible dependency only

## Stage B Gate: Owner-Correct Implementation
- [x] Implementation remains inside QC semantic handling by default
- [x] Unlabeled timelines do not produce false intro/outro issues
- [x] Labeled timelines still enforce intro/outro checks correctly
- [x] Missing labels remain explicit diagnostics, not silent semantic pass/fail coercion
- [x] No runtime/control-plane or published-deliverable ownership drift is introduced

## Stage C Gate: Verification
- [x] Targeted QC boundary tests pass
- [x] Real-sample equivalent verification passes under current assembler/QC path
- [x] No regression is observed in the existing `056` QC boundary test coverage
- [x] Fresh live API run reaches script HITL, resumes, and completes with current QC behavior verified

## Automated Checks
- [x] Characterization tests added for real-sample label absence and QC false-positive trigger
- [x] Focused QC boundary pytest rerun after implementation
- [x] Additional real-sample equivalent verification after implementation
- [x] Fresh quick-mode live run through `8005` API with script-gate approval and worker-result inspection

## QC Rules
- Do not reclassify unlabeled scene evidence as proof of missing intro/outro semantics.
- Do not patch the issue by reading published/temp artifacts directly from QC live code.
- Do not reopen `056` or widen into runtime/control-plane or final-video authority work.
- Do not force case-specific inference rules based on this one trailer structure.

## Evidence Log
- 2026-04-06T03:48:00Z Validation ledger created together with `PLAN-20260406-057`.
- 2026-04-06T03:48:00Z Stage A characterization evidence frozen in `backend/tests/unit/test_quality_checker_boundary.py`:
  - real sample context build proves no `scene_type` labels are present in `concept_plan`, `scene_overview`, or `composition_timeline`
  - direct QC content-analysis characterization proves unlabeled timelines still emit `Missing introduction scene` and `Missing conclusion scene`, while equivalent labeled timelines do not
- 2026-04-06T03:52:41Z Stage B owner-correct repair completed in `backend/app/agents/quality_checker.py`:
  - scene-type evidence is now classified as `complete` / `partial` / `missing`
  - intro/outro heuristics only apply when evidence is `complete`
  - scene breakdown now reports explicit label coverage instead of coercing unlabeled scenes into `main_content`
- 2026-04-06T03:52:41Z Stage C focused verification passed:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 30s backend/.venv/bin/pytest -q backend/tests/unit/test_quality_checker_boundary.py`
  - result: `5 passed, 1 skipped`
  - focused coverage includes:
    - real sample label absence freeze
    - unlabeled timeline no-false-positive behavior
    - partial-label timeline no-false-positive behavior
    - complete-label timeline still enforcing intro/outro checks
    - real-sample equivalent QC content-analysis verification under current boundary assembly
- 2026-04-06T04:07:01Z First fresh live API attempt (`task_id=19f14ff2-f3c4-4b1d-ae66-ba5f8a449f0c`, db id `1061`) failed before script HITL:
  - runtime/task failed with `unable to open database file`
  - root cause traced to worker-side `SQLiteMemoryStore` initialization in `backend/app/agents/memory/long_term/stores/sqlite_store.py`
  - this was frozen as an environment/runtime validation blocker, not a `057` QC semantic regression
- 2026-04-06T04:11:39Z Fresh live API verification passed after restarting the local `uv` celery worker for validation with `MEMORY_SQLITE_PATH=/tmp/qc_live_memory.sqlite`:
  - quick task created via `POST /api/v1/tasks/`: `task_id=d9427491-5bb4-4275-b455-5fd75774299d` (db id `1062`)
  - script HITL opened at runtime session `57`, gate `33`, and was approved through `POST /api/v1/tasks/d9427491-5bb4-4275-b455-5fd75774299d/runtime/script/decision`
  - workflow completed successfully at `2026-04-06T12:20:08` local time with `quality_score=85`
  - worker result inspection (`backend/logs/mas/mas_workflow.log`, lines around `32676-32679`) confirms:
    - `quality_checker.content_quality.issues == []`
    - `quality_checker.content_quality.scene_breakdown.scene_type_label_status == "missing"`
    - `quality_checker.content_quality.scene_type_diagnostics.intro_outro_check_applied == False`
    - no `Missing introduction scene` / `Missing conclusion scene` false positives remain
    - recommendation downgraded to explicit evidence guidance only: `Provide explicit scene_type labels if intro/outro structure needs automated verification`
