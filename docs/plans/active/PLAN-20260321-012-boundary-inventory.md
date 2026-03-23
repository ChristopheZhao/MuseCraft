# Phase A Artifact: PLAN-20260321-012 Boundary Inventory
- Plan ID: PLAN-20260321-012
- Phase: A
- Status: checkpoint-ready
- Updated At: 2026-03-22T01:48:14Z

## 1. Purpose
- Freeze the ownership boundary for the current delivery stage before any backend/frontend refactor slice starts.
- Provide one explicit answer to three questions:
  - what `task_queue.py` is doing today
  - which responsibilities stay in queue/transport, and which must move out
  - what the frontend must treat as runtime truth vs diagnostics

## 2. Evidence Basis
- Current root-cause basis:
  - [SHO-20260321-0001](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/session-handoff/SHO-20260321-0001.md)
- Queue / worker implementation:
  - [task_queue.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py)
  - [tasks.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/tasks.py)
- Runtime / control-plane implementation:
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py)
- Frontend runtime/read-model implementation:
  - [VideoRequestForm.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/forms/VideoRequestForm.tsx)
  - [useTaskPolling.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useTaskPolling.ts)
  - [useWebSocket.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useWebSocket.ts)
  - [QuickModeWorkspace.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/preview/QuickModeWorkspace.tsx)
  - [AgentOrchestrator.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/agents/AgentOrchestrator.tsx)
  - [RealTimeProgress.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/progress/RealTimeProgress.tsx)
- Architecture constraints:
  - [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md)
  - [mas_runtime_control_plane_detailed_design_20260308.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_control_plane_detailed_design_20260308.md)

## 3. Ownership Layers
| Layer | Owns | Must Not Own |
| --- | --- | --- |
| External scheduler / queue infra | broker, worker process, revoke, queue depth, active/reserved/scheduled inspection | MAS node/gate semantics, runtime session SoT, HITL meaning |
| Queue adapter | enqueue gate, consumer entry, execution eligibility short-circuit, queue handle persistence | tool bootstrap, event-bus bootstrap, runtime session lifecycle, gate decision meaning, runtime failure writeback |
| Execution host / bootstrap | tool registry init, event bus reset, event loop lifecycle, dispatch host setup | queue policy, queue metadata persistence, frontend read model |
| Runtime / control-plane | `workflow_session / node / attempt / gate / decision`, resume/apply/fail/complete, runtime view | broker inspection, queue transport policy |
| Frontend runtime read model | current run view, gate status, current node, node detail projection, user-facing failure/paused state | queue health inference, broker semantics, worker liveness as business truth |

## 4. `task_queue.py` Responsibility Inventory
| Current area | Current responsibility | Target owner | Action |
| --- | --- | --- | --- |
| module init: sync engine/session factory | create sync DB access for queue consumer path | shared backend infra helper | keep for now or extract later; not the root boundary issue |
| `_resolve_task_execution_route()` | coarse execution route hint from task payload | queue adapter command builder | keep temporarily as thin routing metadata |
| `TaskQueueService.queue_task()` task lookup | load task and latest quick runtime session for enqueue eligibility | queue adapter | keep |
| `TaskQueueService.queue_task()` eligibility check | apply `get_queue_execution_block_reason(...)` before enqueue | queue adapter | keep |
| `TaskQueueService.queue_task()` `process_video_task.delay(...)` | send transport command to Celery | queue adapter | keep |
| `TaskQueueService.queue_task()` persist `celery_task_id` / set queued | persist queue handle and coarse transport status | queue adapter | keep |
| `sync_process_video_task()` `register_default_tools()` | initialize agent tool registry in worker | execution host / bootstrap | move out of queue layer |
| `sync_process_video_task()` `reset_event_bus()` | reset worker event bus before execution | execution host / bootstrap | move out of queue layer |
| `sync_process_video_task()` task fetch + DB retry loop | consumer-side task load with connection retry | queue consumer infra helper | may stay near consumer entry, but should not stay mixed with runtime logic |
| `sync_process_video_task()` worker-side eligibility short-circuit | drop stale/terminal/non-eligible executions | queue adapter | keep |
| `sync_process_video_task()` `asyncio.new_event_loop()` | create event loop for execution host | execution host / bootstrap | move out of queue layer |
| `sync_process_video_task()` `get_or_create_session_for_task_sync(...)` | create/load runtime session before dispatch | runtime / control-plane | move out of queue layer |
| `sync_process_video_task()` read `runtime_session.input_payload` | recover runtime-owned resume payload | runtime / control-plane | move out of queue layer |
| `sync_process_video_task()` `dispatch_generation(...)` | enter MAS mainline / harness execution | execution host calling runtime runner | move out of queue layer |
| exception path `mark_session_failed_sync(...)` | persist runtime failure state | runtime / control-plane | move out of queue layer |
| exception path non-quick `task.status = FAILED` | legacy coarse task failure fallback | task lifecycle / compatibility path | isolate; do not expand |
| `get_task_queue_stats()` | queue/worker diagnostics | external scheduler / queue infra | keep |
| `cancel_celery_task()` | revoke queue handle | external scheduler / queue infra | keep |

## 5. Phase B Extraction Order
### Slice 1: worker host/bootstrap extraction
- Extract `register_default_tools()`, `reset_event_bus()`, event loop creation, and `dispatch_generation(...)` hosting into a dedicated execution-host entrypoint.
- Leave `sync_process_video_task()` as a thin consumer wrapper that only:
  - loads the task
  - applies execution eligibility
  - hands execution to the extracted host

### Slice 2: runtime/control-plane ownership extraction
- Remove `get_or_create_session_for_task_sync(...)`, resume payload recovery, and runtime failure writeback from `task_queue.py`.
- Replace them with a runtime-owned command such as:
  - load existing session
  - run until wait/complete
  - mark failure inside control-plane path

## 6. Runtime-First Read-Model Priority
| Priority | Data source | Allowed use | Forbidden interpretation |
| --- | --- | --- | --- |
| 1 | `quickRuntime.status` / `quickRuntime.error_message` | top-level run state: running, waiting_gate, resuming, failed, completed | do not override with `nodes[*].status` or WS agent telemetry |
| 2 | `quickRuntime.active_gate` | HITL truth: whether a gate is awaiting human action and what actions are allowed | do not derive gate state from queue pending/backlog |
| 3 | `quickRuntime.current_node_key` | current active workflow node label | do not infer current node from telemetry agent names |
| 4 | `quickRuntime.nodes[]` | stage detail and node-level projection | `queued` here does not prove queue stall; it may mean the run failed before entering the node |
| 5 | `currentRequest` | current workspace run handle, subscription key, UI title/description shell | not business-state truth |
| 6 | `/tasks/{id}/status` coarse task payload | fallback coarse status, final-result retrieval, compatibility | not authoritative over runtime session for current-run state |
| 7 | WS agent telemetry / connection state | auxiliary diagnostics and activity hints | never current-run SoT |

## 7. Current Frontend Truth Chain
- Existing good direction:
  - [VideoRequestForm.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/forms/VideoRequestForm.tsx) discovers unfinished quick runs through `getCurrentQuickRun(...)`.
  - [QuickModeWorkspace.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/preview/QuickModeWorkspace.tsx) already renders failed/gate/current-node using `quickRuntime`.
  - [RealTimeProgress.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/progress/RealTimeProgress.tsx) explicitly treats WS telemetry as auxiliary only.
- Residual gap:
  - [useTaskPolling.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useTaskPolling.ts) still uses `/status` as a coarse control signal for completion/failure side effects.
  - [useWebSocket.ts](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/hooks/useWebSocket.ts) still carries agent telemetry and runtime refresh in the same flow, which keeps room for UI confusion if component consumers read telemetry too eagerly.
- Phase C target:
  - keep `currentRequest` as the run handle only
  - keep `quickRuntime` as the current-run SoT
  - constrain `/status` and WS telemetry to compatibility/diagnostics only

## 8. Resume Semantics Separation
### 8.1 Continue Existing Run
- Trigger:
  - [VideoRequestForm.tsx](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/src/components/forms/VideoRequestForm.tsx) `handleContinueExistingRun()`
- Meaning:
  - rebind frontend to an existing unfinished run
  - set `currentRequest`
  - hydrate `quickRuntime`
  - switch UI to `processing`
- Not allowed to mean:
  - create a new task
  - enqueue a new worker job
  - implicitly resume queue consumption

### 8.2 Gate Decision -> Resume Execution
- Trigger:
  - [tasks.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/tasks.py) `submit_script_gate_decision()`
- Meaning:
  - runtime/control-plane consumes the gate decision
  - session/node/gate/task state is updated via `RuntimeSessionService.submit_gate_decision_sync(...)`
  - only after that does API schedule another execution attempt
- Not allowed to mean:
  - queue layer interpreting human-review semantics on its own

### 8.3 Historical Broker Re-Consumption
- Trigger:
  - old broker message or stale queue handle gets consumed by worker again
- Meaning:
  - queue regression or stale transport artifact
- Not allowed to mean:
  - supported resume mechanism
  - frontend continuation semantics
  - runtime resume contract

## 9. Checkpoint A Conclusion
- Checkpoint A is satisfied when this artifact is treated as the canonical Phase A boundary reference for the current delivery stage.
- From this point onward:
  - any code change must name its owner layer first
  - any refactor that keeps runtime writeback or bootstrap logic in `task_queue.py` is out of bounds
  - any frontend change that lets queue/telemetry override `quickRuntime` is out of bounds

## 10. Immediate Next Action
- Proceed to Phase B, Slice 1:
  - extract execution host/bootstrap responsibilities out of [task_queue.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/task_queue.py)
  - keep queue enqueue/revoke/eligibility contract stable
