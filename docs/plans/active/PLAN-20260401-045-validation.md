# Validation Ledger: PLAN-20260401-045

## Scope
- Validate that quick-runtime lease failures are corrected at the execution-host / orchestrator / runtime boundary.
- Preserve `RuntimeSessionService` lease authority as the single source of truth.
- Keep this plan separate from `PLAN-20260401-044`; no slideshow/prompt-synthesis scope is validated here.

## Acceptance Gates
### Review / boundary gate
- [x] Review confirms the failure is classified as host-liveness / lease-renewal bridge failure rather than media-agent business failure
- [x] Review confirms queue/worker stays transport-only and does not gain runtime authority
- [x] Review confirms `RuntimeSessionService` remains authoritative for attempt lease validation
- [x] Review confirms `mid-run heartbeat stopped/failed` is owned as an execution-host event, bridged by orchestrator, and validated by runtime control-plane lease checks

### Stage 1 gate: observability and diagnostics
- [x] Keepalive activation outcome is explicitly visible
- [x] Keepalive `stopped` / `failed` reasons are persisted into runtime diagnostics
- [x] Runtime failures distinguish activation failure, renewal failure, and final validation failure

### Stage 2 gate: orchestrator boundary tightening
- [x] Orchestrator does not silently continue a long-running attempt when keepalive is unavailable
- [x] Failure classification remains at the orchestrator/runtime boundary rather than the media-agent boundary
- [x] No tool or media-agent lease workaround is introduced

### Stage 3 gate: host-side correction
- [x] Host-side keepalive now exposes a terminal unhealthy probe that long-running video polling can consume without moving lease authority out of the execution-host / runtime boundary
- [ ] Stage 3 evidence identifies whether post-activation loss is `heartbeat_validation_failed` or `heartbeat_error`
- [x] Review confirms queue/broker state is not used as a proxy for runtime lease truth during the repair
- [ ] Long-running quick-runtime attempts can keep the lease live through normal completion
- [ ] No artifact-based completion fallback is introduced

## Automated Checks
- [x] Targeted tests for execution-host keepalive controller
- [x] Targeted tests for queued execution host keepalive context / bridge behavior
- [x] Targeted tests for provider polling keepalive-loss propagation
- [x] Targeted tests for orchestrator attempt lifecycle under keepalive failure
- [x] Retained runtime-session lease fresh-read / diagnostics tests

## Manual Checks
- [ ] Reproduce the current `video` lease-expiry flow and confirm diagnostics identify the bridge failure
- [ ] Compare at least one earlier `image` or `video` lease-expiry task to verify the systemic pattern
- [x] Static review confirms the post-activation stop handling remains at the execution-host/runtime boundary rather than the queue or media-agent business boundary
- [ ] Confirm successful long-running quick-runtime execution no longer terminates with opaque lease-expiry failure

## QC Rules
- Queue and worker health remain diagnostics only, not runtime truth.
- `RuntimeSessionService` remains the sole authority for attempt lease liveness.
- Media agents and tools must not own lease semantics.
- Artifacts such as `video_url`, final-frame files, or `scene_outputs.*` must not be promoted into completion authority.
- This plan does not reopen planner-visible progress-read-model work and does not overlap `PLAN-20260401-044`.

## Evidence Log
- 2026-04-01T03:59:42Z validation ledger created together with `PLAN-20260401-045`
- 2026-04-01T08:01:17Z Stage 1/2 evidence recorded: `test_task_queue.py` keepalive-controller diagnostics checks passed, `test_runtime_session_service.py` diagnostic upsert plus retained lease snapshot checks passed, and `test_orchestrator_runtime_mainline.py` verified fail-fast on keepalive activation unavailability while preserving existing runtime mainline behavior.
- 2026-04-01T08:01:17Z Completion remains pending because no reproduced long-running quick-runtime run has yet confirmed the original mid-run lease-renewal stop is corrected through normal completion.
- 2026-04-01T08:26:00Z Boundary review tightened the remaining Stage 3 target: the unresolved question is post-activation renewal loss inside the execution-host/orchestrator/runtime bridge, not queue ownership and not media-agent behavior.
- 2026-04-01T11:23:41Z Stage 3 partial evidence recorded: `test_task_queue.py -k attempt_lease_keepalive_controller` passed (`3 passed`), `test_zhipu_services.py -k keepalive` passed with `pytest_asyncio` (`1 passed`), `test_doubao_services_model_resolution.py` passed with `pytest_asyncio` (`3 passed`), and retained `test_runtime_session_service.py -k upsert_attempt_node_diagnostic_sync_replaces_keepalive_entry_for_same_attempt` passed (`1 passed`). Touched Stage 3 files also passed no-write syntax compilation via `compile(...)`. Full long-running quick-runtime reproduction and full-file `test_video_generation_tool.py` verdict remain pending in this window.
