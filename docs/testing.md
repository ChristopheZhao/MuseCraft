# Testing strategy

## Release gates

Frontend pull requests run:

```bash
npm run lint
npm run type-check
npm test
npm run build
```

`npm test` contains the maintained unit tests and the runtime-authority/store integration contracts. It is intentionally bounded and completes without external providers.

Backend pull requests run four groups:

- dependency export, environment precedence and migration round-trip contracts;
- the current Quick application/MAS E2E plus the focused control-plane/native-agent boundary suite;
- backend-bounded Agent, transport, persistence and application-use-case guards;
- PostgreSQL lease, heartbeat, gate, continuation and terminal-transition contracts
  against a migrated service database.

The maintained Quick E2E derives its seams from production composition: public API,
queue application use case, execution host, Orchestrator/control plane, real specialist
Agents, script gate continuation, scene-output/finalize receipts, and runtime read model
stay real. Celery delivery and deterministic LLM/tool/provider collaborators are
replaced at their existing ports; live media providers remain separate integration
concerns.

The PostgreSQL transaction suite is explicit and does not fall back to SQLite:

```bash
POSTGRES_RUNTIME_TEST_URL=postgresql://user:password@127.0.0.1:5432/migrated_test_db \
  uv run --project backend --frozen pytest -q \
  backend/tests/integration/test_runtime_store_postgresql_transactions.py
```

Without `POSTGRES_RUNTIME_TEST_URL`, that suite reports a skip instead of making a
PostgreSQL transaction claim. Use a dedicated migrated test database; do not point
the command at a production database.

## Extended legacy suites

The repository still contains older broad frontend integration, performance and accessibility suites plus older backend tests. They are not release gates because the current baseline includes stale UI assumptions, long waits, platform-only process APIs and superseded architecture contracts.

They remain available for targeted rework:

```bash
npm run test:legacy:integration
npm run test:performance
npm run test:a11y
uv run --project backend pytest -q backend/tests/unit
```

Do not interpret a non-gating suite as passing. Promote a suite into CI only after its assertions match current contracts, it has bounded runtime, and it is green on Ubuntu CI.
