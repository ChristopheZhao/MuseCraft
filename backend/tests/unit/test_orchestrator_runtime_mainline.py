import asyncio
import json
import logging
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
    engine = create_engine("sqlite:///:memory:")
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


def _build_agent(monkeypatch, sync_db, *, call_log):
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


def _build_stage_g_agent(monkeypatch, sync_db, *, call_log, llm_responses):
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


def test_orchestrator_mainline_opens_script_gate_and_stops_before_post_script(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)
        task = _create_task(sync_db)
        session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")

        result = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )
        runtime_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
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


def test_orchestrator_mainline_resumes_after_script_approve_without_kernel(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        planning_calls = {"select": 0, "decompose": 0}
        continuation_calls = []
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)

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

        second = asyncio.run(
            agent._execute_impl(
                task=task,
                input_data={"user_prompt": "test prompt"},
                db=sync_db,
            )
        )
        runtime_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
        nodes_by_key = {node["node_key"]: node for node in runtime_view["nodes"]}

        assert second["status"] == "completed"
        assert runtime_view["status"] == WorkflowSessionStatus.COMPLETED.value
        assert task.status == TaskStatus.COMPLETED.value
        assert nodes_by_key["concept"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["script"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert nodes_by_key["image"]["status"] == WorkflowNodeStatus.COMPLETED.value
        assert planning_calls == {"select": 1, "decompose": 1}
        assert continuation_calls == [{"session_id": session.id, "task_id": task.id}]
        assert len(call_log["concept_planner"]) == 1
        assert len(call_log["script_writer"]) == 1
        assert len(call_log["image_generator"]) == 1
    finally:
        sync_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_orchestrator_mainline_fails_closed_when_runtime_script_boundary_missing(monkeypatch):
    engine, SessionLocal = _build_sync_db()
    sync_db = SessionLocal()
    try:
        call_log = {"concept_planner": [], "script_writer": [], "image_generator": []}
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)
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

        runtime_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
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
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)
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

        runtime_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
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
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)

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
        runtime_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
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
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)

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
        runtime_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
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
        agent = _build_agent(monkeypatch, sync_db, call_log=call_log)
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
        runtime_view = RuntimeSessionService.build_runtime_view_for_task_sync(sync_db, task)
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
