# Contributing

## Before opening a change

1. Search existing issues and pull requests.
2. Keep changes scoped to one behavior or contract.
3. Do not add provider calls directly to agents; expose them through registered tools.
4. Keep MAS runtime ownership in the control plane and queue ownership in transport.
5. Add contract-boundary diagnostics instead of silent fallbacks.

## Development setup

Follow [README.md](README.md) and [ENV_SETUP.md](ENV_SETUP.md). Use Python 3.11 and the committed uv lock.

## Validation

Run the checks relevant to your change:

```bash
npm run lint
npm run type-check
npm test
npm run build

uv run --project backend pytest -q \
  backend/tests/unit/test_env_loading.py \
  backend/tests/unit/test_release_migration_contract.py
```

For MAS changes, also run the focused files listed in `.github/workflows/integration-tests.yml`.

## Pull requests

- Explain the problem, root cause and chosen boundary.
- List user-visible or contract changes.
- Include exact test evidence and known limitations.
- Never commit `.env`, provider payloads, generated user media or business documents.
- Use migrations for schema changes; do not call `metadata.create_all()` as a deployment path.
