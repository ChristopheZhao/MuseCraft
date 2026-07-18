# MuseCraft Backend

FastAPI backend for the MuseCraft multi-agent short-video runtime.

## Runtime requirements

- Python 3.11
- uv
- PostgreSQL 15+
- Redis 7+
- FFmpeg/ffprobe

Configuration is loaded from the repository-root `.env`. Explicit process or container environment variables take precedence over `.env` values.

## Install and run with uv

From the repository root:

```bash
uv sync --project backend --frozen
uv run --project backend --frozen python backend/scripts/start_dev_uv.py
```

`--project backend` makes `backend/pyproject.toml` the project entry point and uses `backend/.venv` as the canonical virtual environment. A repository-root `.venv` is not part of the backend runtime contract.

PostgreSQL, Redis, and FFmpeg are external system dependencies and must already be available through the root `.env` configuration. The public runtime supports PostgreSQL only; pre-release MySQL databases require the reviewed reconciliation process in [database-migrations.md](../docs/database-migrations.md). The launcher validates the database contract and Redis, applies Alembic migrations, then starts the API, Celery worker, and Celery beat from the active uv environment. It exits non-zero and cleans up already-started processes when a required service cannot start.

Use `--check` to validate dependencies and migrations without starting long-lived processes:

```bash
uv run --project backend --frozen python backend/scripts/start_dev_uv.py --check
```

The API listens on `http://localhost:8000` by default. OpenAPI is available at `/docs`. For API-only development, run:

```bash
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

API-only mode does not execute queued generation work. The complete local runtime requires the launcher or equivalent separately managed Celery worker and beat processes. Docker Compose remains an optional all-in-one path; it is not required to run the Python application.

## Dependency contract

- Source of truth: `pyproject.toml` and the committed `uv.lock`.
- Compatibility export: `requirements.txt`, generated with:

```bash
uv export --project backend --frozen --format requirements-txt \
  --no-hashes --no-emit-project --output-file backend/requirements.txt
```

Do not edit `requirements.txt` by hand.

## Schema contract

Tracked release revisions are under `alembic/release_versions/`. Apply and verify them with:

```bash
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini check
```

See [database-migrations.md](../docs/database-migrations.md) before adopting an existing pre-release database.

## Tests

```bash
uv run --project backend pytest -q \
  backend/tests/unit/test_env_loading.py \
  backend/tests/unit/test_release_migration_contract.py
```

The CI workflow also runs the focused MAS runtime boundary suite. See [testing.md](../docs/testing.md) for scope and known legacy suites.
