# Checkpoint: Gate F PostgreSQL runtime transaction evidence

- Plan: `PLAN-20260718-068`
- Gate: F
- Status: local_pass_hosted_ci_pending
- Recorded at: 2026-07-24T00:44:09+08:00

## Accepted Boundary

- The evidence exercises existing MAS runtime store and control-plane contracts
  against PostgreSQL. It adds no database behavior to Agents, queue transport, or
  control-plane decision logic.
- `POSTGRES_RUNTIME_TEST_URL` explicitly selects a dedicated, migrated PostgreSQL
  database. Without it, the integration suite skips and makes no PostgreSQL
  transaction claim.
- Tests use fresh SQLAlchemy sessions and the production row-locking adapter. They do
  not call `Base.metadata.create_all`, do not fall back to SQLite, and clean their
  task/runtime rows after each scenario.
- CI separates fast backend-bounded architecture/use-case tests from PostgreSQL
  transaction evidence. PostgreSQL migration success alone is not accepted as
  runtime transaction proof.

## Expectation Checks

- Concurrent lease acquisition produces exactly one committed lease and one typed
  `lease_conflict`.
- Wrong-token and stale heartbeats fail closed; a newer heartbeat is visible through
  a fresh session.
- A script-gate decision whose task precondition fails is fully rolled back. The
  successful decision and continuation checkpoint are visible through fresh
  sessions, and a duplicate decision cannot create a second row.
- Completed and failed runtime sessions project consistent Task, session, node, and
  attempt terminal states through fresh sessions; failure clears the live lease.
- PLAN-050 no longer names the deleted `RuntimeSessionService` or legacy MySQL
  transaction behavior as current release authority.
- The uv process stack starts API, Celery worker, and Celery beat through the canonical
  backend environment, returns HTTP 200 from `/health`, and performs scoped shutdown
  with no managed process residuals.

No production runtime defect was exposed by these tests, so no runtime store,
control-plane, Agent, queue, or database-composition implementation was changed.

## Evidence

- PostgreSQL transaction suite: `4 passed, 2 warnings`.
- Missing `POSTGRES_RUNTIME_TEST_URL` behavior: `4 skipped, 2 warnings`.
- Dedicated database revision: `20260719_0002`; residual `gate-f-*` Task rows: `0`.
- Full backend unit suite: `553 passed, 2 warnings`.
- Full backend architecture suite: `31 passed, 2 warnings`.
- PLAN-066 focused selector: `118 passed, 18 deselected, 2 warnings`.
- Exact backend-boundaries CI file set: `62 passed, 2 warnings`.
- Final uv smoke: PostgreSQL and Redis preflight passed, migrations completed,
  API/worker/beat started, `/health` returned 200, and shutdown reported no
  repo-local managed residuals. A separate process query also returned no matching
  uvicorn or Celery process.
- GitHub Actions YAML parsed successfully with required jobs
  `release-contracts`, `mas-runtime`, `backend-boundaries`, and
  `postgres-runtime-contracts`.
- Scoped Black and `git diff --check` passed.

The two test warnings are existing SQLAlchemy and Pydantic deprecations. The uv smoke
also surfaced existing optional-provider tool-registration warnings for Jimeng,
MiniMax, and the video composer. Gate F does not claim an end-to-end provider
generation pass; those warnings remain visible and require separately scoped
tool-registry follow-up before such a claim.

## Remaining Gate

Hosted GitHub Actions results do not exist until the current worktree is committed and
pushed. Gate F is locally green but remains open for hosted CI. PLAN-068 therefore
stays `in_progress`; remote publication must not claim final closure before all four
backend jobs pass.
