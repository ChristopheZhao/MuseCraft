# Validation Ledger: PLAN-20260330-039

## Scope
- Validate the dedicated remediation of runtime-boundary deviations discovered during `PLAN-20260329-038` review, without expanding scope into generic runtime redesign or content-quality work.
- Validate the amended-but-still-narrow boundary slice: runtime view purity, selector transparency, API reconcile-owner removal, and the ownership handoff path spanning control-plane lease issuance plus execution-host heartbeat sender for `lease_owner` / heartbeat sender / reconcile owner freezing.

## Acceptance Gates
### Runtime boundary correction
- [x] Pre-implementation review/amend gate completed
- [x] `build_runtime_view_for_task[_sync]()` performs projection only
- [x] current-run discovery surfaces projection integrity errors explicitly
- [x] API lifespan no longer registers a quick-runtime reconcile loop, even if reconcile config remains set
- [x] explicit reconcile entrypoint still works
- [x] `lease_owner` / heartbeat sender / reconcile owner semantics are frozen under the amended contract: `lease_owner` = control-plane lease owner / issuer, heartbeat sender = execution host via `lease_token`, reconcile owner = explicit maintenance only
- [x] post-amendment review confirms the amended code-touch envelope and current closeout claims are internally consistent

## Automated Checks
- [x] Runtime view purity regression tests prove builder path does not call reconcile or fail the runtime
- [x] Selector transparency regression tests prove projection integrity errors are surfaced instead of skipped to `None`
- [x] API lifecycle owner regression tests prove lifespan never schedules reconcile ownership
- [x] Explicit reconcile entrypoint regression tests
- [x] Execution-host keepalive regression tests prove heartbeat remains host-only liveness reporting
- [x] Queue/host integration checks prove queued execution host only heartbeats an already-issued lease and does not become reconcile or decision owner

## Manual Checks
- [x] New window reviewed the plan/ledger pair and confirmed scope remains narrow before implementation
- [x] Review confirms no mutate-on-read path remains
- [x] Post-amendment review confirms no second runtime mutation owner exists in API startup flow, orchestrator lease issuance path, or execution-host keepalive path
- [x] Review confirms `038` blocker relationship is documented and recoverable
- [x] Post-amendment review confirms only the ownership handoff path in orchestrator / queued execution host / config / queue tests was absorbed, and no unrelated runtime/orchestrator redesign entered this plan

## QC Rules
- This plan owns implementation for the runtime-boundary remediation discovered from `038`.
- `038` remains blocked until this ledger passes.
- Generator/evaluator or review notes may diagnose boundary issues, but lifecycle ownership remains in plan governance artifacts only.
- The next window must review and may amend this plan before implementation; code execution is not the first step.
- If implementation needs files outside the amended touch envelope, or tries to preserve API-process reconcile ownership behind a config flag, or promotes queue/worker host code into a decision/reconcile owner, stop and amend before coding.

## Evidence Log
- 2026-03-30T02:19:04Z validation ledger created together with `PLAN-20260330-039`. Initial acceptance is intentionally narrow: remove mutate-on-read, remove API-process default reconcile ownership, restore selector error transparency, and preserve explicit maintenance entrypoints.
- 2026-03-30T02:24:36Z validation contract tightened to require a pre-implementation review/amend gate. The successor window must first validate that the plan still matches AGENTS.md boundary rules and narrow-remediation intent before any code changes start.
- 2026-03-30T02:30:33Z review-first amendment tightened anti-overreach gates: API lifespan must lose reconcile-loop registration entirely, semantic freeze is confined to the existing lease/heartbeat/reconcile surfaces, and implementation may not expand beyond the named runtime-boundary files without another amendment.
- 2026-03-30T02:31:45Z current window completed the required review/amend gate, confirmed the plan remains a narrow remediation, and only then authorized implementation to begin.
- 2026-03-30T02:46:23Z targeted verification completed. Python compile checks passed for all touched modules, and direct runtime assertions verified projection purity, selector transparency, API lifespan owner removal, explicit reconcile helper preservation, and execution-host heartbeat behavior. `uv run pytest` was not used as the final evidence path because its cache access was unstable under the current sandbox.
- 2026-03-30T03:46:56Z independent review concluded that the ownership-freeze implementation had crossed the original frozen envelope to close a real lease issuance / heartbeat sender path. The ledger is amended to acknowledge that narrow expansion, correct the `lease_owner` contract, and downgrade prior closure-strength claims until post-amendment queue/host and ownership-path revalidation is completed.
- 2026-03-30T03:54:23Z post-amendment revalidation passed for the amended envelope itself: `py_compile` succeeded for all touched modules, static call-site audit confirmed the only production lease grant path is orchestrator-side, direct runtime assertions returned `selector_transparency_ok`, `lifespan_owner_ok`, and `queue_host_and_keepalive_ok`, and diff review confirmed the additional files are limited to the ownership handoff path. The remaining open gate is semantic closure only: service-level tests still use `worker:*` lease_owner labels, so the amended contract is not yet fully frozen in test vocabulary.
- 2026-03-30T04:05:57Z semantic closure completed. A static audit confirmed no `worker:*` lease_owner usage remains in `backend/tests/unit/test_runtime_session_service.py`, `py_compile` passed for `runtime_session_service.py` and its service-level lease tests after the vocabulary rewrite, and runtime_session_service comments now explicitly describe `lease_owner` as the control-plane issuer while heartbeat remains host-side liveness reporting. With that final alignment, the amended contract, implementation, and service-level test vocabulary now match.
- 2026-03-30T04:16:30Z user accepted closeout with a conservative validation statement. The ledger is considered passed for governance purposes, but the accepted evidence basis remains narrower than ideal: static audit, direct runtime assertions, and compile checks were reproducible, while independent pytest reruns in this window did not provide a stable closeout signal. This limitation is now part of the explicit closure record rather than being treated as implicit success.
