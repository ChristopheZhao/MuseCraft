# Checkpoint: Gate E uv and local PostgreSQL profile

- Plan: `PLAN-20260718-068`
- Gate: E
- Status: passed
- Recorded at: 2026-07-23T23:45:40+08:00

## Accepted Boundary

- `backend/pyproject.toml`, `backend/uv.lock`, and `backend/.venv` are the canonical
  uv backend environment contract.
- Docker is optional. This checkpoint used the directly installed WSL PostgreSQL 16
  cluster and Redis service.
- PostgreSQL remains an external infrastructure dependency. The launcher delegates
  database policy and connection preflight to the existing typed composition owner;
  no Agent or MAS control-plane database responsibility was added.
- `--environment-check` verifies only uv and the canonical virtual environment.
  `--check` verifies external dependencies and applies tracked migrations.

## Evidence

- uv `0.7.20`, Python `3.11.13`, and frozen lock resolution passed in
  `backend/.venv`.
- Pure `--environment-check` passed without touching PostgreSQL, Redis, Alembic, or
  managed processes.
- Directly installed PostgreSQL 16 and Redis were reachable; an isolated non-superuser
  local role/database was used without touching the legacy MySQL configuration or any
  existing PostgreSQL database.
- The first fresh migration exposed a bounded `JSON` versus `JSONB` operator mismatch
  in revision `20260719_0002`. The migration now casts PostgreSQL `JSON` through
  `JSONB`, preserves the SQLite contract path with `json_remove`, and fails explicitly
  for unsupported dialects.
- Release migration contract: `5 passed, 2 warnings`.
- Full launcher test file: `17 passed, 2 warnings`.
- Database composition/logging checks: `12 passed, 2 warnings`.
- Agent persistence boundary: `8 passed, 2 warnings`.
- Fresh `uv --check` completed PostgreSQL/Redis preflight and Alembic upgrade to head.
- `alembic check` reported `No new upgrade operations detected`.
- Scoped Black and `git diff --check` passed.

The warnings are the existing SQLAlchemy and Pydantic deprecations.

## Remaining Gate

This checkpoint closes Gate E only. Gate F still requires the already planned
PostgreSQL lease/gate/continuation transaction evidence. It does not authorize a new
SQL abstraction, persistence redesign, or Agent/control-plane database dependency.
