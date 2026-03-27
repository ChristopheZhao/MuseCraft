# PLAN-20260327-029 Validation

- Plan ID: PLAN-20260327-029
- Recorded At: 2026-03-27T07:24:27Z
- Status: awaiting_user_confirmation

## Purpose
- Record phase-by-phase verification for [PLAN-20260327-029](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-029.md).
- Keep this MAS-mainline schema-alignment fix separate from the already closed project-level unblocker in [PLAN-20260327-028.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-028.md).

## Validation Matrix
### Phase 0
- Status: completed
- Planned checks:
  - confirm the runtime failure path reads `WorkflowGate` through ORM entity selection
  - confirm ORM-vs-migration drift for `workflow_gates`
  - confirm scope freeze excludes query-side compatibility workarounds
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`
- Evidence:
  - Runtime failure chain lands in [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) `get_latest_gate_for_node_sync()` and selects the full `WorkflowGate` entity
  - [workflow_runtime.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/models/workflow_runtime.py) declares `scope` and `diagnostics` on `WorkflowGate`
  - [8b1f0c2d4e5f_add_workflow_runtime_tables.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/alembic/versions/8b1f0c2d4e5f_add_workflow_runtime_tables.py) creates `workflow_gates` without `scope` or `diagnostics`
  - repo grep found no later Alembic `add_column` migration for those fields
- Results:
  - `rg -n "workflow_gates|scope|diagnostics" backend/app backend/alembic -g '*.py'`
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`

### Phase 1
- Status: completed
- Planned checks:
  - migration adds all missing `WorkflowGate` schema columns required by the current ORM contract
  - migration includes minimal backfill for existing rows
  - no query-side compatibility logic introduced
- Evidence:
  - Added [5d2e7a9c4f1b_add_missing_workflow_gate_projection_columns.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/alembic/versions/5d2e7a9c4f1b_add_missing_workflow_gate_projection_columns.py), chained after [3a7d9f1b2c4e_add_project_workspaces_table.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/alembic/versions/3a7d9f1b2c4e_add_project_workspaces_table.py)
  - Migration adds both `scope` and `diagnostics` to `workflow_gates`, matching the current [WorkflowGate](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/models/workflow_runtime.py) ORM fields
  - Migration performs minimal backfill to `{}` / `[]` for historical rows and does not modify runtime query code
- Results:
  - `python3 -m py_compile backend/alembic/versions/5d2e7a9c4f1b_add_missing_workflow_gate_projection_columns.py`
  - focused source review: no runtime query/service files changed in Phase 1; the implementation diff is isolated to the Alembic migration plus governance assets

### Phase 2
- Status: completed
- Planned checks:
  - focused backend validation for migration and runtime gate read path
  - governance asset sync review
  - user confirmation gate before lifecycle closeout
- Evidence:
  - Applied `5d2e7a9c4f1b` to the local MySQL dev database with `alembic upgrade head`
  - `SHOW COLUMNS FROM workflow_gates` now includes both `scope` and `diagnostics`
  - direct ORM `WorkflowGate` read succeeds and returns normalized projection values
  - direct `RuntimeSessionService.get_latest_gate_for_node_sync(db, 14, "script")` succeeds on the previously failing runtime read path
- Results:
  - `cd backend && .venv/bin/alembic current`
  - `cd backend && .venv/bin/alembic upgrade head`
  - `cd backend && .venv/bin/python -c "import pymysql; ... SHOW COLUMNS FROM workflow_gates ..."`
  - `cd backend && .venv/bin/python -c "from app.core.database import SessionLocal; from app.models.workflow_runtime import WorkflowGate; ..."`
  - `cd backend && .venv/bin/python -c "from app.core.database import SessionLocal; from app.services.runtime_session_service import RuntimeSessionService; ... get_latest_gate_for_node_sync(...)"` 
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`

## Notes
- 2026-03-27T07:24:27Z completed Phase 0 audit: root cause is confirmed as `workflow_gates` schema drift (`scope` and `diagnostics` absent from the Alembic table definition while present in the ORM model), so the next phase is a pure schema-alignment migration without runtime query compatibility changes.
- 2026-03-27T07:24:27Z completed Phase 1 implementation: the new migration aligns `workflow_gates` with the current ORM contract by adding `scope` and `diagnostics` plus minimal backfill, while intentionally leaving runtime query code untouched so the fix remains schema-first and auditable.
- 2026-03-27T07:45:54Z completed Phase 2 validation: the local MySQL dev database is now at Alembic head `5d2e7a9c4f1b`, the physical `workflow_gates` table includes `scope` and `diagnostics`, and the previously failing runtime gate read path succeeds without any query-side compatibility changes; lifecycle remains at `awaiting_user_confirmation` until explicit user acceptance.
