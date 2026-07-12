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

Backend pull requests run two groups:

- dependency export, environment precedence and migration round-trip contracts;
- the focused MAS control-plane/native-agent boundary suite established by PLAN-066.

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
