# Checklist: A3/A4 current MAS mainline closure
- Linked Plan: `PLAN-20260808-069`
- Checkpoint: `CHK-a3-a4-mainline-closure`
- Profile: `default`
- Auto Fix Enabled: `false`
- Max Auto Fix Rounds: `1`

<!-- checkpoint-gatekeeper:spec
{
  "plan_id": "PLAN-20260808-069",
  "checkpoint": "CHK-a3-a4-mainline-closure",
  "title": "A3/A4 current MAS mainline closure",
  "profile": "default",
  "allow_auto_fix": false,
  "max_auto_fix_rounds": 1,
  "validation_commands": [
    "backend/.venv/bin/python -m pytest -q backend/tests/e2e/test_quick_mas_runtime.py",
    "backend/.venv/bin/python -m pytest -q backend/tests/unit",
    "backend/.venv/bin/python -m pytest -q backend/tests/architecture",
    "backend/.venv/bin/python -m pytest -q backend/tests/integration/test_video_composer_react_flow.py backend/tests/integration/test_video_composer_voiceover_flow.py",
    "git diff --check"
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
- `backend/.venv/bin/python -m pytest -q backend/tests/e2e/test_quick_mas_runtime.py`
- `backend/.venv/bin/python -m pytest -q backend/tests/unit`
- `backend/.venv/bin/python -m pytest -q backend/tests/architecture`
- `backend/.venv/bin/python -m pytest -q backend/tests/integration/test_video_composer_react_flow.py backend/tests/integration/test_video_composer_voiceover_flow.py`
- `git diff --check`

## Auto-Fix Commands
- _No auto-fix commands configured_

## User Confirmation Triggers
- `MANUAL_REVIEW_REQUIRED`
- `NEEDS_USER_CONFIRMATION`
- `SCOPE_CHANGE_REQUIRED`

## Evidence
- Production trajectory and invalid-test classification: `docs/checkpoints/PLAN-20260808-069/CHK-a3-e2e-trajectory.md`.
- Current Quick mainline: `backend/tests/e2e/test_quick_mas_runtime.py`.
- Exact-status counterexamples: `backend/tests/unit/test_task_queue.py` and `backend/tests/unit/test_episode_orchestrator.py`.
- Finalize/continuation/scene-output counterexamples: `backend/tests/unit/test_video_composer_finalize_handoff.py`, `backend/tests/unit/test_orchestration_state_adapter.py`, `backend/tests/unit/test_video_generator_progress_boundary.py`, and `backend/tests/unit/test_plan_context_progress_read_model.py`.
- Project wrapper/read-model boundary: `backend/tests/unit/test_agent_execution_application_boundary.py` and `backend/tests/architecture/test_project_runtime_authority_boundary.py`.
- Final attempt 2 verdict: `pass` without remediation; exact command outputs and return codes are recorded in `CHK-a3-a4-mainline-closure-gate.json`.
