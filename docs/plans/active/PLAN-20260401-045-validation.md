# Validation Ledger: PLAN-20260401-045

## Scope
- Validate that quick-runtime lease failures are corrected at the execution-host / orchestrator / runtime boundary.
- Preserve `RuntimeSessionService` lease authority as the single source of truth.
- Keep this plan separate from `PLAN-20260401-044`; no slideshow/prompt-synthesis scope is validated here.
- Keep this plan separate from `PLAN-20260402-047`; image-composer diagnostic cleanup remains an unfinished parallel stream and is not validated here.
- Treat `PLAN-20260402-048` as already having repaired the upstream `video_generator` business-boundary chain; this ledger validates only the remaining runtime lease bridge.

## Acceptance Gates
### Review / boundary gate
- [x] Review confirms the failure is classified as host-liveness / lease-renewal bridge failure rather than media-agent business failure
- [x] Review confirms queue/worker stays transport-only and does not gain runtime authority
- [x] Review confirms `RuntimeSessionService` remains authoritative for attempt lease validation
- [x] Review confirms `mid-run heartbeat stopped/failed` is owned as an execution-host event, bridged by orchestrator, and validated by runtime control-plane lease checks

### RCA gate
- [x] Root cause is localized to one owning implementation path before further repair patches are applied
- [x] Architecture review concludes whether the current lease model is design-valid, misconfigured, or architecturally unsound for long-running quick-runtime execution
- [x] Evidence distinguishes activation availability, background renewal execution, renewal persistence/validation, and unhealthy-state diagnostic publication
- [x] Reproduced runtime evidence includes runtime DB lease timestamps plus node diagnostics, not only text logs
- [x] Stage A verdict is recorded: `lease owner`, `keepalive bridge`, and `error surface` are explicitly separated and no queue/worker authority drift is introduced
- [x] Stage B diagnostic receipts exist for `activation_requested`, `first_heartbeat_ack`, `heartbeat_begin`, `heartbeat_end`, `deactivate_reason`, and `completion_validation_failed`
- [x] Stage C replay evidence narrows the failure to one class: activation defect, renewal/blocking defect, target lifecycle defect, or runtime validation freshness defect
- [x] Stage D output names one concrete failing file/function rather than a multi-factor symptom cluster

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
- [x] Stage 3 evidence identifies whether post-activation loss is `heartbeat_validation_failed` or `heartbeat_error`
- [x] Review confirms queue/broker state is not used as a proxy for runtime lease truth during the repair
- [x] Long-running quick-runtime attempts can keep the lease live through normal completion
- [x] No artifact-based completion fallback is introduced

## Automated Checks
- [x] Targeted tests for execution-host keepalive controller
- [x] Targeted tests for queued execution host keepalive context / bridge behavior
- [x] Targeted tests for provider polling keepalive-loss propagation
- [x] Targeted tests for orchestrator attempt lifecycle under keepalive failure
- [x] Retained runtime-session lease fresh-read / diagnostics tests
- [x] RCA diagnostics tests prove lifecycle receipts are emitted without weakening lease authority
- [x] RCA replay-focused tests or harnesses can differentiate "no first heartbeat" from "renewal stopped after first heartbeat"

## Manual Checks
- [x] Reproduce the current `video` lease-expiry flow and confirm diagnostics identify the bridge failure
- [x] Compare at least one earlier `image` or `video` lease-expiry task to verify the systemic pattern
- [x] Static review confirms the post-activation stop handling remains at the execution-host/runtime boundary rather than the queue or media-agent business boundary
- [x] Confirm successful long-running quick-runtime execution no longer terminates with opaque lease-expiry failure
- [x] Record one end-to-end replay timeline that includes activation, first-heartbeat outcome, last successful heartbeat, and completion validation point

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
- 2026-04-02T15:47:10Z Reproduced `task_db_id=1039` and inspected runtime DB session `33` / attempt `47`: `video_generator` business execution completed, but node completion failed with `Workflow attempt 47 execution lease expired`. Node diagnostics retained only a final `execution_lease_snapshot` with `reason_code=lease_validation_failed`, `last_heartbeat_at=2026-04-02T14:32:39+00:00`, and `lease_expires_at=2026-04-02T14:37:39+00:00`; no decisive `execution_host_keepalive` stop/fail diagnostic was present. Validation is therefore amended to require RCA closure before further repair.
- 2026-04-02T15:47:10Z RCA scope widened at the architecture boundary: validation must now determine not only where renewal stops, but also whether the current lease design itself is appropriate for quick-runtime long-running nodes before corrective code changes are accepted.
- 2026-04-03T02:12:40Z Validation amendment: RCA is now checkpointed by stage. Future work must first produce Stage A owner/boundary verdicts, then Stage B diagnostic receipts, then Stage C replay evidence, and only after Stage D single-path localization may repair patches be accepted.
- 2026-04-03T02:12:40Z Stage A verdict recorded: attempt-scoped lease remains design-valid as control-plane fencing, queue / worker / WebSocket remain non-authoritative, and the current defect is narrowed to an under-specified keepalive contract with overly deep lease-surface leakage rather than queue authority drift.
- 2026-04-03T02:28:29Z Stage B receipts landed in code: execution-host keepalive now emits explicit activation, heartbeat-start, first-heartbeat-ack, heartbeat-end, explicit deactivation, and completion-validation-failed diagnostics. Direct-script assertions passed for the new receipt paths, while backend `pytest` remains operationally sticky in this window and full replay evidence is still pending.
- 2026-04-03T02:55:00Z Stage C correction recorded: the earlier bounded synthetic `advanced=False` observation is no longer considered decisive because it mixed a sub-second observation window with the default `heartbeat=60s` configuration and, in one probe, a mismatched runtime DB between the fake orchestrator path and the host keepalive controller.
- 2026-04-03T02:55:00Z New controlled bridge evidence recorded: with a shared threaded-SQLite runtime DB, patched `core_database.SessionLocal`, and compressed keepalive interval (`0.05s`), `run_generation_in_host(quick)` successfully produced lease advancement plus `activation_requested`, `heartbeat_begin`, `first_heartbeat_ack`, and `deactivated` receipts. This narrows the remaining fault away from the pure quick-host bridge logic and toward the real runtime environment / timing path still pending replay.
- 2026-04-03T03:08:00Z Additional Stage C bridge evidence recorded: a second shared-DB quick-host replay with an intentionally blocked heartbeat callback reproduced the silent-expiry window directly in the bridge path. Mid-run, the attempt lease was already expired while the controller still reported healthy and no terminal `execution_host_keepalive` stop/fail diagnostic existed yet; after releasing the blocked heartbeat, the controller transitioned unhealthy and persisted `execution_host_keepalive` with `reason_code=heartbeat_validation_failed`.
- 2026-04-03T03:08:00Z Combined Stage C verdict at this checkpoint: activation and pure quick-host bridge wiring are no longer the leading suspect; the remaining leading defect class consistent with the reproduced production symptom is renewal blocking / missing heartbeat watchdog in the real runtime environment. Real quick-runtime replay with the new receipts remains required before Stage D repair closure.
- 2026-04-03T03:31:49Z Fresh real replay on `task_db_id=1043` / session `37` / attempt `55` reproduced the failure after all three scene videos were generated and persisted. During the same `video` attempt, runtime projections recorded multiple successful heartbeat renewals, but completion/failure diagnostics still reported `last_heartbeat_at=2026-04-03T03:17:53+00:00` and `lease_expires_at=2026-04-03T03:22:53+00:00`, proving the completion-time authority path did not observe the later renewals.
- 2026-04-03T03:31:49Z Live MySQL RCA probe established `@@transaction_isolation = REPEATABLE-READ`. A minimal two-session script showed that after `db2` commits `heartbeat_attempt_lease_sync`, `db1.expire_all()` still reads the pre-heartbeat lease timestamps until `db1.rollback()` clears the old transaction snapshot. This localizes the defect to runtime validation freshness on the long-lived orchestrator/task-queue session rather than to keepalive production itself.
- 2026-04-03T03:31:49Z Stage D closure recorded: the owning failing path is `task_queue.sync_process_video_task` long-lived sync session + `RuntimeSessionService.complete_node_attempt_sync` / `fail_node_attempt_sync` fresh-read path under MySQL repeatable-read semantics. The remaining repair is therefore a bounded control-plane session/transaction freshness correction, not a keepalive-loop rewrite.
- 2026-04-03T04:18:02Z Stage E repair was validated in the real quick-runtime path. After the orchestrator switched completion/failure/gate transitions onto fresh short-lived control-plane sessions, a retry of `task_db_id=1043` created runtime session `40`; `video` attempt `62` completed with `execution_host_keepalive_activation_requested`, `first_heartbeat_ack`, `heartbeat_end`, and `deactivated` receipts, without any `execution_host_keepalive_completion_validation_failed` diagnostic, and runtime advanced through `compose` attempt `63`, `quality` attempt `64`, and final task status `completed`.
- 2026-04-03T04:18:02Z Closure evidence also confirms no artifact-based completion fallback was introduced: `RuntimeSessionService` remained the authority, `video` node status became `completed` through normal control-plane transition, and the previous opaque `Workflow attempt <id> execution lease expired` failure did not recur in the validated replay.
