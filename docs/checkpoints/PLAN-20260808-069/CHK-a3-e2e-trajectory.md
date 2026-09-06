# PLAN-20260808-069 Amendment A3 — E2E trajectory map

This artifact maps the approved PLAN-069 acceptance boundaries to the current production composition. It is evidence for A3-1/A3-2, not a second plan or lifecycle status source.

## 1. Quick production trajectory

| Boundary | Current production owner | Observable contract | Test substitution rule |
| --- | --- | --- | --- |
| Public command | `api/v1/endpoints/tasks.py::create_task` | Durable `Task` plus quick `WorkflowSession` created atomically before dispatch | Exercise the endpoint; do not construct a task/runtime pair directly in the E2E |
| Transport dispatch | `TaskQueueService.queue_task` | Stable task ID enters `QueuedExecutionUseCase.enqueue`; Celery receipt is transport metadata only | Replace only the Celery dispatch port with deterministic in-process delivery |
| Application execution | `QueuedExecutionUseCase.execute` | Loads the authoritative runtime payload and builds a typed `AgentExecutionRequest` | Use the real use case and execution host; no direct `OrchestratorAgent._execute_impl` call |
| Process host | `run_agent_execution_in_host` | Owns event/tool process setup, event loop and attempt keepalive context | Use unchanged |
| MAS composition | `build_orchestrator_agent` | One `OrchestratorAgent` with production specialist Agents and runtime transition/resume facades bound to the same store | Use the production composition root; deterministic collaborators may be injected only at existing LLM/tool/provider/service ports, never by replacing an Agent |
| Runtime control | `OrchestratorAgent` + `OrchestrationControlPlane` + runtime facades | Attempts, gates, decisions and terminal session state are persisted by the MAS control plane | Never replace with a fake controller or infer success from the worker result |
| Human continuation | `submit_script_gate_decision` | Decision binds to the active script gate and re-dispatches the same task/runtime session | Exercise the public endpoint and assert the same session identity resumes |
| External observation | `get_task_runtime` -> `RuntimeReadModelService` -> `RuntimeReadModelPresenter` | Gate, nodes, attempts and terminal `summary_output` are the client-visible truth | Assert only this projection for business state; queue/Celery fields remain diagnostics |

## 2. Project/Episode production trajectory

`projects.orchestrate_project` creates a project execution task, then the normal `TaskQueueService` and `QueuedExecutionUseCase` route it to `EpisodeExecutionCoordinator`. The coordinator selects approved episodes and invokes `PersistentEpisodeWorkflowExecutor`, which creates one durable child task/runtime session and calls the same production-composed `OrchestratorAgent`.

The Project wrapper may select episodes and aggregate child receipts. It must not invent child success, own attempt/gate semantics, or project a second runtime truth. Project read models may aggregate authoritative child runtime outputs only.

## 3. Acceptance mapping

| PLAN-069 invariant | Positive evidence required | Counterexample required |
| --- | --- | --- |
| Runtime is the only business-state SoT | API-created task reaches waiting gate/completed through persisted runtime; GET runtime reports it | Worker/queue return values cannot make runtime completed |
| Report and attempt success are exact | Current attempt report is accepted and attempt becomes completed before terminal promotion | Missing status/report/finalize receipt or stale attempt identity fails closed |
| Continuation identity is stable | Script approval resumes the same task, workflow, runtime session and scheduled agent contract | Cross-workflow/execution/agent continuation identity is rejected |
| Scene-output consumption uses an explicit projection | Downstream planning context observes accepted `scene_outputs.*` receipts through `progress_read_model` | Raw observation receipts, rejected outputs or empty authoritative sets do not become accepted progress |
| Project is a wrapper over the same MAS runtime | Episode child is created with a quick runtime and executed by the production Orchestrator composition | Wrapper output without canonical child status cannot become completed |

## 4. Existing `backend/tests/e2e` classification

| File | Classification | Evidence | Action |
| --- | --- | --- | --- |
| `test_complete_mas_system.py` | Invalid legacy pseudo-E2E | Directly constructs agents/memory adapters, catches failures, references undefined workflow variables, and ends with hard-coded readiness booleans | Delete |
| `test_final_integration.py` | Invalid legacy pseudo-E2E | Manually builds an execution queue and writes working-memory facts; bypasses API, queue use case, execution host, runtime attempts/gates and read model | Delete |
| `test_final_workflow.py` | Supplier/tool script | Directly calls script/image tools and passes with heuristic length/keyword scoring plus a one-failure tolerance | Delete |
| `test_first_last_frame.py` | Supplier debug script | Uses hard-coded remote URLs/local files and swallows failures without assertions | Delete |
| `test_full_audio_integration.py` | Manual media script | Downloads a stale remote asset, conditionally skips composition, hand-builds an FFmpeg command and calls private agent heuristics | Delete |
| `test_full_audio_workflow.py` | Legacy direct-agent script | Requires a developer-local video, calls private `_execute_impl`, and treats missing tools/Suno errors as success | Delete |

No current file is a valid starting implementation for the production E2E. Business scenarios may be restated in new tests, but none of these files or their compatibility assumptions should be retained.

## 5. Production defect found during mapping

The current application path still contains success-defaulting outside the MAS control plane:

- `QueuedExecutionUseCase.execute` returns `result_payload.get("status") or "completed"` for both Quick/Project host results and episode coordination results.
- `EpisodeExecutionCoordinator.execute` records `str(output.get("status") or "completed")` for child workflows.

These branches can present a missing canonical status as success even though queue/application wrappers do not own completion semantics. This is a production boundary defect, not a reason to weaken the E2E. A separate amendment must register the repair before production code changes; the counterexample should require an explicit canonical child/host status and preserve the authoritative runtime state.

Resolution: Amendment A4 was registered before the production edit. The three success defaults are now removed; one thin `require_canonical_execution_status` boundary validates caller-owned allowed values, while the existing failure transitions remain the only writers of failed runtime/task state. No alias, inferred success, legacy compatibility path, or second status store was added.

## 6. First implementation slice

1. Deleted the six invalid legacy E2E files.
2. Registered Amendment A4 and repaired the success-defaulting defect negative-first.
3. Added `backend/tests/e2e/test_quick_mas_runtime.py` using the public Quick endpoints, real queue use case/host/Orchestrator/runtime/read-model, deterministic delivery at the Celery port, and deterministic LLM/tool collaborators at existing boundaries. Amendment A5 subsequently removed the initial specialist-Agent replacement from this maintained test.
4. Added Project wrapper/runtime identity evidence after the A4 focused suite passed.
