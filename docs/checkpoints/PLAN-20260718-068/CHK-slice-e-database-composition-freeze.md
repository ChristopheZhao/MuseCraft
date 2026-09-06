# Slice E Database Composition Freeze

- Timestamp: `2026-07-19T05:37:49+08:00`
- Status: pass; implementation has not started
- Scope: profile, adapter, preflight, migration, and ownership contract

## Expected Outcomes Checked

- [x] `local`, `production`, and `test` profiles have explicit, non-overlapping contracts.
- [x] PostgreSQL is the only public adapter; SQLite is test-only and MySQL remains unsupported.
- [x] Production requires an explicit URL and must fail closed on localhost or example credentials.
- [x] One infrastructure composition owner is assigned URL/driver adaptation, engines, session factories, migration capability, and typed preflight.
- [x] uv, Alembic, API/worker, and maintenance entrypoints are consumers rather than database-policy owners.
- [x] Diagnostics must expose typed reason codes without leaking credentials or full URLs.
- [x] An executable ratchet records exactly five current policy owners and protects Agent/control-plane/queue negative boundaries.

## Evidence

- Architecture freeze suite: `12 passed, 2 warnings`.
- Black and isort: pass for the new architecture guard.
- `git diff --check`: pass.
- Warnings are the existing SQLAlchemy `as_declarative` and Pydantic class-config deprecations.

## Expectation Check

The freeze matches the intended Slice E boundary. It distinguishes deployment configuration from application ownership and does not equate SQLite test smoke or a successful connection with public provider support. No implementation or release-support claim is made at this checkpoint.

## Transitional Debt

Provider/profile/driver policy remains duplicated in exactly `app/core/config.py`, `app/core/database.py`, `alembic/env.py`, `scripts/start_dev.py`, and `scripts/start_dev_uv.py`. Gate E cannot close until the exact ratchet reaches zero and all active entrypoints consume the typed composition owner.
