# Checklist: Gate B - Agent persistence isolation
- Linked Plan: `PLAN-20260718-068`
- Checkpoint: `CHK-gate-b-agent-pure`
- Profile: `default`
- Auto Fix Enabled: `false`
- Max Auto Fix Rounds: `1`

<!-- checkpoint-gatekeeper:spec
{
  "plan_id": "PLAN-20260718-068",
  "checkpoint": "CHK-gate-b-agent-pure",
  "title": "Gate B - Agent persistence isolation",
  "profile": "default",
  "allow_auto_fix": false,
  "max_auto_fix_rounds": 1,
  "validation_commands": [
    "git -c safe.directory=/mnt/d/code/agent/Opensource/vertical_application/short-video-maker diff --check",
    "UV_CACHE_DIR=/tmp/musecraft-uv-cache UV_PROJECT_ENVIRONMENT=/tmp/musecraft-plan068-test-venv uv run --project backend --extra test --frozen pytest -q backend/tests/architecture/test_agent_persistence_boundary.py backend/tests/unit/test_agent_execution_application_boundary.py --tb=short"
  ],
  "auto_fix_commands": [],
  "user_confirmation_triggers": [
    "MANUAL_REVIEW_REQUIRED",
    "NEEDS_USER_CONFIRMATION",
    "SCOPE_CHANGE_REQUIRED"
  ]
}
-->

## Validation Commands
- `git -c safe.directory=/mnt/d/code/agent/Opensource/vertical_application/short-video-maker diff --check`
- `UV_CACHE_DIR=/tmp/musecraft-uv-cache UV_PROJECT_ENVIRONMENT=/tmp/musecraft-plan068-test-venv uv run --project backend --extra test --frozen pytest -q backend/tests/architecture/test_agent_persistence_boundary.py backend/tests/unit/test_agent_execution_application_boundary.py --tb=short`

## Auto-Fix Commands
- _No auto-fix commands configured_

## User Confirmation Triggers
- `MANUAL_REVIEW_REQUIRED`
- `NEEDS_USER_CONFIRMATION`
- `SCOPE_CHANGE_REQUIRED`

## Evidence
- Record relevant artifacts, logs, or screenshots here after each checkpoint run.
