# PLAN-20260327-031 Validation

- Plan ID: PLAN-20260327-031
- Recorded At: 2026-03-27T14:14:42Z
- Status: completed

## Purpose
- Record phase-by-phase verification for [PLAN-20260327-031](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-031.md).
- Keep this MAS-mainline HITL resume-path alignment stream separate from [PLAN-20260327-029.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-029.md) schema work and the already completed provider-routing stream in [PLAN-20260327-030.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-030.md).

## Validation Matrix
### Phase 0
- Status: completed
- Planned checks:
  - confirm architecture ownership split across governance / gate / control / orchestration
  - confirm script-gate approval currently requeues into a fresh queued execution host
  - confirm `approve` path still runs `_llm_select_candidate_agents(...)` and `_llm_decompose_tasks(...)` before `skip_agents`
  - confirm `workflow.task_specs` already exists as orchestration projection
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`
- Evidence:
  - architecture docs explicitly place `workflow_session / node / attempt / gate / decision` and `pause / resume / retry / revise / replan / apply` in the control layer, while gate layer only produces decision input and may not directly advance session lifecycle
  - [tasks.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/api/v1/endpoints/tasks.py) `submit_script_gate_decision(...)` writes the decision through control-layer APIs and then requeues the task through `_schedule_task_execution(...)`
  - [queued_task_execution_host.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/queued_task_execution_host.py) reinitializes tool registry and event bus on every queued host run
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) currently executes candidate selection and task decomposition before `script_resume_action == "approve"` applies skip semantics
  - [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) already persists `workflow.task_specs`, and [context_assembler.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/context_assembler.py) already consumes that projection for runtime hints
- Results:
  - source review of the files listed above
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`

### Phase 1
- Status: completed
- Planned checks:
  - freeze explicit semantics for `approve` / `revise` / `replan`
  - decide authoritative continuation input for approval resume
  - confirm queue/worker ownership remains transport-only
- Evidence:
  - [script_review_contract.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/script_review_contract.py) already encodes `revise -> ["script_writer"]` and `replan -> ["concept_planner", "script_writer"]`, with distinct review guidance text
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) already persists `invalidation_scope="workflow"` for `replan` and clears `script_review_contract` for `approve`
  - [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) persists authoritative `workflow.task_specs` and `workflow.conditional_tasks`, while the activation-pool snapshot is explicitly diagnostics output
  - [orchestration_queue_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_queue_policy.py) can deterministically rebuild execution order from `task_specs` alone when `candidate_agents` is absent, which makes a deserialized `workflow.task_specs` projection a viable continuation input
  - repo audit found no existing loader that reads `workflow.task_specs` back into `Dict[AgentType, spec]`, so Phase 2 must implement that adapter instead of pretending the capability already exists
- Results:
  - source review of `script_review_contract.py`, `runtime_session_service.py`, `orchestration_state_adapter.py`, `orchestration_queue_policy.py`, `script_writer.py`, `concept_planner.py`, and `orchestrator.py`
  - frozen contract result:
    - `approve`: control-plane continuation, no top-level planning, no `script_review_contract`
    - `revise`: node-scoped script continuation, retain `script_review_contract`, target `script_writer` only
    - `replan`: workflow-scoped continuation, may legitimately re-enter candidate selection and task decomposition

### Phase 2
- Status: completed
- Planned checks:
  - approve path avoids candidate selection / task decomposition before continuation is applied
  - revise/replan path remains explicitly replannable
  - no queue/worker or gate-layer ownership regression introduced
- Evidence:
  - [orchestration_state_adapter.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/orchestration_state_adapter.py) now exposes a narrow `load_task_specs(...)` loader that deserializes persisted `workflow.task_specs` / `workflow.conditional_tasks` back into orchestration-owned structures instead of promoting diagnostics snapshots into runtime authority
  - [runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/runtime_session_service.py) now owns `approve` continuation live-state mutation through `consume_script_approval_continuation_sync(...)`, which consumes the approved gate decision and performs the `APPROVED -> COMPLETED` plus `RESUMING -> RUNNING` transition inside the control plane
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) now routes `approve` and `revise` through `_load_authoritative_resume_task_specs(...)` before any candidate selection or task decomposition, and `approve` consumes the control-plane continuation command instead of directly mutating runtime session/node/task state
  - [test_orchestrator_runtime_mainline.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_orchestrator_runtime_mainline.py) now asserts:
    - `approve` does not increment planning-call counters on the second run
    - `approve` continuation is consumed through `RuntimeSessionService.consume_script_approval_continuation_sync(...)`
    - `revise` does not rerun `concept_planner` and re-enters only `script_writer`
    - `replan` still increments planning-call counters and reruns `concept_planner`
  - [test_runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_runtime_session_service.py) now asserts the approve continuation transition itself stays in the control plane: session returns to `RUNNING`, script node becomes `COMPLETED`, and no runtime live-state mutation needs to occur in the orchestrator
- Results:
  - `backend/.venv/bin/python -m py_compile backend/app/agents/orchestrator.py backend/app/services/runtime_session_service.py backend/tests/unit/test_orchestrator_runtime_mainline.py backend/tests/unit/test_runtime_session_service.py`
  - `backend/.venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_runtime_session_service.py -k 'consume_script_approval_continuation_sync_rehomes_runtime_transition'`
  - Result summary: `1 passed, 10 deselected`
  - `backend/.venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_orchestrator_runtime_mainline.py -k 'resumes_after_script_approve_without_kernel or revise_reopens_script_gate_via_concept_and_script or replan_reopens_script_gate_with_review_contract'`
  - Result summary: `3 passed, 4 deselected`

### Phase 3
- Status: completed
- Planned checks:
  - focused backend tests/probes cover approval resume without redundant front-loaded planning
  - governance asset sync review
  - user confirmation gate before lifecycle closeout
- Evidence:
  - [test_runtime_session_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_runtime_session_service.py) now directly covers the control-plane approve continuation transition and proves the orchestration layer no longer needs to mutate runtime session/node/task state to consume approval
  - [test_orchestrator_runtime_mainline.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_orchestrator_runtime_mainline.py) continues to cover `approve`, `revise`, and `replan` as three distinct continuation contracts
  - [orchestrator.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py) no longer contains the previous direct runtime-state mutation block for approve continuation
  - plan / validation / index are now synchronized on the corrected Phase 2 boundary and Phase 3 completion state
- Results:
  - `backend/.venv/bin/python -m py_compile backend/app/agents/orchestrator.py backend/app/services/runtime_session_service.py backend/tests/unit/test_orchestrator_runtime_mainline.py backend/tests/unit/test_runtime_session_service.py`
  - `backend/.venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_runtime_session_service.py -k 'consume_script_approval_continuation_sync_rehomes_runtime_transition'`
  - Result summary: `1 passed, 10 deselected`
  - `backend/.venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_orchestrator_runtime_mainline.py -k 'resumes_after_script_approve_without_kernel or revise_reopens_script_gate_via_concept_and_script or replan_reopens_script_gate_with_review_contract'`
  - Result summary: `3 passed, 4 deselected`
  - `rg -n "script_node\\.status|runtime_session\\.current_node_key = None|runtime_session\\.current_attempt_id = None|task\\.status = TaskStatus\\.IN_PROGRESS\\.value|db\\.commit\\(\\)" backend/app/agents/orchestrator.py`
  - Result summary: zero matches
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`

## Notes
- 2026-03-27T14:14:42Z completed Phase 0 audit only. The review confirms that HITL is not a standalone fifth layer and not merely a gate-layer concern: gate input generation and gate opening are aligned, queue-host restart is an expected transport/container behavior, and the real residual issue is that control-plane continuation semantics for `approve` are consumed too late because orchestrator still performs top-level LLM planning before applying runtime skip state. The next phase is therefore frozen to explicit continuation-contract design rather than queue refactoring or gate-layer patching.
- 2026-03-27T14:23:46Z completed Phase 1 contract freeze. The repo now has an explicit architectural decision for all three HITL actions: `approve` must bypass top-level planning and resume from post-script execution using persisted orchestration projections as continuation input; `revise` remains a node-scoped script-only continuation with `script_review_contract`; and `replan` remains the sole workflow-scoped action allowed to re-enter candidate selection and task decomposition. The remaining implementation work is therefore narrowed to a control-plane-driven loader/split, not a queue or gate redesign.
- 2026-03-27T14:38:40Z completed Phase 2 implementation. The runtime now loads persisted task specs directly for `approve` / `revise` continuation, fails fast if that authority is missing, bypasses top-level planning for those two actions, and preserves `replan` as the only workflow-scoped action that still re-enters candidate selection and decomposition. Focused resume-path validation passed on the three direct HITL cases, and no queue/worker or gate-layer ownership changes were introduced.
- 2026-03-27T14:56:40Z corrected the residual Phase 2 architecture leak before closeout. Follow-up review found that `approve` continuation still let `orchestrator.py` directly mutate runtime live state after the top-level planning bypass had been fixed. The correction moved that transition into `RuntimeSessionService.consume_script_approval_continuation_sync(...)`, added a direct service-level test for the `APPROVED -> COMPLETED` / `RESUMING -> RUNNING` mutation, and tightened the orchestrator test to assert the continuation command is consumed through the control plane instead of by direct orchestration-side state writes.
- 2026-03-27T15:20:03Z completed Phase 3 without lifecycle closeout. Validation now records the corrected control-plane boundary, confirms the direct approve continuation transition plus the three HITL resume paths all pass focused tests, confirms the old orchestration-side runtime mutation block is gone, and moves the plan to awaiting user confirmation so architectural acceptance remains an explicit gate.
- 2026-03-27T15:23:11Z completed lifecycle closeout after explicit user confirmation. Validation status now matches the plan as `completed`, and the stream closes with architecture acceptance recorded: control-plane owns the approve continuation transition, orchestrator consumes but does not mutate runtime live state, and queue/worker remain transport-only.
