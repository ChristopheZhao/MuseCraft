# Database migrations

## New installations

The release schema source of truth is `backend/alembic/release_versions/` and currently has one PostgreSQL baseline head.

```bash
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini check
```

## Existing pre-release databases

Earlier local migration snapshots were never committed and contain MySQL-specific DDL. They are not a trustworthy shared upgrade history.

Before adopting the release baseline:

1. Back up the database and test restoration.
2. Compare every table, column, index, foreign key and enum with current SQLAlchemy metadata.
3. Reconcile differences through a reviewed migration or data move.
4. Run application regression tests against the reconciled copy.
5. Only then use `alembic stamp 20260711_0001` to record an already-matching schema.

`stamp` changes only Alembic metadata. It does not create, migrate or validate application tables. Never stamp an unverified production database.
