# Validation Ledger: PLAN-20260329-037

## Scope
- Validate that generic stale-run resume is owned by control-plane continuation checkpoints rather than guarded re-dispatch.

## Automated Checks
- [ ] Backend tests for continuation checkpoint schema/validation
- [ ] Backend tests for generic resume consumer and fail-fast rejection
- [ ] Backend tests for `resume_control` reason precedence
- [ ] Frontend/API contract checks if projection shape changes

## Manual Checks
- [ ] API restart only reattaches `quick/current` view and subscriptions
- [ ] Live transport returns view-only state and no resume CTA
- [ ] Stale run without checkpoint returns `resume_blocked`
- [ ] Stale run with valid checkpoint returns `resume_available`
- [ ] Explicit resume on valid checkpoint produces new runtime progression evidence
- [ ] `waiting_gate` remains gate-owned and rejects generic resume

## Evidence Log
- Pending
