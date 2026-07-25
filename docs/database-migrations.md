# Database migrations

## New installations

The release schema source of truth is `backend/alembic/release_versions/`. It has one
linear PostgreSQL history rooted at baseline `20260711_0001`; the current head is
`20260719_0002`.

```bash
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini check
```

## Existing pre-release databases

Earlier local migration snapshots were never committed and contain MySQL-specific DDL. They are not a trustworthy shared upgrade history.

The shared database composition preflight therefore rejects MySQL with `reason_code=unsupported_database_backend` before any active entrypoint attempts release migrations. This is a database compatibility boundary, not a limitation of uv-based application startup.

Before adopting the release baseline:

1. Back up the database and test restoration.
2. Compare every table, column, index, foreign key and enum with current SQLAlchemy metadata.
3. Reconcile differences through a reviewed migration or data move.
4. Run application regression tests against the reconciled copy.
5. Only then use `alembic stamp 20260719_0002` to record a schema already matching the
   current release head. Stamp the baseline instead only when the schema matches that
   baseline and the forward migrations will be run immediately afterward.

`stamp` changes only Alembic metadata. It does not create, migrate or validate application tables. Never stamp an unverified production database.
