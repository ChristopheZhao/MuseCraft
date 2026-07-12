# MuseCraft Backend

FastAPI backend for the MuseCraft multi-agent short-video runtime.

## Runtime requirements

- Python 3.11
- uv
- PostgreSQL 15+
- Redis 7+
- FFmpeg/ffprobe

Configuration is loaded from the repository-root `.env`. Explicit process or container environment variables take precedence over `.env` values.

## Install and run

From the repository root:

```bash
uv sync --project backend --frozen --extra dev --extra test
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

The API listens on `http://localhost:8000` by default. OpenAPI is available at `/docs`.

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
