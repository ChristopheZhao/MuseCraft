# Checkpoint: Gate A4 runtime contract correction

- Plan: `PLAN-20260718-068`
- Gate: A4
- Status: superseded
- Recorded at: 2026-07-25T17:44:35+08:00
- Superseded by: `CHK-gate-a5-thin-contract-boundaries.md` on 2026-07-26. The
  test evidence below remains historical, but A4's thick-validator acceptance wording
  is not a current gate verdict.

## Accepted Boundary

- Agent output is recorded and a runtime attempt can become successful only after the
  explicit orchestration report has been normalized as canonical success.
- Failed, partial, contradictory, missing, or malformed reports fail closed with a
  bounded typed reason that remains visible in runtime diagnostics.
- A returned `standby_agents` collection is authoritative by field presence; an empty
  collection cannot resurrect a consumed standby Agent.
- The scene-output read model uses producer-issued authoritative acceptance. Observation
  receipts cannot override a rejection or supply success when the authoritative set is
  empty.
- Scene acceptance requires exact canonical success/storage values and a parseable,
  timezone-bearing acceptance timestamp.
- Continuation specs carry a canonical `AgentType`; task-spec identity must match its
  owner key.
- A3.4 project compare-and-delete remains unchanged and accepted.

## Negative Cases Proved

- `success=false` plus report `status=completed` is rejected as
  `orchestration_result_report_conflict`.
- Report `status=partial` is rejected as `orchestration_report_not_successful`.
- Contradictory output is not inserted into `workflow_results` or `workflow_data`.
- `standby_agents=[]` produces no remaining standby Agent.
- Authoritative reject plus observation accepted remains incomplete.
- Missing or empty authoritative scene-output data does not fall back to observation
  acceptance.
- Whitespace/case variants of accepted/producer/storage status and invalid or
  timezone-free `accepted_at` values are rejected.
- Unknown continuation Agent identities and task-key/spec-agent mismatches fail with
  distinct typed reasons.

## Evidence

- A3/A4 focused suite: `187 passed, 2 warnings`.
- PLAN-066/MAS selector: `136 passed, 18 deselected, 2 warnings`.
- Exact backend-boundaries CI file set: `62 passed, 2 warnings`.
- Full unit regression: initial run exposed two A4-related ReAct reason-code regressions
  plus the two known Windows Conda OSS import failures. The reason-code regression was
  fixed at the local orchestration error boundary. Final feasible run:
  `594 passed, 2 deselected, 2 warnings`.
- The two deselected tests are the previously recorded Windows Conda
  `pyOpenSSL`/OpenSSL incompatibility reached through `oss2`:
  `test_default_tool_registration_exposes_core_capabilities` and
  `test_draft_narration_generates_natural_text`.
- Scoped Black and isort checks passed for A4-touched files.
- Python compilation, plan-index JSON, scene-output/workflow YAML, and
  `git diff --check` passed.

## Tooling Note

The optional `checkpoint-gatekeeper` CLI was not used to emit a machine gate JSON
because its runner is hard-coded to `/bin/bash`, while this host has no WSL
distribution or Git Bash. No scripted pass was fabricated; this checkpoint records
the commands run directly in the repository's available Windows Conda environment.

## Remaining Gate

- The worktree remains intentionally uncommitted.
- Commit, push, and hosted `release-contracts`, `mas-runtime`, `backend-boundaries`, and
  `postgres-runtime-contracts` evidence remain pending explicit authorization.
- PLAN-068 therefore remains `in_progress`.
