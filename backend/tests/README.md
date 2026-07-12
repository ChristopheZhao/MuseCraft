# Backend tests

Backend tests use the dependency graph locked by `backend/uv.lock`. Do not install a second hand-maintained requirements set for test execution.

## Setup

```bash
uv sync --project backend --frozen --extra test
```

Set an isolated PostgreSQL/Redis configuration when running integration tests. Never point destructive migration or reset tests at a shared database.

## Release contracts

```bash
uv run --project backend pytest -q \
  backend/tests/unit/test_env_loading.py \
  backend/tests/unit/test_release_migration_contract.py
```

These tests verify environment precedence, the generated requirements export, the committed lockfile, and the release Alembic graph.

## MAS boundary regression

The exact focused command is maintained in `.github/workflows/integration-tests.yml`. It covers fail-closed orchestration decisions, explicit agent reports, scene-output acceptance, typed payload/checkpoint boundaries, continuation gates, and runtime read models.

## Broader suites

`backend/tests/unit/` contains focused unit and contract tests. Files directly under `backend/tests/` include older integration/meta suites and are not all release gates. A passing release workflow must not be interpreted as a claim that every legacy suite is current.

See [`docs/testing.md`](../../docs/testing.md) for the repository-wide gate policy and known non-gating debt.
