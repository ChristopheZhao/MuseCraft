import asyncio
import json
import logging
import tempfile
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.orchestrator import OrchestratorAgent
from app.agents import orchestrator as orchestrator_module
from app.agents.base import AgentError
from app.core.prompt_manager import get_prompt_manager
from app.core.database import Base
from app.models import (
    AgentType,
    Task,
    TaskStatus,
    TaskType,
    WorkflowSessionStatus,
    WorkflowNodeStatus,
)
from app.services.orchestration_state_adapter import OrchestrationStateAdapter
from app.services.context_assembler import ContextContractAssembler
from app.services.orchestration_runtime_resume_bootstrap_facade import (
    OrchestrationRuntimeResumeBootstrapFacade,
)
from app.services.orchestration_runtime_transition_facade import (
    OrchestrationRuntimeTransitionFacade,
)
from app.services.published_deliverable_service import (
    PublishedDeliverableService,
    build_deliverable_ref,
)
from app.services.runtime_session_service import RuntimeSessionService


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

    async def execute(self, *, task, input_data, db, execution_order):
        self._calls.append(
            {
                "agent_name": self.agent_name,
                "input_data": dict(input_data),
                "execution_order": execution_order,
            }
        )
        return dict(self._output)


class _FlakyAgent:
    def __init__(self, name, *, first_error, success_output, calls):
        self.agent_name = name
        self._first_error = first_error
        self._success_output = dict(success_output)
        self._calls = calls
        self._attempt = 0

    async def execute(self, *, task, input_data, db, execution_order):
        self._attempt += 1
        self._calls.append(
            {
                "agent_name": self.agent_name,
                "input_data": dict(input_data),
                "execution_order": execution_order,
                "attempt": self._attempt,
            }
        )
        if self._attempt == 1:
            raise self._first_error
        return dict(self._success_output)


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
    deliverable = PublishedDeliverableService.publish_script_deliverable_sync(
        kwargs["db"],
        session=kwargs["session"],
        workflow_id=str(kwargs.get("workflow_state_id") or ""),
        attempt_id=int(kwargs.get("attempt_id") or 0),
        payload={
            "concept_plan": {"scenes": [{"scene_number": 1}]},
            "scene_overview": {
                "scenes": [{"scene_number": 1, "visual_description": "stub scene"}]
            },
            "scene_scripts": {"1": {"script_text": "Scene 1 approved script"}},
        },
        summary={"total_scenes": 1},
    )
    artifact_ref = build_deliverable_ref(deliverable)
    return {
        "artifact_ref": artifact_ref,
        "artifact_refs": [artifact_ref],
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


def _load_runtime_view_from_fresh_session(SessionLocal, task_id):
    inspect_db = SessionLocal()
    try:
        fresh_task = inspect_db.query(Task).filter(Task.id == int(task_id)).first()
        if fresh_task is None:
            raise AssertionError(f"task {task_id} missing in fresh-session inspection")
        return RuntimeSessionService.build_runtime_view_for_task_sync(inspect_db, fresh_task)
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
        fresh_session = RuntimeSessionService.get_session_by_id_sync(inspect_db, int(session_id))
        if fresh_session is None:
            raise AssertionError(f"runtime session {session_id} missing in fresh-session inspection")
        return {
            "id": fresh_session.id,
            "status": fresh_session.status,
        }
    finally:
        inspect_db.close()


def _load_runtime_node_snapshot_from_fresh_session(SessionLocal, session_id, node_key):
    inspect_db = SessionLocal()
    try:
        fresh_node = RuntimeSessionService.get_node_by_key_sync(inspect_db, int(session_id), node_key)
        if fresh_node is None:
            raise AssertionError(
                f"runtime node {node_key} missing for session {session_id} in fresh-session inspection"
            )
        return {
            "id": fresh_node.id,
            "status": fresh_node.status,
            "diagnostics": list(fresh_node.diagnostics or []),
        }
    finally:
        inspect_db.close()


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
    monkeypatch.setattr(orchestrator_module, "activate_current_attempt_keepalive", lambda **kwargs: True)
    monkeypatch.setattr(orchestrator_module, "deactivate_current_attempt_keepalive", lambda **kwargs: True)

    agent = object.__new__(OrchestratorAgent)
    agent.agent_type = AgentType.ORCHESTRATOR
    agent.agent_name = "orchestrator"
    agent.logger = logging.getLogger("test.orchestrator.runtime_mainline")
    agent._task_db_id = None
    agent._memory_services = memory_services
    agent._wm_cache = None
    agent._last_audio_route_payload = {}
    agent._orchestration_state = OrchestrationStateAdapter(memory_services=memory_services)
    agent._context_contract_assembler = SimpleNamespace(
        assemble_agent_context=lambda **kwargs: {},
        publish_script_review_boundary_sync=_fake_script_review_boundary,
    )
    if session_factory is not None:
        agent._orchestration_runtime_transition_facade = OrchestrationRuntimeTransitionFacade(
            context_contract_assembler=agent._context_contract_assembler,
            orchestration_state=agent._orchestration_state,
            session_factory=session_factory,
        )
    agent._workflow_completion_adapter = SimpleNamespace(
        publish_completed=_async_return({"final_video_url": "https://example.com/final.mp4"}),
        publish_failed=_async_return({}),
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
            "apply_result": {},
            "decision_ack": {},
        }
    )
    agent._emit_pre_dispatch_diagnostics = lambda *args, **kwargs: None
    agent._build_execution_queue = lambda task_specs, candidate_agents=None: list(task_specs.keys())
    agent._build_standby_agents = lambda task_specs, candidate_agents=None: []
    agent._store_composer_outputs = lambda *args, **kwargs: None
    agent._store_creative_guidance_from_output = _async_noop
    agent._should_retry_step = _async_return(False)
    agent._llm_decompose_tasks = _async_return(
        (
            {
                AgentType.CONCEPT_PLANNER: {"run": True, "order": 0, "scope": {}},
                AgentType.SCRIPT_WRITER: {"run": True, "order": 1, "scope": {}},
                AgentType.IMAGE_GENERATOR: {"run": True, "order": 2, "scope": {}},
            },
            {},
        )
    )
    agent.agents = {
        AgentType.CONCEPT_PLANNER: _FakeAgent(
            "concept_planner",
            {"concept_plan": {"scenes": [{"scene_number": 1}]}},
            call_log["concept_planner"],
        ),
        AgentType.SCRIPT_WRITER: _FakeAgent(
            "script_writer",
            {
                "scenes_generated": 1,
                "total_scenes": 1,
                "script_results": {"scripts": {"1": {"script_text": "Scene 1 approved script"}}},
            },
            call_log["script_writer"],
        ),
        AgentType.IMAGE_GENERATOR: _FakeAgent(
            "image_generator",
            {"success": True},
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
    monkeypatch.setattr(orchestrator_module, "activate_current_attempt_keepalive", lambda **kwargs: True)
    monkeypatch.setattr(orchestrator_module, "deactivate_current_attempt_keepalive", lambda **kwargs: True)

    agent = object.__new__(OrchestratorAgent)
    agent.agent_type = AgentType.ORCHESTRATOR
    agent.agent_name = "orchestrator"
    agent.logger = logging.getLogger("test.orchestrator.stage_g")
    agent.prompt_manager = get_prompt_manager()
    agent._llms = {"plan": _QueuedPlanLLM(llm_responses)}
    agent._task_db_id = None
    agent._memory_services = memory_services
    agent._wm_cache = None
    agent._last_audio_route_payload = {}
    agent._orchestration_state = OrchestrationStateAdapter(memory_services=memory_services)
    agent._context_contract_assembler = SimpleNamespace(
        assemble_agent_context=lambda **kwargs: {},
        publish_script_review_boundary_sync=_fake_script_review_boundary,
    )
    if session_factory is not None:
        agent._orchestration_runtime_transition_facade = OrchestrationRuntimeTransitionFacade(
            context_contract_assembler=agent._context_contract_assembler,
            orchestration_state=agent._orchestration_state,
            session_factory=session_factory,
        )
    agent._workflow_completion_adapter = SimpleNamespace(
        publish_completed=_async_return({"final_video_url": "https://example.com/final.mp4"}),
        publish_failed=_async_return({}),
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
            "apply_result": {},
            "decision_ack": {},
        }
    )
    agent._emit_pre_dispatch_diagnostics = lambda *args, **kwargs: None
    agent._store_composer_outputs = lambda *args, **kwargs: None
    agent._store_creative_guidance_from_output = _async_noop
    agent._should_retry_step = _async_return(False)
    agent.agents = {
        AgentType.CONCEPT_PLANNER: _FakeAgent(
            "concept_planner",
            {"concept_plan": {"scenes": [{"scene_number": 1}]}},
            call_log["concept_planner"],
        ),
        AgentType.SCRIPT_WRITER: _FakeAgent(
            "script_writer",
            {
                "scenes_generated": 1,
                "total_scenes": 1,
                "script_results": {"scripts": {"1": {"script_text": "Scene 1 approved script"}}},
            },
            call_log["script_writer"],
        ),
        AgentType.IMAGE_GENERATOR: _FakeAgent(
            "image_generator",
            {"success": True},
            call_log["image_generator"],
        ),
        AgentType.VIDEO_GENERATOR: _FakeAgent(
            "video_generator",
            {"success": True},
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


async def _async_identity(*args, **kwargs):
    workflow_data = dict(args[0] if args else kwargs.get("workflow_data") or {})
    return workflow_data


def _build_recording_resume_bootstrap_facade(agent):
    real_facade = OrchestrationRuntimeResumeBootstrapFacade(
        orchestration_state=agent._orchestration_state,
    )

    class _RecordingResumeBootstrapFacade:
        def __init__(self):
            self.resolve_calls = []
            self.load_calls = []
            self.start_calls = []

        def resolve_runtime_resume_context(self, **kwargs):
            self.resolve_calls.append(dict(kwargs))
            return real_facade.resolve_runtime_resume_context(**kwargs)

        def load_authoritative_resume_task_specs(self, **kwargs):
            self.load_calls.append(dict(kwargs))
            return real_facade.load_authoritative_resume_task_specs(**kwargs)

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
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        result = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )
        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}

        assert result["status"] == "waiting_gate"
        assert result["session_id"] == session.id
        assert runtime_view["status"] == WorkflowSessionStatus.WAITING_GATE.value
        assert nodes_by_key["concept"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.PENDING_GATE.value
        assert runtime_view["active_gate"]["gate_name"] == "script_review"
        assert task.status == TaskStatus.IN_PROGRESS.value
        assert len(call_log["concept_planner"]) == 1
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
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
        facade = OrchestrationRuntimeTransitionFacade(
            context_contract_assembler=agent._context_contract_assembler,
            orchestration_state=agent._orchestration_state,
            session_factory=SessionLocal,
        )

        observed = {}

        def _record_loaded_runtime_state(runtime_db, runtime_session, runtime_task):
            observed["db_id"] = id(runtime_db)
            observed["session_id"] = runtime_session.id
            observed["task_id"] = runtime_task.id if runtime_task is not None else None
            return "ok"

        result = facade._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=session.id,
            task_db_id=task.id,
            action=_record_loaded_runtime_state,
        )

        assert result == "ok"
        assert observed["db_id"] != id(sync_db)
        assert observed["session_id"] == session.id
        assert observed["task_id"] == task.id
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_runtime_resume_bootstrap_facade_uses_caller_owned_session(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)
        facade = OrchestrationRuntimeResumeBootstrapFacade(
            orchestration_state=agent._orchestration_state,
        )
        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        observed_db_ids = []
        original_start = RuntimeSessionService.start_node_attempt_sync
        original_bind = RuntimeSessionService.bind_attempt_continuation_checkpoint_sync
        original_grant = RuntimeSessionService.grant_attempt_lease_sync
        original_clear = RuntimeSessionService.clear_node_diagnostic_codes_sync

        def _record_start(db, runtime_session, **kwargs):
            observed_db_ids.append(("start", id(db)))
            return original_start(db, runtime_session, **kwargs)

        def _record_bind(db, runtime_session, **kwargs):
            observed_db_ids.append(("bind", id(db)))
            return original_bind(db, runtime_session, **kwargs)

        def _record_grant(db, runtime_session, **kwargs):
            observed_db_ids.append(("grant", id(db)))
            return original_grant(db, runtime_session, **kwargs)

        def _record_clear(db, runtime_session, **kwargs):
            observed_db_ids.append(("clear", id(db)))
            return original_clear(db, runtime_session, **kwargs)

        monkeypatch.setattr(RuntimeSessionService, "start_node_attempt_sync", staticmethod(_record_start))
        monkeypatch.setattr(RuntimeSessionService, "bind_attempt_continuation_checkpoint_sync", staticmethod(_record_bind))
        monkeypatch.setattr(RuntimeSessionService, "grant_attempt_lease_sync", staticmethod(_record_grant))
        monkeypatch.setattr(RuntimeSessionService, "clear_node_diagnostic_codes_sync", staticmethod(_record_clear))

        result = facade.start_runtime_attempt(
            db=sync_db,
            runtime_session=session,
            task=task,
            current_agent_type=AgentType.CONCEPT_PLANNER,
            workflow_state_id=str(task.task_id),
            task_specs={
                AgentType.CONCEPT_PLANNER: {"run": True, "order": 0, "scope": {}},
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
        assert {db_id for _name, db_id in observed_db_ids} == {id(sync_db)}
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
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        completion_calls = []
        class _StubRuntimeTransitions:
            def complete_runtime_attempt(self, **kwargs):
                completion_calls.append(dict(kwargs))

            def open_script_review_gate(self, **kwargs):
                return {
                    "status": "waiting_gate",
                    "session_id": session.id,
                    "gate_id": 1,
                    "node_key": "script",
                }

        agent._orchestration_runtime_transition_facade = _StubRuntimeTransitions()

        result = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )

        assert result["status"] == "waiting_gate"
        assert completion_calls
        assert completion_calls[0]["runtime_session_id"] == session.id
        assert completion_calls[0]["node_key"] == "concept"
        assert completion_calls[0]["node_status"] == WorkflowNodeStatus.COMPLETED.value
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_routes_script_gate_transition_through_runtime_transition_facade(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        completion_calls = []
        gate_calls = []
        class _StubRuntimeTransitions:
            def complete_runtime_attempt(self, **kwargs):
                completion_calls.append(dict(kwargs))

            def open_script_review_gate(self, **kwargs):
                gate_calls.append(dict(kwargs))
                return {
                    "status": "waiting_gate",
                    "session_id": session.id,
                    "gate_id": 1,
                    "node_key": "script",
                }

        agent._orchestration_runtime_transition_facade = _StubRuntimeTransitions()

        result = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )

        assert result["status"] == "waiting_gate"
        assert completion_calls
        assert gate_calls
        assert gate_calls[0]["runtime_session_id"] == session.id
        assert gate_calls[0]["task_db_id"] == task.id
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
        agent._orchestration_runtime_resume_bootstrap_facade = _build_recording_resume_bootstrap_facade(agent)
        monkeypatch.setattr(
            orchestrator_module,
            "activate_current_attempt_keepalive",
            lambda **kwargs: activate_calls.append(dict(kwargs)) or True,
        )

        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        completion_calls = []
        gate_calls = []

        class _StubRuntimeTransitions:
            def complete_runtime_attempt(self, **kwargs):
                completion_calls.append(dict(kwargs))

            def open_script_review_gate(self, **kwargs):
                gate_calls.append(dict(kwargs))
                return {
                    "status": "waiting_gate",
                    "session_id": session.id,
                    "gate_id": 1,
                    "node_key": "script",
                }

        agent._orchestration_runtime_transition_facade = _StubRuntimeTransitions()

        result = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
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
        agent._orchestration_runtime_resume_bootstrap_facade = _build_recording_resume_bootstrap_facade(agent)
        monkeypatch.setattr(orchestrator_module, "activate_current_attempt_keepalive", lambda **kwargs: False)

        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        with pytest.raises(AgentError, match="Execution host keepalive unavailable"):
            asyncio.run(
                agent._execute_impl(
                    task=task,
                    input_data={"user_prompt": "test prompt"},
                    db=sync_db,
                )
            )

        fresh_task = _load_task_snapshot_from_fresh_session(SessionLocal, task.id)
        fresh_session = _load_runtime_session_snapshot_from_fresh_session(SessionLocal, session.id)
        node = _load_runtime_node_snapshot_from_fresh_session(SessionLocal, session.id, "concept")
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
        assert agent._orchestration_runtime_resume_bootstrap_facade.start_calls[0]["current_agent_type"] == AgentType.CONCEPT_PLANNER
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_resumes_after_script_approve_without_kernel(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        planning_calls = {"select": 0, "decompose": 0}
        continuation_calls = []
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
                    AgentType.CONCEPT_PLANNER: {"run": True, "order": 0, "scope": {}},
                    AgentType.SCRIPT_WRITER: {"run": True, "order": 1, "scope": {}},
                    AgentType.IMAGE_GENERATOR: {"run": True, "order": 2, "scope": {}},
                },
                {},
            )

        agent._llm_select_candidate_agents = _count_select
        agent._llm_decompose_tasks = _count_decompose
        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
        original_consume = RuntimeSessionService.consume_script_approval_continuation_sync

        def _record_consume(db, runtime_session, *, task=None):
            continuation_calls.append(
                {
                    "session_id": runtime_session.id,
                    "task_id": getattr(task, "id", None),
                }
            )
            return original_consume(db, runtime_session, task=task)

        monkeypatch.setattr(
            RuntimeSessionService,
            "consume_script_approval_continuation_sync",
            staticmethod(_record_consume),
        )

        first = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )
        assert first["status"] == "waiting_gate"

        RuntimeSessionService.submit_gate_decision_sync(
            sync_db,
            session.id,
            node_key="script",
            action="approve",
            feedback_text="looks good",
        )
        agent._memory_services.short_term._shared_store.clear()
        agent._orchestration_runtime_resume_bootstrap_facade = _build_recording_resume_bootstrap_facade(agent)

        second = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )
        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        fresh_task = _load_task_snapshot_from_fresh_session(SessionLocal, task.id)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}

        assert second["status"] == "completed"
        assert runtime_view["status"] == WorkflowSessionStatus.COMPLETED.value
        assert fresh_task["status"] == TaskStatus.COMPLETED.value
        assert nodes_by_key["concept"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["image"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert len(agent._orchestration_runtime_resume_bootstrap_facade.load_calls) == 1
        assert agent._orchestration_runtime_resume_bootstrap_facade.load_calls[0]["resume_action"] == "approve"
        assert planning_calls == {"select": 1, "decompose": 1}
        assert continuation_calls == [{"session_id": session.id, "task_id": task.id}]
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
        agent._orchestration_runtime_resume_bootstrap_facade = _build_recording_resume_bootstrap_facade(agent)

        async def _count_select(*args, **kwargs):
            planning_calls["select"] += 1
            return ([AgentType.SCRIPT_WRITER], "unexpected-selection")

        async def _count_decompose(*args, **kwargs):
            planning_calls["decompose"] += 1
            return ({AgentType.SCRIPT_WRITER: {"run": True, "order": 0, "scope": {}}}, {})

        agent._llm_select_candidate_agents = _count_select
        agent._llm_decompose_tasks = _count_decompose

        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
        attempt = RuntimeSessionService.start_node_attempt_sync(
            sync_db,
            session,
            node_key="script",
            task=task,
        )
        continuation_checkpoint = agent._orchestration_state.build_continuation_checkpoint(
            task_specs={
                AgentType.SCRIPT_WRITER: {"run": True, "order": 0, "scope": {}},
            },
            conditional_task_specs={},
            candidate_agents=[AgentType.SCRIPT_WRITER],
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            node_key="script",
            attempt_id=attempt.id,
            decision_id=None,
        )
        RuntimeSessionService.bind_attempt_continuation_checkpoint_sync(
            sync_db,
            session,
            attempt_id=attempt.id,
            continuation_checkpoint=continuation_checkpoint,
        )
        RuntimeSessionService.mark_session_resuming_sync(sync_db, session, task=task)

        result = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
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
        agent._prepare_agent_context = OrchestratorAgent._prepare_agent_context.__get__(agent, OrchestratorAgent)
        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        first = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )
        assert first["status"] == "waiting_gate"

        real_assembler = ContextContractAssembler(agent._memory_services)
        agent._context_contract_assembler.assemble_agent_context = real_assembler.assemble_agent_context
        RuntimeSessionService.submit_gate_decision_sync(
            sync_db,
            session.id,
            node_key="script",
            action="approve",
            feedback_text="looks good",
        )
        session.input_payload = {}
        sync_db.commit()

        with pytest.raises(AgentError, match="script_prerequisite_not_satisfied"):
            asyncio.run(
                agent._execute_impl(
                    task=task,
                    input_data={"user_prompt": "test prompt"},
                    db=sync_db,
                )
            )

        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        assert runtime_view["status"] == WorkflowSessionStatus.FAILED.value
        assert len(call_log["image_generator"]) == 0
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_blocks_script_consumers_before_dispatch_when_queue_is_misordered(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log, session_factory=SessionLocal)
        task = _create_task(sync_db)

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
                    AgentType.CONCEPT_PLANNER: {"run": True, "order": 0, "scope": {}},
                    AgentType.IMAGE_GENERATOR: {"run": True, "order": 1, "scope": {}},
                    AgentType.SCRIPT_WRITER: {"run": True, "order": 2, "scope": {}},
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
                agent._execute_impl(
                    task=task,
                    input_data={"user_prompt": "test prompt"},
                    db=sync_db,
                )
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
                    AgentType.CONCEPT_PLANNER: {"run": True, "order": 0, "scope": {}},
                    AgentType.SCRIPT_WRITER: {"run": True, "order": 1, "scope": {}},
                    AgentType.IMAGE_GENERATOR: {"run": True, "order": 2, "scope": {}},
                },
                {},
            )

        agent._llm_select_candidate_agents = _count_select
        agent._llm_decompose_tasks = _count_decompose
        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        first = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )
        assert first["status"] == "waiting_gate"

        RuntimeSessionService.submit_gate_decision_sync(
            sync_db,
            session.id,
            node_key="script",
            action="revise",
            feedback_text="tighten pacing",
            structured_constraints={"keep_character": True},
        )
        agent._memory_services.short_term._shared_store.clear()

        second = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
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
        assert call_log["script_writer"][1]["input_data"]["script_review_contract"]["action"] == "revise"
        assert call_log["script_writer"][1]["input_data"]["script_review_contract"]["feedback_text"] == "tighten pacing"
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
                    AgentType.CONCEPT_PLANNER: {"run": True, "order": 0, "scope": {}},
                    AgentType.SCRIPT_WRITER: {"run": True, "order": 1, "scope": {}},
                    AgentType.IMAGE_GENERATOR: {"run": True, "order": 2, "scope": {}},
                },
                {},
            )

        agent._llm_select_candidate_agents = _count_select
        agent._llm_decompose_tasks = _count_decompose
        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        first = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )
        assert first["status"] == "waiting_gate"

        RuntimeSessionService.submit_gate_decision_sync(
            sync_db,
            session.id,
            node_key="script",
            action="replan",
            feedback_text="change structure",
            structured_constraints={"new_arc": "stronger opening"},
        )
        agent._memory_services.short_term._shared_store.clear()

        second = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
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
        assert call_log["concept_planner"][1]["input_data"]["script_review_contract"]["action"] == "replan"
        assert call_log["concept_planner"][1]["input_data"]["script_review_contract"]["structured_constraints"] == {
            "new_arc": "stronger opening"
        }
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
        agent._should_retry_step = _async_return(True)
        agent.agents[AgentType.SCRIPT_WRITER] = _FlakyAgent(
            "script_writer",
            first_error=RuntimeError("temporary timeout"),
            success_output={
                "scenes_generated": 1,
                "total_scenes": 1,
                "script_results": {"scripts": {"1": {"script_text": "Scene 1 approved script"}}},
            },
            calls=call_log["script_writer"],
        )
        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        result = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )
        runtime_view = _load_runtime_view_from_fresh_session(SessionLocal, task.id)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}

        assert result["status"] == "waiting_gate"
        assert result["session_id"] == session.id
        assert runtime_view["status"] == WorkflowSessionStatus.WAITING_GATE.value
        assert runtime_view["active_gate"]["gate_name"] == "script_review"
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.PENDING_GATE.value
        assert len(call_log["concept_planner"]) == 1
        assert len(call_log["script_writer"]) == 2
        assert call_log["image_generator"] == []
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
        )
        task = _create_task(sync_db)

        result = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )

        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
        attempt = RuntimeSessionService.get_attempt_by_id_sync(
            sync_db,
            session.id,
            session.current_attempt_id,
        )
        checkpoint = dict(getattr(attempt, "continuation_checkpoint", {}) or {})

        assert result["status"] == "waiting_gate"
        assert shared_store.get("workflow.diagnostics.compat.plan_snapshot") is None
        assert shared_store.get("workflow.diagnostics.compat.activation_pool_snapshot") is None
        assert shared_store.get("workflow.plan") is None
        assert shared_store.get("workflow.activation_pool") is None
        assert shared_store.get("workflow.task_specs") is None
        assert shared_store.get("workflow.conditional_tasks") is None
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
