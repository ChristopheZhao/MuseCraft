# Validation Ledger: PLAN-20260329-037

## Scope
- Validate that generic stale-run resume is owned by control-plane continuation checkpoints rather than guarded re-dispatch.

## Automated Checks
- [x] Backend tests for continuation checkpoint schema/validation
- [x] Backend tests for generic resume consumer and fail-fast rejection
- [x] Backend tests for `resume_control` reason precedence
- [x] Frontend/API contract checks if projection shape changes

## Manual Checks
- [ ] API restart only reattaches `quick/current` view and subscriptions
- [ ] Live transport returns view-only state and no resume CTA
- [ ] Stale run without checkpoint returns `resume_blocked`
- [ ] Stale run with valid checkpoint returns `resume_available`
- [ ] Explicit resume on valid checkpoint produces new runtime progression evidence
- [ ] `waiting_gate` remains gate-owned and rejects generic resume

## Evidence Log
- 2026-03-29T07:14:08Z `backend/.venv/bin/pytest backend/tests/unit/test_runtime_session_service.py backend/tests/unit/test_tasks_endpoint.py -q` => `29 passed, 2 warnings in 18.06s`
- 2026-03-29T07:14:08Z `npm run build` => exit `0`; Next.js production build completed successfully. Existing repo noise remains: ESLint could not load `@typescript-eslint/recommended`, and static export emitted pre-existing MIME warnings for `.pdf/.doc/.docx`.
- 2026-03-29T07:14:08Z Manual restart-path validation is still pending. Previous sandboxed fixture seeding hit `pymysql.err.OperationalError` against local MySQL, so Phase 3 likely requires escalated local DB/API access or an alternate fixture path.
