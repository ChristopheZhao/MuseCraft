# Release migrations

This directory is the versioned schema source of truth for public releases.

The earlier local-only migration snapshots under `alembic/versions/` were never
committed and contain MySQL-specific DDL. They are intentionally excluded from
the release chain. The first tracked revision is a baseline for clean
PostgreSQL installations.

Existing databases must be backed up and compared with the current SQLAlchemy
metadata before an operator runs `alembic stamp` for the release baseline.
Stamping does not create or validate schema objects.
