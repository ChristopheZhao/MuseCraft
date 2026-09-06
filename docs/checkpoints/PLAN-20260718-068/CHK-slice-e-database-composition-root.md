# Slice E Database Composition Root

- Timestamp: `2026-07-19T06:41:22+08:00`
- Status: pass for implementation checkpoint; Gate E remains open
- Scope: typed database composition, profile resolution, entrypoint delegation, provider truthfulness, and diagnostic safety

## Expected Outcomes Checked

- [x] One infrastructure owner resolves profiles, validates registered adapters, constructs sync/async engines and session factories, supplies the migration URL, and performs connection preflight.
- [x] `local` defaults to the documented localhost PostgreSQL URL; `production` requires an explicit non-local PostgreSQL URL and rejects known development credentials; SQLite remains test-only.
- [x] Unsupported MySQL configuration returns `unsupported_database_backend` before any connection probe or Alembic command.
- [x] Core database sessions and Alembic consume the typed composition result instead of parsing or rewriting database URLs.
- [x] The canonical uv launcher renders typed preflight diagnostics and owns process lifecycle only; the two historical launchers delegate to it.
- [x] The system validator consumes resolver/preflight results and no longer creates sessions, executes its own SQL probe, or logs raw database exceptions.
- [x] Docker API, migration, worker, and beat services receive the same explicit profile contract.
- [x] MySQL drivers were removed from project metadata, lockfile, and generated requirements because no MySQL release adapter is registered.
- [x] Active `app/`, `scripts/`, and Alembic entrypoints are AST-scanned for duplicate engine construction and provider policy; the exact transitional policy ratchet is empty.
- [x] The previously recorded `extract_video_last_frame.py` syntax error was corrected so every active Python entrypoint can be parsed by the architecture guard.
- [x] Redis dependency failures in the uv launcher now emit reason/error type only and do not print credential-bearing exception text.

## Evidence

- Focused composition/launcher/migration/logging suite: `45 passed, 2 warnings`.
- Expanded architecture/config/API/queue/runtime-store regression: `131 passed, 2 warnings`.
- Architecture composition guard: `6 passed, 2 warnings`; it parses all active application and script files.
- SQLite release migration round trip and Alembic metadata check pass inside the focused suite.
- `uv lock --check`: pass; a fresh `uv export` matches committed `requirements.txt` after its generated-command header.
- Mypy: composition owner passes with full imports; core facade passes with `--follow-imports=skip`. Full-import core analysis timed out without diagnostics after 124 seconds and is not claimed.
- Black: pass for the new/refactored Slice E files except the pre-existing whole-file formatting debt in `validate_system.py`; isort passes for all related files.
- `git diff --check`: pass.
- Current project `.env` smoke returns `profile=local backend=mysql reason=unsupported_database_backend` and the real uv `--check` exits before migrations with the same sanitized diagnostic.

## Expectation Check

The implementation matches the intended ownership boundary: deployment selects a profile and URL, infrastructure owns adapter and engine policy, and launchers/control-plane/Agents remain consumers. Unsupported-provider and connection failures are explicit typed facts rather than launcher branches or swallowed exceptions. No compatibility layer preserves false MySQL support.

This checkpoint does not close P0-G or Gate E. The documented local default reached a PostgreSQL listener on `127.0.0.1:5432` but failed authentication/database selection with a sanitized `OperationalError`; the existing service does not match the documented local credentials. Docker was not available as an alternative clean PostgreSQL fixture. A successful clean PostgreSQL preflight plus `alembic upgrade head` and uv `--check` is still required.

## Recorded Follow-up

- Run the local-profile smoke against an isolated PostgreSQL instance configured with the documented local URL; do not modify or stamp the existing MySQL database.
- Re-run production-profile negative smoke and then close Gate E only if the local migration/start contract succeeds.
- `test_config_system.py::test_hardcoded_elimination` remains a pre-existing stale test that references `MIN_SCENE_DURATION` and `MAX_SCENE_DURATION`, both explicitly deprecated in `app/core/config.py`; the expanded Slice E suite excludes that unrelated test rather than restoring obsolete settings.
