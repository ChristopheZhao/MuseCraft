import asyncio
import json
import logging
import tempfile
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.orchestration_runtime_transition_facade as transition_facade_module
from app.agents import orchestrator as orchestrator_module
from app.agents.base import AgentError
from app.agents.orchestrator import OrchestratorAgent
from app.core.database import Base
from app.core.prompt_manager import get_prompt_manager
from app.domain import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentType,
    JsonObjectPayload,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    TaskStatus,
    TaskType,
    WorkflowAttemptStatus,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)
from app.infrastructure import SqlAlchemyRuntimeAttemptStore
from app.models import Task, WorkflowNodeAttempt, WorkflowSession
from app.services.agent_execution_boundary import build_agent_execution_request
from app.services.context_assembler import ContextContractAssembler
from app.services.orchestration_protocol import OrchestrationProtocol
from app.services.orchestration_runtime_resume_bootstrap_facade import (
    OrchestrationRuntimeResumeBootstrapError,
    OrchestrationRuntimeResumeBootstrapFacade,
)
from app.services.orchestration_runtime_transition_facade import (
    OrchestrationRuntimeTransitionFacade,
)
from app.services.orchestration_state_adapter import OrchestrationStateAdapter
from app.services.runtime_attempt_control_plane import RuntimeAttemptControlPlane
from app.services.runtime_read_model_service import (
    RuntimeReadModelPresenter,
    RuntimeReadModelService,
)
from app.services.runtime_session_bootstrap_control_plane import RuntimeSessionBootstrapControlPlane
from app.services.runtime_session_control_plane import RuntimeSessionControlPlane
from app.services.script_gate_decision_control_plane import ScriptGateDecisionControlPlane


def test_video_audio_capability_failure_is_not_fabricated_as_unsupported():
    agent = object.__new__(OrchestratorAgent)

    def _raise_provider_config_error():
        raise RuntimeError("provider config unavailable")

    agent.video_config = SimpleNamespace(
        get_current_provider_config=_raise_provider_config_error,
    )

    with pytest.raises(AgentError, match="video_audio_capability_unavailable") as exc_info:
        agent._get_video_audio_capability()

    assert getattr(exc_info.value, "reason_code", None) == "video_audio_capability_unavailable"


def test_video_audio_capability_rejects_missing_supplier_fact():
    agent = object.__new__(OrchestratorAgent)
    agent.video_config = SimpleNamespace(
        get_current_provider_config=lambda: SimpleNamespace(
            provider_name="provider-a",
            native_audio_param_name="generate_audio",
            native_audio_default_enabled=None,
        ),
    )

    with pytest.raises(AgentError, match="supports_native_audio must be boolean"):
        agent._get_video_audio_capability()


class _FakeSharedStore(dict):
    def put(self, key, value):
        self[key] = value


class _FakeShortTermService:
    def __init__(self, shared_store):
        self._shared_store = shared_store

    def create_or_get(self, *args, **kwargs):
        return self._shared_store

    def get(self, *args, **kwargs):
        return self._shared_store

    def reset(self, *args, **kwargs):
        return None

    def cleanup_workflow(self, *args, **kwargs):
        return None


class _FakeAgent:
    def __init__(self, name, output, calls):
        self.agent_name = name
        self._output = dict(output)
        self._calls = calls

    async def execute(self, request):
        assert isinstance(request, AgentExecutionRequest)
        self._calls.append(
            {
                "agent_name": self.agent_name,
                "input_data": request.input_data.to_dict(),
                "execution_order": request.execution_order,
            }
        )
        return _agent_result(self._output)


class _FlakyAgent:
    def __init__(self, name, *, first_error, success_output, calls):
        self.agent_name = name
        self._first_error = first_error
        self._success_output = dict(success_output)
        self._calls = calls
        self._attempt = 0

    async def execute(self, request):
        assert isinstance(request, AgentExecutionRequest)
        self._attempt += 1
        self._calls.append(
            {
                "agent_name": self.agent_name,
                "input_data": request.input_data.to_dict(),
                "execution_order": request.execution_order,
                "attempt": self._attempt,
            }
        )
        if self._attempt == 1:
            raise self._first_error
        return _agent_result(self._success_output)


def _fake_report(boundary_event: str, artifact_ref: str) -> dict:
    return {
        "status": "completed",
        "boundary_event": boundary_event,
        "gate_triggers": [],
        "artifacts": [{"kind": "shared_fact", "ref": artifact_ref}],
        "reflection": {
            "reported_gaps": [],
            "reported_hints": [],
        },
    }


def _agent_result(output: dict) -> AgentExecutionResult:
    normalized = dict(output)
    report = normalized.pop("orchestration_report", None)
    return AgentExecutionResult(
        output_data=JsonObjectPayload.from_mapping(
            normalized,
            field_path="test.agent_output",
        ),
        orchestration_report=(
            JsonObjectPayload.from_mapping(
                report,
                field_path="test.orchestration_report",
            )
            if report is not None
            else None
        ),
    )


def _orchestrator_request(task: Task, input_data: dict) -> AgentExecutionRequest:
    return build_agent_execution_request(
        task=task,
        agent_type=AgentType.ORCHESTRATOR,
        input_data=input_data,
        execution_order=0,
    )


def _runtime_summary_stub(**kwargs):
    return dict(kwargs)


class _QueuedPlanLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("plan llm called more times than expected")
        return self._responses.pop(0)


def _fake_script_review_boundary(**kwargs):
    return {
        "payload": {
            "concept_plan": {"scenes": [{"scene_number": 1}]},
            "scene_overview": {"scenes": [{"scene_number": 1, "visual_description": "stub scene"}]},
            "scene_scripts": {"1": {"script_text": "Scene 1 approved script"}},
        },
        "summary": {"total_scenes": 1},
        "script_preview_text": "preview",
    }


def _build_sync_db():
    tmpdir = tempfile.TemporaryDirectory(prefix="orchestrator_runtime_mainline_")
    engine = create_engine(
        f"sqlite:///{tmpdir.name}/runtime.sqlite3",
        connect_args={"check_same_thread": False},
    )
    original_dispose = engine.dispose

    def _dispose_with_tmpdir_cleanup():
        try:
            original_dispose()
        finally:
            tmpdir.cleanup()

    engine.dispose = _dispose_with_tmpdir_cleanup
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return engine, SessionLocal


def _create_task(sync_db):
    task = Task(
        title="Orchestrator Runtime Mainline Test",
        description="test",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.PENDING.value,
        input_parameters={"user_prompt": "test prompt"},
    )
    sync_db.add(task)
    sync_db.commit()
    sync_db.refresh(task)
    return task


def _create_runtime_session(sync_db, task):
    record = RuntimeSessionBootstrapControlPlane(
        SqlAlchemyRuntimeAttemptStore(sync_db)
    ).create_quick_session(
        task_id=str(task.task_id),
        expected_task_status=TaskStatus(str(task.status)),
        expected_latest_session_id=None,
        input_payload=JsonObjectPayload.from_mapping(
            task.input_parameters or {},
            field_path="test.runtime_input_payload",
        ),
    )
    sync_db.commit()
    return record


def _submit_script_decision(
    sync_db,
    *,
    session_id,
    action,
    feedback_text,
    structured_constraints=None,
):
    sync_db.expire_all()
    store = SqlAlchemyRuntimeAttemptStore(sync_db)
    session = store.load_session(session_id)
    assert session is not None
    decision = ScriptGateDecisionControlPlane(store).submit(
        session_id=session_id,
        node_key="script",
        action=action,
        feedback_text=feedback_text,
        structured_constraints=JsonObjectPayload.from_mapping(
            structured_constraints or {},
            field_path="test.script_decision_constraints",
        ),
        actor_type="human",
        actor_id="test-reviewer",
        task_id=session.task_id,
        expected_task_status=session.task_status,
    )
    sync_db.commit()
    return decision


def _start_runtime_checkpoint_attempt(sync_db, session_id, *, node_key):
    sync_db.expire_all()
    store = SqlAlchemyRuntimeAttemptStore(sync_db)
    session = store.load_session(session_id)
    assert session is not None
    attempt = RuntimeAttemptControlPlane(store).start_attempt(
        session_id=session_id,
        node_key=node_key,
        trigger_reason="initial",
        requested_by="test",
        input_contract=JsonObjectPayload.empty(),
        task_transition=RuntimeTaskTransition(
            task_id=session.task_id,
            expected_status=session.task_status,
            target_status=TaskStatus.IN_PROGRESS,
            requires_human_review=False,
        ),
    )
    return store, attempt


def _load_runtime_view_from_fresh_session(SessionLocal, task_id):
    inspect_db = SessionLocal()
    try:
        fresh_task = inspect_db.query(Task).filter(Task.id == int(task_id)).first()
        if fresh_task is None:
            raise AssertionError(f"task {task_id} missing in fresh-session inspection")
        model = RuntimeReadModelService(SqlAlchemyRuntimeAttemptStore(inspect_db)).load_for_task(
            str(fresh_task.task_id)
        )
        if model is None:
            raise AssertionError(f"runtime for task {task_id} missing in fresh-session inspection")
        return RuntimeReadModelPresenter.to_payload(model).to_dict()
    finally:
        inspect_db.close()


def _load_task_snapshot_from_fresh_session(SessionLocal, task_id):
    inspect_db = SessionLocal()
    try:
        fresh_task = inspect_db.query(Task).filter(Task.id == int(task_id)).first()
        if fresh_task is None:
            raise AssertionError(f"task {task_id} missing in fresh-session inspection")
        return {
            "id": fresh_task.id,
            "status": fresh_task.status,
        }
    finally:
        inspect_db.close()


def _load_runtime_session_snapshot_from_fresh_session(SessionLocal, session_id):
    inspect_db = SessionLocal()
    try:
        fresh_session = SqlAlchemyRuntimeAttemptStore(inspect_db).load_session(int(session_id))
        if fresh_session is None:
            raise AssertionError(
                f"runtime session {session_id} missing in fresh-session inspection"
            )
        return {
            "id": fresh_session.session_id,
            "status": fresh_session.status.value,
        }
    finally:
        inspect_db.close()


def _load_runtime_node_snapshot_from_fresh_session(SessionLocal, session_id, node_key):
    inspect_db = SessionLocal()
    try:
        fresh_node = SqlAlchemyRuntimeAttemptStore(inspect_db).load_node(int(session_id), node_key)
        if fresh_node is None:
            raise AssertionError(
                f"runtime node {node_key} missing for session {session_id} in fresh-session inspection"
            )
        return {
            "id": fresh_node.node_id,
            "status": fresh_node.status.value,
            "diagnostics": [item.to_dict() for item in fresh_node.diagnostics],
        }
    finally:
        inspect_db.close()


def _load_runtime_attempt_snapshot_from_fresh_session(SessionLocal, session_id, attempt_id):
    inspect_db = SessionLocal()
    try:
        fresh_attempt = SqlAlchemyRuntimeAttemptStore(inspect_db).load_attempt(
            int(session_id),
            int(attempt_id),
        )
        if fresh_attempt is None:
            raise AssertionError(
                f"runtime attempt {attempt_id} missing for session {session_id} in fresh-session inspection"
            )
        return {
            "id": fresh_attempt.attempt_id,
            "status": fresh_attempt.status.value,
            "error_message": fresh_attempt.error_message,
            "lease_token": fresh_attempt.lease_token,
        }
    finally:
        inspect_db.close()


def _primary_task_spec(agent_type, *, order=0, scope=None):
    spec = {
        "agent": agent_type.value,
        "run": True,
        "mission": f"Execute the {agent_type.value} assignment",
        "deliverable": f"Accepted {agent_type.value} output",
        "order": order,
    }
    if scope is not None:
        spec["scope"] = scope
    return spec


def _build_agent(monkeypatch, sync_db, *, call_log, session_factory=None):
    shared_store = _FakeSharedStore()
    short_term = _FakeShortTermService(shared_store)
    memory_services = SimpleNamespace(
        short_term=short_term,
        global_service=object(),
        long_term=object(),
    )

    monkeypatch.setattr(
        orchestrator_module,
        "get_mas_working_memory",
        lambda workflow_id, service=None: shared_store,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "write_shared_fact",
        lambda workflow_id, key, value, service=None: shared_store.put(key, value),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "read_shared_fact",
        lambda workflow_id, key, default=None, service=None: shared_store.get(key, default),
    )
    monkeypatch.setattr(orchestrator_module, "publish_event", _async_noop, raising=False)
    monkeypatch.setattr(
        orchestrator_module, "activate_current_attempt_keepalive", lambda **kwargs: True
    )
    monkeypatch.setattr(
        orchestrator_module, "deactivate_current_attempt_keepalive", lambda **kwargs: True
    )

    agent = object.__new__(OrchestratorAgent)
    agent.agent_type = AgentType.ORCHESTRATOR
    agent.agent_name = "orchestrator"
    agent.logger = logging.getLogger("test.orchestrator.runtime_mainline")
    agent._memory_services = memory_services
    agent._wm_cache = None
    agent._last_audio_route_payload = {}
    agent._orchestration_state = OrchestrationStateAdapter(memory_services=memory_services)
    agent._orchestration_protocol = OrchestrationProtocol()
    agent._context_contract_assembler = SimpleNamespace(
        assemble_agent_context=lambda **kwargs: {},
        build_script_review_boundary_draft=_fake_script_review_boundary,
    )
    if session_factory is not None:
        agent._orchestration_runtime_resume_bootstrap_facade = (
            OrchestrationRuntimeResumeBootstrapFacade(
                orchestration_state=agent._orchestration_state,
                session_factory=session_factory,
            )
        )
        agent._orchestration_runtime_transition_facade = OrchestrationRuntimeTransitionFacade(
            context_contract_assembler=agent._context_contract_assembler,
            orchestration_state=agent._orchestration_state,
            session_factory=session_factory,
        )
    agent._workflow_completion_adapter = SimpleNamespace(
        build_persistence_payload=lambda workflow_id: {
            "final_video_url": "https://example.com/final.mp4"
        },
        publish_completed=_async_return({"final_video_url": "https://example.com/final.mp4"}),
        publish_failed=_async_return({}),
        build_runtime_summary_output=_runtime_summary_stub,
    )
    agent._get_video_audio_capability = lambda: {
        "provider": "",
        "supports_native_audio": False,
        "native_audio_param_name": "generate_audio",
        "native_audio_default_enabled": None,
    }
    agent._update_progress = _async_noop
    agent._prepare_agent_context = _async_identity
    agent._llm_select_candidate_agents = _async_return(
        (
            [
                AgentType.CONCEPT_PLANNER,
                AgentType.SCRIPT_WRITER,
                AgentType.IMAGE_GENERATOR,
            ],
            "test-selection",
        )
    )
    agent._evaluate_runtime_boundary_cycle = _async_return(
        {
            "runtime_decision": {"action": "continue", "reason": "none"},
            "apply_result": {"status": "continue", "reason": "none"},
            "decision_ack": {},
        }
    )
    agent._emit_pre_dispatch_diagnostics = lambda *args, **kwargs: None
    agent._build_execution_queue = lambda task_specs, candidate_agents=None: list(task_specs.keys())
    agent._build_standby_agents = lambda task_specs, candidate_agents=None: []
    agent._store_composer_outputs = lambda *args, **kwargs: None
    agent._should_retry_step = _async_return(False)
    agent._llm_decompose_tasks = _async_return(
        (
            {
                AgentType.CONCEPT_PLANNER: _primary_task_spec(
                    AgentType.CONCEPT_PLANNER, order=0, scope={}
                ),
                AgentType.SCRIPT_WRITER: _primary_task_spec(
                    AgentType.SCRIPT_WRITER, order=1, scope={}
                ),
                AgentType.IMAGE_GENERATOR: _primary_task_spec(
                    AgentType.IMAGE_GENERATOR, order=2, scope={}
                ),
            },
            {},
        )
    )
    agent.agents = {
        AgentType.CONCEPT_PLANNER: _FakeAgent(
            "concept_planner",
            {
                "concept_plan": {"scenes": [{"scene_number": 1}]},
                "orchestration_report": _fake_report(
                    "concept_plan_completed",
                    "project.concept_plan",
                ),
            },
            call_log["concept_planner"],
        ),
        AgentType.SCRIPT_WRITER: _FakeAgent(
            "script_writer",
            {
                "scenes_generated": 1,
                "total_scenes": 1,
                "script_results": {"scripts": {"1": {"script_text": "Scene 1 approved script"}}},
                "orchestration_report": _fake_report(
                    "scene_script_completed",
                    "project.scene_scripts",
                ),
            },
            call_log["script_writer"],
        ),
        AgentType.IMAGE_GENERATOR: _FakeAgent(
            "image_generator",
            {
                "success": True,
                "orchestration_report": _fake_report(
                    "scene_image_completed",
                    "scene_outputs.image",
                ),
            },
            call_log["image_generator"],
        ),
    }
    return agent


def _build_stage_g_agent(monkeypatch, sync_db, *, call_log, llm_responses, session_factory=None):
    shared_store = _FakeSharedStore()
    short_term = _FakeShortTermService(shared_store)
    memory_services = SimpleNamespace(
        short_term=short_term,
        global_service=object(),
        long_term=object(),
    )

    monkeypatch.setattr(
        orchestrator_module,
        "get_mas_working_memory",
        lambda workflow_id, service=None: shared_store,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "write_shared_fact",
        lambda workflow_id, key, value, service=None: shared_store.put(key, value),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "read_shared_fact",
        lambda workflow_id, key, default=None, service=None: shared_store.get(key, default),
    )
    monkeypatch.setattr(orchestrator_module, "publish_event", _async_noop, raising=False)
    monkeypatch.setattr(
        orchestrator_module, "activate_current_attempt_keepalive", lambda **kwargs: True
    )
    monkeypatch.setattr(
        orchestrator_module, "deactivate_current_attempt_keepalive", lambda **kwargs: True
    )

    agent = object.__new__(OrchestratorAgent)
    agent.agent_type = AgentType.ORCHESTRATOR
    agent.agent_name = "orchestrator"
    agent.logger = logging.getLogger("test.orchestrator.stage_g")
    agent.prompt_manager = get_prompt_manager()
    agent._llms = {"plan": _QueuedPlanLLM(llm_responses)}
    agent._memory_services = memory_services
    agent._wm_cache = None
    agent._last_audio_route_payload = {}
    agent._orchestration_state = OrchestrationStateAdapter(memory_services=memory_services)
    agent._orchestration_protocol = OrchestrationProtocol()
    agent._context_contract_assembler = SimpleNamespace(
        assemble_agent_context=lambda **kwargs: {},
        build_script_review_boundary_draft=_fake_script_review_boundary,
    )
    if session_factory is not None:
        agent._orchestration_runtime_resume_bootstrap_facade = (
            OrchestrationRuntimeResumeBootstrapFacade(
                orchestration_state=agent._orchestration_state,
                session_factory=session_factory,
            )
        )
        agent._orchestration_runtime_transition_facade = OrchestrationRuntimeTransitionFacade(
            context_contract_assembler=agent._context_contract_assembler,
            orchestration_state=agent._orchestration_state,
            session_factory=session_factory,
        )
    agent._workflow_completion_adapter = SimpleNamespace(
        build_persistence_payload=lambda workflow_id: {
            "final_video_url": "https://example.com/final.mp4"
        },
        publish_completed=_async_return({"final_video_url": "https://example.com/final.mp4"}),
        publish_failed=_async_return({}),
        build_runtime_summary_output=_runtime_summary_stub,
    )
    agent._get_video_audio_capability = lambda: {
        "provider": "",
        "supports_native_audio": False,
        "native_audio_param_name": "generate_audio",
        "native_audio_default_enabled": None,
    }
    agent._update_progress = _async_noop
    agent._prepare_agent_context = _async_identity
    agent._evaluate_runtime_boundary_cycle = _async_return(
        {
            "runtime_decision": {"action": "continue", "reason": "none"},
            "apply_result": {"status": "continue", "reason": "none"},
            "decision_ack": {},
        }
    )
    agent._emit_pre_dispatch_diagnostics = lambda *args, **kwargs: None
    agent._store_composer_outputs = lambda *args, **kwargs: None
    agent._should_retry_step = _async_return(False)
    agent.agents = {
        AgentType.CONCEPT_PLANNER: _FakeAgent(
            "concept_planner",
            {
                "concept_plan": {"scenes": [{"scene_number": 1}]},
                "orchestration_report": _fake_report(
                    "concept_plan_completed",
                    "project.concept_plan",
                ),
            },
            call_log["concept_planner"],
        ),
        AgentType.SCRIPT_WRITER: _FakeAgent(
            "script_writer",
            {
                "scenes_generated": 1,
                "total_scenes": 1,
                "script_results": {"scripts": {"1": {"script_text": "Scene 1 approved script"}}},
                "orchestration_report": _fake_report(
                    "scene_script_completed",
                    "project.scene_scripts",
                ),
            },
            call_log["script_writer"],
        ),
        AgentType.IMAGE_GENERATOR: _FakeAgent(
            "image_generator",
            {
                "success": True,
                "orchestration_report": _fake_report(
                    "scene_image_completed",
                    "scene_outputs.image",
                ),
            },
            call_log["image_generator"],
        ),
        AgentType.VIDEO_GENERATOR: _FakeAgent(
            "video_generator",
            {
                "success": True,
                "orchestration_report": _fake_report(
                    "scene_video_completed",
                    "scene_outputs.video",
                ),
            },
            [],
        ),
    }
    return agent, shared_store


async def _async_noop(*args, **kwargs):
    return None


def _async_return(value):
    async def _wrapped(*args, **kwargs):
        return value

    return _wrapped


async def _retry_failed_runtime_boundary(**kwargs):
    if (kwargs.get("normalized_report") or {}).get("status") == "failed":
        return {
            "runtime_decision": {
                "action": "retry_current",
                "reason": "retry the failed agent execution",
            },
            "apply_result": {
                "status": "retry",
                "reason": "retry the failed agent execution",
                "replan_count": 1,
            },
            "decision_ack": {},
        }
    return {
        "runtime_decision": {"action": "continue", "reason": "none"},
        "apply_result": {"status": "continue", "reason": "none"},
        "decision_ack": {},
    }


async def _async_identity(*args, **kwargs):
    workflow_data = dict(args[0] if args else kwargs.get("workflow_data") or {})
    return workflow_data


def _build_recording_resume_bootstrap_facade(agent):
    real_facade = agent._orchestration_runtime_resume_bootstrap_facade

    class _RecordingResumeBootstrapFacade:
        def __init__(self):
            self.resolve_calls = []
            self.load_calls = []
            self.consume_calls = []
            self.start_calls = []

        def resolve_runtime_resume_context(self, **kwargs):
            self.resolve_calls.append(dict(kwargs))
            return real_facade.resolve_runtime_resume_context(**kwargs)

        def load_authoritative_resume_task_specs(self, **kwargs):
            self.load_calls.append(dict(kwargs))
            return real_facade.load_authoritative_resume_task_specs(**kwargs)

        def project_script_revision_context(self, **kwargs):
            return real_facade.project_script_revision_context(**kwargs)

        def consume_script_approval_continuation(self, **kwargs):
            self.consume_calls.append(dict(kwargs))
            return real_facade.consume_script_approval_continuation(**kwargs)

        def start_runtime_attempt(self, **kwargs):
            result = real_facade.start_runtime_attempt(**kwargs)
            record = dict(kwargs)
            record.update(
                {
                    "node_key": result.node_key,
                    "attempt_id": result.attempt_id,
                    "trigger_reason": result.trigger_reason,
                    "lease_token": result.lease_token,
                }
            )
            self.start_calls.append(record)
            return result

    return _RecordingResumeBootstrapFacade()


def test_orchestrator_mainline_opens_script_gate_and_stops_before_post_script(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        result = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )
        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        task_snapshot = _load_task_snapshot_from_fresh_session(SessionLocal, task.id)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}

        assert result["status"] == "waiting_gate"
        assert result["session_id"] == session.session_id
        assert runtime_view["status"] == WorkflowSessionStatus.WAITING_GATE.value
        assert nodes_by_key["concept"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.PENDING_GATE.value
        assert runtime_view["active_gate"]["gate_name"] == "script_review"
        assert task_snapshot["status"] == TaskStatus.IN_PROGRESS.value
        assert len(call_log["concept_planner"]) == 1
        assert len(call_log["script_writer"]) == 1
        assert call_log["image_generator"] == []
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_rejects_missing_script_report_before_opening_gate(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        agent.agents[AgentType.SCRIPT_WRITER] = _FakeAgent(
            "script_writer",
            {
                "scenes_generated": 1,
                "total_scenes": 1,
                "script_results": {"scripts": {"1": {"script_text": "Scene 1 unreported script"}}},
            },
            call_log["script_writer"],
        )
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        with pytest.raises(
            AgentError,
            match="Subagent script_writer must return explicit orchestration_report",
        ):
            asyncio.run(
                agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
            )

        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}
        script_attempt = _load_runtime_attempt_snapshot_from_fresh_session(
            SessionLocal,
            session.session_id,
            runtime_view["current_attempt_id"],
        )

        assert runtime_view["status"] == WorkflowSessionStatus.FAILED.value
        assert runtime_view["active_gate"] is None
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.FAILED.value
        assert script_attempt["status"] == WorkflowAttemptStatus.FAILED.value
        script_diagnostic = next(
            item
            for item in (nodes_by_key["script"]["diagnostics"] or [])
            if item.get("code") == "script_stage_failed"
        )
        assert script_diagnostic["reason_code"] == "agent_contract_orchestration_report_missing"
        assert len(call_log["script_writer"]) == 1
        assert call_log["image_generator"] == []
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_runtime_transition_facade_opens_fresh_session(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)
        facade = OrchestrationRuntimeTransitionFacade(
            context_contract_assembler=agent._context_contract_assembler,
            orchestration_state=agent._orchestration_state,
            session_factory=SessionLocal,
        )

        observed = {}

        def _record_loaded_runtime_state(runtime_db, runtime_store, runtime_session):
            observed["db_id"] = id(runtime_db)
            observed["store_type"] = type(runtime_store).__name__
            observed["session_id"] = runtime_session.session_id
            observed["task_id"] = runtime_session.task_id
            return "ok"

        result = facade._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=session.session_id,
            task_id=str(task.task_id),
            action=_record_loaded_runtime_state,
        )

        assert result == "ok"
        assert observed["db_id"] != id(sync_db)
        assert observed["store_type"] == "SqlAlchemyRuntimeAttemptStore"
        assert observed["session_id"] == session.session_id
        assert observed["task_id"] == str(task.task_id)
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_runtime_transition_facade_compensates_published_payload_on_failure(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)
        facade = OrchestrationRuntimeTransitionFacade(
            context_contract_assembler=agent._context_contract_assembler,
            orchestration_state=agent._orchestration_state,
            session_factory=SessionLocal,
        )
        discarded_refs = []
        monkeypatch.setattr(
            transition_facade_module,
            "discard_published_payload",
            discarded_refs.append,
        )

        def _fail_after_publication(runtime_db, _runtime_store, _runtime_session):
            runtime_db.info[facade._PAYLOAD_COMPENSATION_INFO_KEY] = "/tmp/orphan.json"
            raise RuntimeError("gate transition failed")

        with pytest.raises(RuntimeError, match="gate transition failed"):
            facade._run_with_fresh_runtime_control_plane_session(
                runtime_session_id=session.session_id,
                task_id=str(task.task_id),
                action=_fail_after_publication,
            )

        assert discarded_refs == ["/tmp/orphan.json"]
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_runtime_resume_bootstrap_facade_owns_fresh_session(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)
        facade = OrchestrationRuntimeResumeBootstrapFacade(
            orchestration_state=agent._orchestration_state,
            session_factory=SessionLocal,
        )
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        observed_db_ids = []
        original_clear = SqlAlchemyRuntimeAttemptStore.clear_node_diagnostics

        def _record_clear(store, command):
            observed_db_ids.append(("clear", id(store._db)))
            return original_clear(store, command)

        monkeypatch.setattr(
            SqlAlchemyRuntimeAttemptStore,
            "clear_node_diagnostics",
            _record_clear,
        )

        result = facade.start_runtime_attempt(
            runtime_session_id=session.session_id,
            task=_orchestrator_request(task, {"user_prompt": "test prompt"}).task,
            current_agent_type=AgentType.CONCEPT_PLANNER,
            workflow_state_id=str(task.task_id),
            task_specs={
                AgentType.CONCEPT_PLANNER: _primary_task_spec(AgentType.CONCEPT_PLANNER, scope={}),
            },
            conditional_task_specs={},
            candidate_agents=[AgentType.CONCEPT_PLANNER],
            script_trigger_reason="initial",
            script_requested_by="system",
            resume_anchor_agent=None,
        )

        assert result.node_key == "concept"
        assert result.attempt_id is not None
        assert result.lease_token
        assert observed_db_ids
        assert len({db_id for _name, db_id in observed_db_ids}) == 1
        assert id(sync_db) not in {db_id for _name, db_id in observed_db_ids}

        with pytest.raises(
            OrchestrationRuntimeResumeBootstrapError,
            match="Runtime node mapping is missing",
        ):
            facade.start_runtime_attempt(
                runtime_session_id=session.session_id,
                task=_orchestrator_request(task, {"user_prompt": "test prompt"}).task,
                current_agent_type=AgentType.SERIES_PLANNER,
                workflow_state_id=str(task.task_id),
                task_specs={
                    AgentType.SERIES_PLANNER: _primary_task_spec(
                        AgentType.SERIES_PLANNER, scope={}
                    ),
                },
                conditional_task_specs={},
                candidate_agents=[AgentType.SERIES_PLANNER],
                script_trigger_reason="initial",
                script_requested_by="system",
                resume_anchor_agent=None,
            )
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_runtime_resume_bootstrap_rolls_back_attempt_when_continuation_bind_fails(
    monkeypatch,
):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)
        facade = OrchestrationRuntimeResumeBootstrapFacade(
            orchestration_state=agent._orchestration_state,
            session_factory=SessionLocal,
        )
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        def _fail_bind(self, **kwargs):
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation="bind_attempt_continuation",
                message="injected continuation conflict",
            )

        monkeypatch.setattr(RuntimeAttemptControlPlane, "bind_continuation", _fail_bind)

        with pytest.raises(RuntimeStoreError, match="injected continuation conflict"):
            facade.start_runtime_attempt(
                runtime_session_id=session.session_id,
                task=_orchestrator_request(task, {"user_prompt": "test prompt"}).task,
                current_agent_type=AgentType.CONCEPT_PLANNER,
                workflow_state_id=str(task.task_id),
                task_specs={
                    AgentType.CONCEPT_PLANNER: _primary_task_spec(
                        AgentType.CONCEPT_PLANNER, scope={}
                    ),
                },
                conditional_task_specs={},
                candidate_agents=[AgentType.CONCEPT_PLANNER],
                script_trigger_reason="initial",
                script_requested_by="system",
                resume_anchor_agent=None,
            )

        sync_db.expire_all()
        store = SqlAlchemyRuntimeAttemptStore(sync_db)
        persisted_session = store.load_session(session.session_id)
        persisted_node = store.load_node(session.session_id, "concept")
        assert persisted_session is not None
        assert persisted_node is not None
        persisted_task = sync_db.get(Task, task.id)
        assert persisted_task is not None
        assert sync_db.query(WorkflowNodeAttempt).count() == 0
        assert persisted_session.status is WorkflowSessionStatus.QUEUED
        assert persisted_session.current_attempt_id is None
        assert persisted_node.status is WorkflowNodeStatus.QUEUED
        assert persisted_task.status == TaskStatus.PENDING.value
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_routes_attempt_completion_through_fresh_session_helper(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        completion_calls = []

        class _StubRuntimeTransitions:
            def complete_runtime_attempt(self, **kwargs):
                completion_calls.append(dict(kwargs))

            def open_script_review_gate(self, **kwargs):
                return {
                    "status": "waiting_gate",
                    "session_id": session.session_id,
                    "gate_id": 1,
                    "node_key": "script",
                }

        agent._orchestration_runtime_transition_facade = _StubRuntimeTransitions()

        result = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )

        assert result["status"] == "waiting_gate"
        assert completion_calls
        assert completion_calls[0]["runtime_session_id"] == session.session_id
        assert completion_calls[0]["node_key"] == "concept"
        assert completion_calls[0]["node_status"] == WorkflowNodeStatus.COMPLETED.value
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_routes_script_gate_transition_through_runtime_transition_facade(
    monkeypatch,
):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        completion_calls = []
        gate_calls = []

        class _StubRuntimeTransitions:
            def complete_runtime_attempt(self, **kwargs):
                completion_calls.append(dict(kwargs))

            def open_script_review_gate(self, **kwargs):
                gate_calls.append(dict(kwargs))
                return {
                    "status": "waiting_gate",
                    "session_id": session.session_id,
                    "gate_id": 1,
                    "node_key": "script",
                }

        agent._orchestration_runtime_transition_facade = _StubRuntimeTransitions()

        result = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )

        assert result["status"] == "waiting_gate"
        assert completion_calls
        assert gate_calls
        assert gate_calls[0]["runtime_session_id"] == session.session_id
        assert gate_calls[0]["task_id"] == str(task.task_id)
        assert gate_calls[0]["script_attempt_id"] >= 1
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_routes_attempt_bootstrap_through_resume_facade(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        activate_calls = []
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        agent._orchestration_runtime_resume_bootstrap_facade = (
            _build_recording_resume_bootstrap_facade(agent)
        )
        monkeypatch.setattr(
            orchestrator_module,
            "activate_current_attempt_keepalive",
            lambda **kwargs: activate_calls.append(dict(kwargs)) or True,
        )

        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        completion_calls = []
        gate_calls = []

        class _StubRuntimeTransitions:
            def complete_runtime_attempt(self, **kwargs):
                completion_calls.append(dict(kwargs))

            def open_script_review_gate(self, **kwargs):
                gate_calls.append(dict(kwargs))
                return {
                    "status": "waiting_gate",
                    "session_id": session.session_id,
                    "gate_id": 1,
                    "node_key": "script",
                }

        agent._orchestration_runtime_transition_facade = _StubRuntimeTransitions()

        result = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )

        start_calls = agent._orchestration_runtime_resume_bootstrap_facade.start_calls
        assert result["status"] == "waiting_gate"
        assert len(start_calls) == 2
        assert len(activate_calls) == 2
        assert start_calls[0]["current_agent_type"] == AgentType.CONCEPT_PLANNER
        assert start_calls[1]["current_agent_type"] == AgentType.SCRIPT_WRITER
        assert activate_calls[0]["lease_token"] == start_calls[0]["lease_token"]
        assert activate_calls[1]["lease_token"] == start_calls[1]["lease_token"]
        assert completion_calls[0]["lease_token"] == start_calls[0]["lease_token"]
        assert gate_calls[0]["lease_token"] == start_calls[1]["lease_token"]
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_fails_when_execution_host_keepalive_is_unavailable(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        agent._orchestration_runtime_resume_bootstrap_facade = (
            _build_recording_resume_bootstrap_facade(agent)
        )
        monkeypatch.setattr(
            orchestrator_module, "activate_current_attempt_keepalive", lambda **kwargs: False
        )

        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        with pytest.raises(AgentError, match="Execution host keepalive unavailable"):
            asyncio.run(
                agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
            )

        fresh_task = _load_task_snapshot_from_fresh_session(SessionLocal, task.id)
        fresh_session = _load_runtime_session_snapshot_from_fresh_session(
            SessionLocal, session.session_id
        )
        node = _load_runtime_node_snapshot_from_fresh_session(
            SessionLocal, session.session_id, "concept"
        )
        keepalive_diagnostic = next(
            item
            for item in (node["diagnostics"] or [])
            if item.get("code") == "execution_host_keepalive"
        )

        assert call_log["concept_planner"] == []
        assert fresh_session["status"] == WorkflowSessionStatus.FAILED.value
        assert fresh_task["status"] == TaskStatus.FAILED.value
        assert node["status"] == WorkflowNodeStatus.FAILED.value
        assert keepalive_diagnostic["state"] == "activation_failed"
        assert keepalive_diagnostic["reason_code"] == "keepalive_unavailable"
        assert len(agent._orchestration_runtime_resume_bootstrap_facade.start_calls) == 1
        assert (
            agent._orchestration_runtime_resume_bootstrap_facade.start_calls[0][
                "current_agent_type"
            ]
            == AgentType.CONCEPT_PLANNER
        )
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_fails_active_attempt_when_runtime_decision_fails(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        agent._orchestration_runtime_resume_bootstrap_facade = (
            _build_recording_resume_bootstrap_facade(agent)
        )

        async def _raise_runtime_decision_failure(*args, **kwargs):
            raise AgentError("Runtime replan missing action")

        agent._evaluate_runtime_boundary_cycle = _raise_runtime_decision_failure

        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        with pytest.raises(AgentError, match="Runtime replan missing action"):
            asyncio.run(
                agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
            )

        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        node = _load_runtime_node_snapshot_from_fresh_session(
            SessionLocal, session.session_id, "concept"
        )
        task_snapshot = _load_task_snapshot_from_fresh_session(SessionLocal, task.id)
        attempt_snapshot = _load_runtime_attempt_snapshot_from_fresh_session(
            SessionLocal,
            session.session_id,
            runtime_view["current_attempt_id"],
        )
        stage_diagnostic = next(
            item
            for item in (node["diagnostics"] or [])
            if item.get("code") == "concept_stage_failed"
        )

        assert runtime_view["status"] == WorkflowSessionStatus.FAILED.value
        assert "Runtime replan missing action" in str(runtime_view["error_message"] or "")
        assert "active execution lease" not in str(runtime_view["error_message"] or "")
        assert task_snapshot["status"] == TaskStatus.FAILED.value
        assert node["status"] == WorkflowNodeStatus.FAILED.value
        assert stage_diagnostic["message"] == "Runtime replan missing action"
        assert "state" not in stage_diagnostic
        assert "reason_code" not in stage_diagnostic
        assert attempt_snapshot["status"] == WorkflowAttemptStatus.FAILED.value
        assert attempt_snapshot["lease_token"] in (None, "")
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_runtime_decision_prompt_requires_explicit_continue_action(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.agent_name = "orchestrator"
    agent.logger = logging.getLogger("test.orchestrator.runtime_decision.prompt_contract")
    agent.prompt_manager = get_prompt_manager()
    agent.get_system_instructions = lambda: {"primary_role": "工作流编排器"}
    captured = {}

    async def _capture_chat_completion(*, messages, **kwargs):
        captured["messages"] = list(messages)
        captured["kwargs"] = dict(kwargs)
        return {"content": json.dumps({"action": "continue", "reason": "all_have_audio"})}

    agent.get_llm = lambda role: SimpleNamespace(chat_completion=_capture_chat_completion)

    decision = asyncio.run(
        agent._llm_decide_runtime_decision(
            workflow_state_id="wf-runtime-contract-1",
            current_agent=AgentType.VIDEO_GENERATOR,
            standby_agents=[AgentType.AUDIO_GENERATOR],
            report={
                "status": "completed",
                "boundary_event": "scene_video_completed",
            },
            gate_events=[
                {
                    "gate_name": "workflow_video_audio_delivery",
                    "result": "pass",
                    "reason_code": "all_have_audio",
                    "recommended_action": "continue",
                    "facts": {"all_have_audio": True},
                }
            ],
            replan_count=0,
            max_replans=2,
        )
    )

    system_content = captured["messages"][0]["content"]

    assert decision["action"] == "continue"
    assert captured["kwargs"]["response_format"] == {"type": "json_object"}
    assert "必须包含规范字符串 action 与 reason" in system_content
    assert "partial 可选择 retry_current" in system_content
    assert "failed 可选择 retry_current" in system_content


def test_candidate_selection_prompt_includes_mainline_and_audio_optionality_priors(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.agent_name = "orchestrator"
    agent.logger = logging.getLogger("test.orchestrator.candidate_selection.prompt_contract")
    agent.prompt_manager = get_prompt_manager()
    agent.get_system_instructions = lambda: {"primary_role": "工作流编排器"}
    agent.agents = {
        AgentType.CONCEPT_PLANNER: object(),
        AgentType.SCRIPT_WRITER: object(),
        AgentType.VOICE_SYNTHESIZER: object(),
        AgentType.IMAGE_GENERATOR: object(),
        AgentType.VIDEO_GENERATOR: object(),
        AgentType.AUDIO_GENERATOR: object(),
        AgentType.VIDEO_COMPOSER: object(),
        AgentType.QUALITY_CHECKER: object(),
    }
    captured = {}

    async def _capture_chat_completion(*, messages, **kwargs):
        captured["messages"] = list(messages)
        captured["kwargs"] = dict(kwargs)
        return {
            "content": json.dumps(
                {
                    "candidate_agents": [
                        AgentType.CONCEPT_PLANNER.value,
                        AgentType.SCRIPT_WRITER.value,
                        AgentType.IMAGE_GENERATOR.value,
                        AgentType.VIDEO_GENERATOR.value,
                        AgentType.VIDEO_COMPOSER.value,
                        AgentType.QUALITY_CHECKER.value,
                    ],
                    "selection_rationale": "test",
                }
            )
        }

    agent.get_llm = lambda role: SimpleNamespace(chat_completion=_capture_chat_completion)

    selected, rationale = asyncio.run(
        agent._llm_select_candidate_agents(
            workflow_data={
                "user_prompt": "生成一个5秒的测试短视频，简单蓝色主题即可",
                "duration": 5,
                "resolution": "1280x720",
                "target_resolution": "1280x720",
                "audio_contract": {
                    "allow_silence": True,
                    "need_voiceover": False,
                    "need_global_bgm": False,
                },
                "audio_capability": {
                    "provider": "doubao",
                    "supports_native_audio": True,
                    "native_audio_default_enabled": True,
                },
            },
            workflow_id="wf-candidate-contract-1",
        )
    )

    system_content = captured["messages"][0]["content"]
    user_content = captured["messages"][1]["content"]

    assert [agent_type.value for agent_type in selected] == [
        AgentType.CONCEPT_PLANNER.value,
        AgentType.SCRIPT_WRITER.value,
        AgentType.IMAGE_GENERATOR.value,
        AgentType.VIDEO_GENERATOR.value,
        AgentType.VIDEO_COMPOSER.value,
        AgentType.QUALITY_CHECKER.value,
    ]
    assert rationale == "test"
    assert captured["kwargs"]["response_format"] == {"type": "json_object"}
    assert "最小可执行候选集" in system_content
    assert "当前视频模型是否支持同步生成声音" in system_content
    assert "不能省略 script_writer" in system_content
    assert "只影响 voice_synthesizer / audio_generator 是否可省略" in user_content
    assert "必须同时保留 script_writer" in user_content


def test_orchestrator_planning_prompts_do_not_expose_workflow_state_id(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.agent_name = "orchestrator"
    agent.logger = logging.getLogger("test.orchestrator.planning_prompt.runtime_identity")
    agent.prompt_manager = get_prompt_manager()
    agent.get_system_instructions = lambda: {"primary_role": "工作流编排器"}
    agent.agents = {
        AgentType.VIDEO_GENERATOR: object(),
        AgentType.VIDEO_COMPOSER: object(),
    }
    captured_user_messages = []
    captured_kwargs = []

    async def _capture_chat_completion(*, messages, **kwargs):
        captured_user_messages.append(messages[1]["content"])
        captured_kwargs.append(dict(kwargs))
        if len(captured_user_messages) == 1:
            return {
                "content": json.dumps(
                    {
                        "candidate_agents": [
                            AgentType.VIDEO_GENERATOR.value,
                            AgentType.VIDEO_COMPOSER.value,
                        ],
                        "selection_rationale": "native audio is enough",
                    },
                    ensure_ascii=False,
                )
            }
        return {
            "content": json.dumps(
                {
                    "agents": [
                        {
                            "agent": AgentType.VIDEO_GENERATOR.value,
                            "run": True,
                            "mission": "generate scene video clips",
                            "deliverable": "scene video clips",
                            "constraints": [],
                            "order": 0,
                            "runtime_hints": {"generate_audio": True},
                        },
                        {
                            "agent": AgentType.VIDEO_COMPOSER.value,
                            "run": True,
                            "mission": "compose the final video",
                            "deliverable": "final composed video",
                            "constraints": [],
                            "order": 1,
                            "runtime_hints": {},
                        },
                    ],
                },
                ensure_ascii=False,
            )
        }

    agent.get_llm = lambda role: SimpleNamespace(chat_completion=_capture_chat_completion)

    workflow_id = "wf-planning-boundary-secret"
    workflow_data = {
        "user_prompt": "make a short video",
        "audio_contract": {
            "allow_silence": True,
            "need_voiceover": False,
            "workflow_state_id": workflow_id,
        },
        "audio_capability": {"supports_native_audio": True},
    }

    selected, _ = asyncio.run(
        agent._llm_select_candidate_agents(
            workflow_data=workflow_data,
            workflow_id=workflow_id,
        )
    )
    task_specs, _ = asyncio.run(
        agent._llm_decompose_tasks(
            workflow_data,
            workflow_id,
            candidate_agents=selected,
        )
    )

    assert selected == [AgentType.VIDEO_GENERATOR, AgentType.VIDEO_COMPOSER]
    assert task_specs[AgentType.VIDEO_GENERATOR]["runtime_hints"] == {"generate_audio": True}
    assert len(captured_user_messages) == 2
    assert [call["response_format"] for call in captured_kwargs] == [
        {"type": "json_object"},
        {"type": "json_object"},
    ]
    rendered_planning_text = "\n".join(captured_user_messages)
    assert "workflow_state_id" not in rendered_planning_text
    assert workflow_id not in rendered_planning_text


def test_orchestrator_mainline_resumes_after_script_approve_without_kernel(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        planning_calls = {"select": 0, "decompose": 0}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)

        async def _count_select(*args, **kwargs):
            planning_calls["select"] += 1
            return (
                [
                    AgentType.CONCEPT_PLANNER,
                    AgentType.SCRIPT_WRITER,
                    AgentType.IMAGE_GENERATOR,
                ],
                "test-selection",
            )

        async def _count_decompose(*args, **kwargs):
            planning_calls["decompose"] += 1
            return (
                {
                    AgentType.CONCEPT_PLANNER: _primary_task_spec(
                        AgentType.CONCEPT_PLANNER, order=0, scope={}
                    ),
                    AgentType.SCRIPT_WRITER: _primary_task_spec(
                        AgentType.SCRIPT_WRITER, order=1, scope={}
                    ),
                    AgentType.IMAGE_GENERATOR: _primary_task_spec(
                        AgentType.IMAGE_GENERATOR, order=2, scope={}
                    ),
                },
                {},
            )

        agent._llm_select_candidate_agents = _count_select
        agent._llm_decompose_tasks = _count_decompose
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)
        first = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )
        assert first["status"] == "waiting_gate"

        _submit_script_decision(
            sync_db,
            session_id=session.session_id,
            action="approve",
            feedback_text="looks good",
        )
        agent._memory_services.short_term._shared_store.clear()
        agent._orchestration_runtime_resume_bootstrap_facade = (
            _build_recording_resume_bootstrap_facade(agent)
        )
        published_runtime_states = []
        published_kwargs = []

        async def _publish_after_terminal_commit(**kwargs):
            published_runtime_states.append(
                _load_runtime_view_from_fresh_session(SessionLocal, task.id)["status"]
            )
            published_kwargs.append(dict(kwargs))
            return {"final_video_url": "https://example.com/final.mp4"}

        agent._workflow_completion_adapter.publish_completed = _publish_after_terminal_commit

        second = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )
        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        fresh_task = _load_task_snapshot_from_fresh_session(SessionLocal, task.id)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}

        assert second["status"] == "completed"
        assert published_runtime_states == [WorkflowSessionStatus.COMPLETED.value]
        assert published_kwargs[0]["runtime_session_id"] == session.session_id
        assert published_kwargs[0]["runtime_terminal_committed"] is True
        assert runtime_view["status"] == WorkflowSessionStatus.COMPLETED.value
        assert fresh_task["status"] == TaskStatus.COMPLETED.value
        assert nodes_by_key["concept"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["image"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert len(agent._orchestration_runtime_resume_bootstrap_facade.load_calls) == 1
        assert (
            agent._orchestration_runtime_resume_bootstrap_facade.load_calls[0]["resume_action"]
            == "approve"
        )
        assert planning_calls == {"select": 1, "decompose": 1}
        assert len(agent._orchestration_runtime_resume_bootstrap_facade.consume_calls) == 1
        assert (
            agent._orchestration_runtime_resume_bootstrap_facade.consume_calls[0][
                "runtime_session_id"
            ]
            == session.session_id
        )
        assert len(call_log["concept_planner"]) == 1
        assert len(call_log["script_writer"]) == 1
        assert len(call_log["image_generator"]) == 1
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_resumes_from_runtime_checkpoint_via_resume_facade(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        planning_calls = {"select": 0, "decompose": 0}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        agent._orchestration_runtime_resume_bootstrap_facade = (
            _build_recording_resume_bootstrap_facade(agent)
        )

        async def _count_select(*args, **kwargs):
            planning_calls["select"] += 1
            return ([AgentType.SCRIPT_WRITER], "unexpected-selection")

        async def _count_decompose(*args, **kwargs):
            planning_calls["decompose"] += 1
            return (
                {AgentType.SCRIPT_WRITER: _primary_task_spec(AgentType.SCRIPT_WRITER, scope={})},
                {},
            )

        agent._llm_select_candidate_agents = _count_select
        agent._llm_decompose_tasks = _count_decompose

        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)
        store, attempt = _start_runtime_checkpoint_attempt(
            sync_db, session.session_id, node_key="script"
        )
        continuation_checkpoint = agent._orchestration_state.build_continuation_checkpoint(
            task_specs={
                AgentType.SCRIPT_WRITER: _primary_task_spec(AgentType.SCRIPT_WRITER, scope={}),
            },
            conditional_task_specs={},
            candidate_agents=[AgentType.SCRIPT_WRITER],
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            node_key="script",
            attempt_id=attempt.attempt_id,
            decision_id=None,
        )
        RuntimeAttemptControlPlane(store).bind_continuation(
            session_id=session.session_id,
            attempt_id=attempt.attempt_id,
            continuation_checkpoint=JsonObjectPayload.from_mapping(
                continuation_checkpoint,
                field_path="test.runtime_checkpoint",
            ),
        )
        RuntimeSessionControlPlane(store).mark_resuming(session.session_id)
        sync_db.commit()

        result = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )

        resolve_calls = agent._orchestration_runtime_resume_bootstrap_facade.resolve_calls
        start_calls = agent._orchestration_runtime_resume_bootstrap_facade.start_calls
        assert result["status"] == "waiting_gate"
        assert len(resolve_calls) == 1
        assert len(start_calls) == 1
        assert start_calls[0]["current_agent_type"] == AgentType.SCRIPT_WRITER
        assert start_calls[0]["trigger_reason"] == "resume"
        assert planning_calls == {"select": 0, "decompose": 0}
        assert len(call_log["concept_planner"]) == 0
        assert len(call_log["script_writer"]) == 1
        assert len(call_log["image_generator"]) == 0
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_fails_closed_when_runtime_script_boundary_missing(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        agent._prepare_agent_context = OrchestratorAgent._prepare_agent_context.__get__(
            agent, OrchestratorAgent
        )
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        first = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )
        assert first["status"] == "waiting_gate"

        real_assembler = ContextContractAssembler(agent._memory_services)
        agent._context_contract_assembler.assemble_agent_context = (
            real_assembler.assemble_agent_context
        )
        _submit_script_decision(
            sync_db,
            session_id=session.session_id,
            action="approve",
            feedback_text="looks good",
        )
        session_row = sync_db.get(WorkflowSession, session.session_id)
        assert session_row is not None
        session_row.input_payload = {}
        sync_db.commit()

        with pytest.raises(AgentError, match="script_prerequisite_not_satisfied"):
            asyncio.run(
                agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
            )

        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        assert runtime_view["status"] == WorkflowSessionStatus.FAILED.value
        assert len(call_log["image_generator"]) == 0
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_blocks_script_consumers_before_dispatch_when_queue_is_misordered(
    monkeypatch,
):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        task = _create_task(sync_db)
        _create_runtime_session(sync_db, task)

        agent._llm_select_candidate_agents = _async_return(
            (
                [
                    AgentType.CONCEPT_PLANNER,
                    AgentType.IMAGE_GENERATOR,
                    AgentType.SCRIPT_WRITER,
                ],
                "misordered-selection",
            )
        )
        agent._llm_decompose_tasks = _async_return(
            (
                {
                    AgentType.CONCEPT_PLANNER: _primary_task_spec(
                        AgentType.CONCEPT_PLANNER, order=0, scope={}
                    ),
                    AgentType.IMAGE_GENERATOR: _primary_task_spec(
                        AgentType.IMAGE_GENERATOR, order=1, scope={}
                    ),
                    AgentType.SCRIPT_WRITER: _primary_task_spec(
                        AgentType.SCRIPT_WRITER, order=2, scope={}
                    ),
                },
                {},
            )
        )
        agent._build_execution_queue = lambda task_specs, candidate_agents=None: [
            AgentType.CONCEPT_PLANNER,
            AgentType.IMAGE_GENERATOR,
            AgentType.SCRIPT_WRITER,
        ]

        with pytest.raises(AgentError, match="script_prerequisite_not_satisfied"):
            asyncio.run(
                agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
            )

        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        assert runtime_view["status"] == WorkflowSessionStatus.FAILED.value
        assert len(call_log["concept_planner"]) == 1
        assert len(call_log["image_generator"]) == 0
        assert len(call_log["script_writer"]) == 0
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_revise_reopens_script_gate_via_concept_and_script(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        planning_calls = {"select": 0, "decompose": 0}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)

        async def _count_select(*args, **kwargs):
            planning_calls["select"] += 1
            return (
                [
                    AgentType.CONCEPT_PLANNER,
                    AgentType.SCRIPT_WRITER,
                    AgentType.IMAGE_GENERATOR,
                ],
                "test-selection",
            )

        async def _count_decompose(*args, **kwargs):
            planning_calls["decompose"] += 1
            return (
                {
                    AgentType.CONCEPT_PLANNER: _primary_task_spec(
                        AgentType.CONCEPT_PLANNER, order=0, scope={}
                    ),
                    AgentType.SCRIPT_WRITER: _primary_task_spec(
                        AgentType.SCRIPT_WRITER, order=1, scope={}
                    ),
                    AgentType.IMAGE_GENERATOR: _primary_task_spec(
                        AgentType.IMAGE_GENERATOR, order=2, scope={}
                    ),
                },
                {},
            )

        agent._llm_select_candidate_agents = _count_select
        agent._llm_decompose_tasks = _count_decompose
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        first = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )
        assert first["status"] == "waiting_gate"

        _submit_script_decision(
            sync_db,
            session_id=session.session_id,
            action="revise",
            feedback_text="tighten pacing",
            structured_constraints={"keep_character": True},
        )
        agent._memory_services.short_term._shared_store.clear()

        second = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )
        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}

        assert second["status"] == "waiting_gate"
        assert runtime_view["status"] == WorkflowSessionStatus.WAITING_GATE.value
        assert nodes_by_key["concept"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.PENDING_GATE.value
        assert planning_calls == {"select": 1, "decompose": 1}
        assert len(call_log["concept_planner"]) == 1
        assert len(call_log["script_writer"]) == 2
        assert call_log["image_generator"] == []
        assert (
            agent._memory_services.short_term._shared_store["scene_overview"]["scenes"][0][
                "visual_description"
            ]
            == "stub scene"
        )
        assert (
            call_log["script_writer"][1]["input_data"]["script_review_contract"]["action"]
            == "revise"
        )
        assert (
            call_log["script_writer"][1]["input_data"]["script_review_contract"]["feedback_text"]
            == "tighten pacing"
        )
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_replan_reopens_script_gate_with_review_contract(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        planning_calls = {"select": 0, "decompose": 0}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)

        async def _count_select(*args, **kwargs):
            planning_calls["select"] += 1
            return (
                [
                    AgentType.CONCEPT_PLANNER,
                    AgentType.SCRIPT_WRITER,
                    AgentType.IMAGE_GENERATOR,
                ],
                "test-selection",
            )

        async def _count_decompose(*args, **kwargs):
            planning_calls["decompose"] += 1
            return (
                {
                    AgentType.CONCEPT_PLANNER: _primary_task_spec(
                        AgentType.CONCEPT_PLANNER, order=0, scope={}
                    ),
                    AgentType.SCRIPT_WRITER: _primary_task_spec(
                        AgentType.SCRIPT_WRITER, order=1, scope={}
                    ),
                    AgentType.IMAGE_GENERATOR: _primary_task_spec(
                        AgentType.IMAGE_GENERATOR, order=2, scope={}
                    ),
                },
                {},
            )

        agent._llm_select_candidate_agents = _count_select
        agent._llm_decompose_tasks = _count_decompose
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        first = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )
        assert first["status"] == "waiting_gate"

        _submit_script_decision(
            sync_db,
            session_id=session.session_id,
            action="replan",
            feedback_text="change structure",
            structured_constraints={"new_arc": "stronger opening"},
        )
        agent._memory_services.short_term._shared_store.clear()

        second = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )
        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}

        assert second["status"] == "waiting_gate"
        assert runtime_view["status"] == WorkflowSessionStatus.WAITING_GATE.value
        assert nodes_by_key["concept"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.PENDING_GATE.value
        assert planning_calls == {"select": 2, "decompose": 2}
        assert len(call_log["concept_planner"]) == 2
        assert len(call_log["script_writer"]) == 2
        assert call_log["image_generator"] == []
        assert (
            call_log["concept_planner"][1]["input_data"]["script_review_contract"]["action"]
            == "replan"
        )
        assert call_log["concept_planner"][1]["input_data"]["script_review_contract"][
            "structured_constraints"
        ] == {"new_arc": "stronger opening"}
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_script_retry_reopens_review_gate(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        boundary_calls = []

        async def _record_runtime_boundary(**kwargs):
            boundary_calls.append(dict(kwargs))
            if (kwargs.get("normalized_report") or {}).get("status") == "failed":
                return {
                    "runtime_decision": {
                        "action": "retry_current",
                        "reason": "retry the failed script execution",
                    },
                    "apply_result": {
                        "status": "retry",
                        "reason": "retry the failed script execution",
                        "replan_count": 1,
                    },
                    "decision_ack": {},
                }
            return {
                "runtime_decision": {"action": "continue", "reason": "none"},
                "apply_result": {"status": "continue", "reason": "none"},
                "decision_ack": {},
            }

        agent._evaluate_runtime_boundary_cycle = _record_runtime_boundary
        agent.agents[AgentType.SCRIPT_WRITER] = _FlakyAgent(
            "script_writer",
            first_error=RuntimeError("temporary timeout"),
            success_output={
                "scenes_generated": 1,
                "total_scenes": 1,
                "script_results": {"scripts": {"1": {"script_text": "Scene 1 approved script"}}},
                "orchestration_report": _fake_report(
                    "scene_script_completed",
                    "project.scene_scripts",
                ),
            },
            calls=call_log["script_writer"],
        )
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        result = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )
        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}

        assert result["status"] == "waiting_gate"
        assert result["session_id"] == session.session_id
        assert runtime_view["status"] == WorkflowSessionStatus.WAITING_GATE.value
        assert runtime_view["active_gate"]["gate_name"] == "script_review"
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.PENDING_GATE.value
        assert len(call_log["concept_planner"]) == 1
        assert len(call_log["script_writer"]) == 2
        assert call_log["image_generator"] == []
        assert [call["current_agent"] for call in boundary_calls] == [
            AgentType.CONCEPT_PLANNER,
            AgentType.SCRIPT_WRITER,
            AgentType.SCRIPT_WRITER,
        ]
        assert (
            boundary_calls[-1]["agent_result"]
            .require_orchestration_report()
            .to_dict()["boundary_event"]
            == "scene_script_completed"
        )
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_malformed_retry_report_fails_retry_attempt(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        agent._evaluate_runtime_boundary_cycle = _retry_failed_runtime_boundary
        malformed_report = _fake_report(
            "concept_plan_completed",
            "project.concept_plan",
        )
        malformed_report["gate_triggers"] = "not-a-list"
        agent.agents[AgentType.CONCEPT_PLANNER] = _FlakyAgent(
            "concept_planner",
            first_error=RuntimeError("temporary concept failure"),
            success_output={
                "concept_plan": {"scenes": [{"scene_number": 1}]},
                "orchestration_report": malformed_report,
            },
            calls=call_log["concept_planner"],
        )
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        with pytest.raises(
            AgentError,
            match="orchestration_report field gate_triggers must be list",
        ):
            asyncio.run(
                agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
            )

        inspect_db = SessionLocal()
        try:
            attempts = (
                inspect_db.query(WorkflowNodeAttempt)
                .filter(WorkflowNodeAttempt.session_id == session.session_id)
                .order_by(WorkflowNodeAttempt.attempt_no.asc())
                .all()
            )
            runtime_model = RuntimeReadModelService(
                SqlAlchemyRuntimeAttemptStore(inspect_db)
            ).load_for_task(str(task.task_id))
            assert runtime_model is not None
            runtime_view = RuntimeReadModelPresenter.to_payload(runtime_model).to_dict()
            assert [attempt.status for attempt in attempts] == [
                WorkflowAttemptStatus.FAILED.value,
                WorkflowAttemptStatus.FAILED.value,
            ]
            assert runtime_view["status"] == WorkflowSessionStatus.FAILED.value
            assert runtime_view["active_gate"] is None
        finally:
            inspect_db.close()

        assert len(call_log["concept_planner"]) == 2
        assert call_log["script_writer"] == []
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_retry_input_failure_fails_retry_attempt(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        agent._evaluate_runtime_boundary_cycle = _retry_failed_runtime_boundary
        agent.agents[AgentType.CONCEPT_PLANNER] = _FlakyAgent(
            "concept_planner",
            first_error=RuntimeError("temporary concept failure"),
            success_output={
                "concept_plan": {"scenes": [{"scene_number": 1}]},
                "orchestration_report": _fake_report(
                    "concept_plan_completed",
                    "project.concept_plan",
                ),
            },
            calls=call_log["concept_planner"],
        )
        original_prepare = agent._prepare_scheduled_agent_input
        prepare_calls = []

        async def _prepare_with_retry_failure(**kwargs):
            prepare_calls.append(kwargs["agent_type"])
            if len(prepare_calls) == 2:
                raise AgentError("retry input contract unavailable")
            return await original_prepare(**kwargs)

        agent._prepare_scheduled_agent_input = _prepare_with_retry_failure
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        with pytest.raises(AgentError, match="retry input contract unavailable"):
            asyncio.run(
                agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
            )

        inspect_db = SessionLocal()
        try:
            attempts = (
                inspect_db.query(WorkflowNodeAttempt)
                .filter(WorkflowNodeAttempt.session_id == session.session_id)
                .order_by(WorkflowNodeAttempt.attempt_no.asc())
                .all()
            )
            assert [attempt.status for attempt in attempts] == [
                WorkflowAttemptStatus.FAILED.value,
                WorkflowAttemptStatus.FAILED.value,
            ]
        finally:
            inspect_db.close()

        assert prepare_calls == [
            AgentType.CONCEPT_PLANNER,
            AgentType.CONCEPT_PLANNER,
        ]
        assert len(call_log["concept_planner"]) == 1
        assert call_log["script_writer"] == []
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_stage_g_execute_impl_wires_candidate_selection_to_queue(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        selection_payload = {
            "candidate_agents": [
                AgentType.CONCEPT_PLANNER.value,
                AgentType.SCRIPT_WRITER.value,
                AgentType.VIDEO_GENERATOR.value,
            ],
            "selection_rationale": "video generation may be needed later, but not immediately",
        }
        decomposition_payload = {
            "agents": [
                {
                    "agent": AgentType.CONCEPT_PLANNER.value,
                    "run": True,
                    "mission": "plan the creative concept for the trailer",
                    "deliverable": "concept plan",
                    "constraints": [],
                    "order": 0,
                    "runtime_hints": {},
                },
                {
                    "agent": AgentType.SCRIPT_WRITER.value,
                    "run": True,
                    "mission": "expand the concept into scene scripts",
                    "deliverable": "scene scripts",
                    "constraints": [],
                    "order": 1,
                    "runtime_hints": {},
                },
                {
                    "agent": AgentType.VIDEO_GENERATOR.value,
                    "run": False,
                    "mission": "generate scene videos when downstream materials are ready",
                    "deliverable": "scene video fragments",
                    "constraints": [],
                    "order": 2,
                    "runtime_hints": {"generate_audio": True},
                },
            ],
        }
        agent, shared_store = _build_stage_g_agent(
            monkeypatch,
            sync_db,
            call_log=call_log,
            llm_responses=[
                {"content": json.dumps(selection_payload, ensure_ascii=False)},
                {"content": json.dumps(decomposition_payload, ensure_ascii=False)},
            ],
            session_factory=SessionLocal,
        )
        task = _create_task(sync_db)
        session = _create_runtime_session(sync_db, task)

        result = asyncio.run(
            agent._execute_impl(_orchestrator_request(task, {"user_prompt": "test prompt"}))
        )

        with SessionLocal() as verification_db:
            runtime_store = SqlAlchemyRuntimeAttemptStore(verification_db)
            runtime_session = runtime_store.load_session(session.session_id)
            assert runtime_session is not None
            assert runtime_session.current_attempt_id is not None
            attempt = runtime_store.load_attempt(
                runtime_session.session_id,
                runtime_session.current_attempt_id,
            )
            assert attempt is not None
            assert attempt.continuation_checkpoint is not None
            checkpoint = attempt.continuation_checkpoint.to_dict()

        assert result["status"] == "waiting_gate"
        assert shared_store.get("workflow.diagnostics.compat.plan_snapshot") is None
        assert shared_store.get("workflow.diagnostics.compat.activation_pool_snapshot") is None
        assert shared_store.get("workflow.plan") is None
        assert shared_store.get("workflow.activation_pool") is None
        assert shared_store.get("workflow.task_specs") is None
        assert shared_store.get("workflow.conditional_tasks") is None
        rendered_planning_text = "\n".join(
            message.get("content", "")
            for call in agent._llms["plan"].calls
            for message in call.get("messages", [])
            if isinstance(message, dict)
        )
        assert "workflow_state_id" not in rendered_planning_text
        assert str(task.task_id) not in rendered_planning_text
        assert checkpoint["task_specs"][AgentType.VIDEO_GENERATOR.value]["run"] is False
        assert checkpoint["task_specs"][AgentType.VIDEO_GENERATOR.value]["runtime_hints"] == {
            "generate_audio": True
        }
        assert len(call_log["concept_planner"]) == 1
        assert len(call_log["script_writer"]) == 1
        assert call_log["image_generator"] == []
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
