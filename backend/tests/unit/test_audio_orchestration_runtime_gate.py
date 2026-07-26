import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.agents import orchestrator as orchestrator_module
from app.agents.base import AgentError
from app.agents.orchestrator import OrchestratorAgent
from app.agents.tools.video_composition import composition_tool as composition_module
from app.agents.tools.video_composition.composition_tool import CompositionTool
from app.agents.utils.artifacts import (
    evaluate_scene_output_acceptance,
    issue_scene_output_acceptance_receipts,
)
from app.core.config import settings
from app.core.prompt_manager import get_prompt_manager
from app.domain import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentTaskReference,
    AgentType,
    JsonObjectPayload,
    TaskStatus,
)
from app.services import audio_delivery_gate_evaluator as audio_gate_module
from app.services.audio_delivery_gate_evaluator import AudioDeliveryGateEvaluator
from app.services.orchestration_control_plane import (
    OrchestrationControlPlane,
    OrchestrationControlPlaneError,
)
from app.services.orchestration_observation_adapter import OrchestrationObservationAdapter
from app.services.orchestration_protocol import OrchestrationProtocol, OrchestrationProtocolError
from app.services.orchestration_queue_policy import OrchestrationQueuePolicy
from app.services.orchestration_runtime_controller import (
    OrchestrationRuntimeController,
    OrchestrationRuntimeControllerError,
)
from app.services.orchestration_state_adapter import OrchestrationStateAdapter


class _FakeWM:
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class _StubFFmpegTool:
    def __init__(self, payload_by_path):
        self.payload_by_path = payload_by_path

    async def execute(self, tool_input):
        file_path = tool_input.parameters.get("file_path")
        payload = self.payload_by_path.get(file_path)
        if isinstance(payload, Exception):
            raise payload
        return payload


class _FakeSharedMemoryStore:
    def __init__(self, initial=None):
        self._data = dict(initial or {})

    def get(self, key, default=None):
        return self._data.get(key, default)

    def put(self, key, value):
        self._data[key] = value


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


class _FakeWorkflowTask:
    def __init__(self, task_id):
        self.task_id = task_id
        self.status = TaskStatus.PENDING
        self.current_step = None
        self.progress_percentage = 0

    def update_progress(self, step, percentage):
        self.current_step = step
        self.progress_percentage = percentage


class _StubWorkflowAgent:
    def __init__(self, agent_name, outputs):
        self.agent_name = agent_name
        self._outputs = list(outputs)

    async def execute(self, request):
        assert isinstance(request, AgentExecutionRequest)
        if not self._outputs:
            raise AssertionError(f"{self.agent_name} executed more times than expected")
        output = self._outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output if isinstance(output, AgentExecutionResult) else _make_agent_result(output)


def _make_agent_result(output=None, *, report=None):
    normalized = dict(output or {})
    explicit_report = normalized.pop("orchestration_report", report)
    return AgentExecutionResult(
        output_data=JsonObjectPayload.from_mapping(
            normalized,
            field_path="test.agent_output",
        ),
        orchestration_report=(
            JsonObjectPayload.from_mapping(
                explicit_report,
                field_path="test.orchestration_report",
            )
            if explicit_report is not None
            else None
        ),
    )


def _make_orchestrator_request(task, input_data):
    return AgentExecutionRequest(
        task=AgentTaskReference(
            task_id=str(task.task_id),
            task_type="video_generation",
        ),
        agent_type=AgentType.ORCHESTRATOR.value,
        input_data=JsonObjectPayload.from_mapping(
            input_data,
            field_path="test.orchestrator_input",
        ),
        workflow_state_id=str(task.task_id),
    )


def _run_main_loop(agent, task):
    return agent._execute_impl(
        _make_orchestrator_request(
            task,
            {"user_prompt": "make a short video", "resolution": "720p"},
        )
    )


def _build_video_wm(total_scenes, scene_records):
    return _FakeWM(
        {
            "scene_overview": {
                "scenes": [{"scene_number": i + 1} for i in range(total_scenes)],
            },
            "scene_outputs.video": scene_records,
        }
    )


def _scene_output_record(
    *,
    kind,
    scene_number,
    workflow_state_id,
    artifact_path="",
    artifact_url="",
):
    artifact = {
        "success": True,
        "scene_number": scene_number,
        f"{kind}_path": artifact_path,
        f"{kind}_url": artifact_url,
    }
    if kind == "video" and artifact_path:
        artifact["metadata"] = {"storage": {"status": "persisted"}}
    issued, _receipts = issue_scene_output_acceptance_receipts(
        kind=kind,
        artifacts=[artifact],
        workflow_state_id=workflow_state_id,
    )
    return issued[0]


def _build_orchestrator_gate_agent(shared_facts):
    agent = object.__new__(OrchestratorAgent)
    agent.agent_name = "orchestrator"
    agent.logger = logging.getLogger("test.orchestrator.gate")
    shared_store = _FakeSharedMemoryStore(shared_facts)
    agent._memory_services = SimpleNamespace(short_term=_FakeShortTermService(shared_store))
    return agent


def test_image_step_completion_requires_all_expected_scene_outputs():
    agent = _build_orchestrator_gate_agent(
        {
            "scene_overview": {
                "scenes": [{"scene_number": 1}, {"scene_number": 2}],
            },
            "scene_outputs.image": {
                1: {"scene_number": 1, "image_url": "https://example.com/scene-1.png"},
            },
        }
    )

    assert agent._is_image_step_completed("wf-image-incomplete") is False


def test_image_step_completion_accepts_scene_output_contract():
    agent = _build_orchestrator_gate_agent(
        {
            "scene_overview": {
                "scenes": [{"scene_number": 1}, {"scene_number": 2}],
            },
            "scene_outputs.image": {
                1: _scene_output_record(
                    kind="image",
                    scene_number=1,
                    workflow_state_id="wf-image-complete",
                    artifact_url="https://example.com/scene-1.png",
                ),
                2: _scene_output_record(
                    kind="image",
                    scene_number=2,
                    workflow_state_id="wf-image-complete",
                    artifact_path="/tmp/scene-2.png",
                ),
            },
        }
    )

    assert agent._is_image_step_completed("wf-image-complete") is True


def test_video_step_completion_rejects_url_only_scene_outputs():
    agent = _build_orchestrator_gate_agent(
        {
            "scene_overview": {
                "scenes": [{"scene_number": 1}, {"scene_number": 2}],
            },
            "scene_outputs.video": {
                1: _scene_output_record(
                    kind="video",
                    scene_number=1,
                    workflow_state_id="wf-video-url-only",
                    artifact_path="/tmp/scene-1.mp4",
                ),
                2: _scene_output_record(
                    kind="video",
                    scene_number=2,
                    workflow_state_id="wf-video-url-only",
                    artifact_url="https://example.com/scene-2.mp4",
                ),
            },
        }
    )

    assert agent._is_video_step_completed("wf-video-url-only") is False


def test_video_step_completion_accepts_scene_output_contract():
    agent = _build_orchestrator_gate_agent(
        {
            "scene_overview": {
                "scenes": [{"scene_number": 1}, {"scene_number": 2}],
            },
            "scene_outputs.video": {
                1: _scene_output_record(
                    kind="video",
                    scene_number=1,
                    workflow_state_id="wf-video-complete",
                    artifact_path="/tmp/scene-1.mp4",
                ),
                2: _scene_output_record(
                    kind="video",
                    scene_number=2,
                    workflow_state_id="wf-video-complete",
                    artifact_path="/tmp/scene-2.mp4",
                ),
            },
        }
    )

    assert agent._is_video_step_completed("wf-video-complete") is True


def test_scene_output_acceptance_does_not_mint_receipt_from_path():
    shared = _FakeWM(
        {
            "scene_outputs.image": {
                1: {"scene_number": 1, "image_path": "/tmp/scene-1.png"},
            }
        }
    )

    contract = evaluate_scene_output_acceptance(
        kind="image",
        workflow_id="wf-no-receipt",
        agent_memory=None,
        shared_memory=shared,
        expected_scene_numbers=[1],
    )

    assert contract["accepted"] is False
    assert contract["accepted_receipts"] == []
    assert contract["rejected_scene_outputs"] == [
        {
            "scene_number": 1,
            "reason_code": "scene_output_acceptance_receipt_missing",
        }
    ]


@pytest.mark.parametrize(
    ("status_value", "remove_status", "reason_code"),
    [
        ("", True, "scene_output_acceptance_receipt_incomplete"),
        ("pending", False, "scene_output_acceptance_receipt_invalid"),
        ("unknown", False, "scene_output_acceptance_receipt_invalid"),
    ],
)
def test_scene_output_acceptance_rejects_missing_or_nonaccepted_status(
    status_value,
    remove_status,
    reason_code,
):
    record = _scene_output_record(
        kind="image",
        scene_number=1,
        workflow_state_id="wf-status-contract",
        artifact_path="/tmp/scene-1.png",
    )
    receipt = record["acceptance_receipt"]
    if remove_status:
        receipt.pop("status")
    else:
        receipt["status"] = status_value
    shared = _FakeWM({"scene_outputs.image": {1: record}})

    contract = evaluate_scene_output_acceptance(
        kind="image",
        workflow_id="wf-status-contract",
        agent_memory=None,
        shared_memory=shared,
        expected_scene_numbers=[1],
    )

    assert contract["accepted"] is False
    assert contract["rejected_scene_outputs"][0]["reason_code"] == reason_code


@pytest.mark.parametrize(
    ("field_name", "field_value", "reason_code"),
    [
        ("artifact_kind", "video", "scene_output_acceptance_kind_mismatch"),
        (
            "delivery_ref",
            "scene_outputs.image.99",
            "scene_output_acceptance_ref_mismatch",
        ),
        (
            "artifact_ref",
            "/tmp/other-scene.png",
            "scene_output_acceptance_artifact_ref_mismatch",
        ),
        (
            "workflow_state_id",
            "wf-other",
            "scene_output_acceptance_workflow_mismatch",
        ),
    ],
)
def test_scene_output_acceptance_rejects_mismatched_receipt_provenance(
    field_name,
    field_value,
    reason_code,
):
    record = _scene_output_record(
        kind="image",
        scene_number=1,
        workflow_state_id="wf-provenance",
        artifact_path="/tmp/scene-1.png",
    )
    record["acceptance_receipt"][field_name] = field_value
    shared = _FakeWM({"scene_outputs.image": {1: record}})

    contract = evaluate_scene_output_acceptance(
        kind="image",
        workflow_id="wf-provenance",
        agent_memory=None,
        shared_memory=shared,
        expected_scene_numbers=[1],
    )

    assert contract["accepted"] is False
    assert contract["rejected_scene_outputs"][0]["reason_code"] == reason_code


def test_scene_output_acceptance_rejects_unknown_receipt_keys():
    record = _scene_output_record(
        kind="image",
        scene_number=1,
        workflow_state_id="wf-unknown-receipt-key",
        artifact_path="/tmp/scene-1.png",
    )
    record["acceptance_receipt"]["unreviewed_extension"] = True
    shared = _FakeWM({"scene_outputs.image": {1: record}})

    contract = evaluate_scene_output_acceptance(
        kind="image",
        workflow_id="wf-unknown-receipt-key",
        agent_memory=None,
        shared_memory=shared,
        expected_scene_numbers=[1],
    )

    assert contract["accepted"] is False
    assert contract["rejected_scene_outputs"][0] == {
        "scene_number": 1,
        "reason_code": "scene_output_acceptance_receipt_unknown_keys",
        "detail": "unreviewed_extension",
    }


def test_video_scene_acceptance_rejects_failed_storage_for_stale_path():
    record = _scene_output_record(
        kind="video",
        scene_number=1,
        workflow_state_id="wf-stale-video",
        artifact_path="/tmp/stale-scene-1.mp4",
    )
    record["metadata"]["storage"] = {
        "status": "failed",
        "fallback_reason": "artifact_missing_after_persist",
    }
    shared = _FakeWM({"scene_outputs.video": {1: record}})

    contract = evaluate_scene_output_acceptance(
        kind="video",
        workflow_id="wf-stale-video",
        agent_memory=None,
        shared_memory=shared,
        expected_scene_numbers=[1],
    )

    assert contract["accepted"] is False
    assert contract["rejected_scene_outputs"][0] == {
        "scene_number": 1,
        "reason_code": "scene_output_storage_failed",
        "detail": "artifact_missing_after_persist",
    }


def _make_gate_result(**facts):
    merged_facts = {
        "records": 0,
        "checked": 0,
        "with_audio": 0,
        "without_audio": 0,
        "unknown": 0,
        "all_have_audio": False,
        "reason": "video_outputs_missing",
    }
    merged_facts.update(facts)
    result = "pass" if merged_facts.get("all_have_audio") else "fail"
    if merged_facts.get("reason") in {
        "video_outputs_missing",
        "workflow_id_missing",
    } or merged_facts.get("unknown", 0):
        result = "inconclusive"
    return {
        "gate_name": "workflow_video_audio_delivery",
        "gate_type": "system_evaluator",
        "result": result,
        "reason_code": merged_facts["reason"],
        "facts": merged_facts,
        "allowed_actions": [],
        "recommended_action": "continue" if result == "pass" else "inspect_runtime_gap",
    }


def _make_explicit_report(
    *,
    status="completed",
    boundary_event="",
    gate_triggers=None,
    artifacts=None,
    reflection=None,
):
    merged_reflection = {
        "completion_state": "completed" if status == "completed" else "partial",
        "reported_gaps": [],
        "reported_hints": [],
    }
    if isinstance(reflection, dict):
        merged_reflection.update(reflection)
    return {
        "status": status,
        "boundary_event": boundary_event,
        "gate_triggers": list(gate_triggers or []),
        "artifacts": list(artifacts or []),
        "reflection": merged_reflection,
    }


def _build_main_loop_runtime_harness(
    monkeypatch,
    *,
    gate_triggers,
    video_output=None,
    video_outputs=None,
    runtime_decision_mode="activate",
    retry_failed_step=False,
):
    shared_store = _FakeSharedMemoryStore()
    short_term = _FakeShortTermService(shared_store)
    memory_services = SimpleNamespace(
        short_term=short_term,
        global_service=object(),
        long_term=object(),
    )
    state_calls = {"trace": []}
    runtime_calls = {"open": [], "apply": [], "llm": []}

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

    state_adapter = SimpleNamespace(
        build_audio_contract=lambda **kwargs: {"policy": "adaptive", "need_global_bgm": False},
        append_replan_trace=lambda **kwargs: state_calls["trace"].append(kwargs),
    )
    observation_adapter = SimpleNamespace(
        build_audio_route_payload=lambda **kwargs: {
            "route_source": "control_plane.boundary_trigger",
            "route_id": f"{kwargs['workflow_state_id']}:boundary",
            "policy": "adaptive",
        },
        persist_audio_gate_observation=lambda **kwargs: None,
    )
    audio_gate = SimpleNamespace(
        evaluate_workflow_video_audio=lambda workflow_id: _make_gate_result(
            without_audio=1,
            reason="audio_missing_or_unknown",
        ),
        evaluate_global_bgm_mix_delivery=lambda workflow_id: {},
    )
    runtime_controller = OrchestrationRuntimeController(
        memory_services=memory_services,
        orchestration_state=state_adapter,
    )
    control_plane = OrchestrationControlPlane(
        memory_services=memory_services,
        protocol=OrchestrationProtocol(),
        orchestration_state=state_adapter,
        audio_delivery_gate=audio_gate,
        observation_adapter=observation_adapter,
        runtime_controller=runtime_controller,
    )
    original_open = control_plane.open_runtime_decision
    original_apply = control_plane.apply_runtime_decision

    def _open_runtime_decision(**kwargs):
        runtime_calls["open"].append(kwargs)
        return original_open(**kwargs)

    def _apply_runtime_decision(**kwargs):
        runtime_calls["apply"].append(kwargs)
        return original_apply(**kwargs)

    control_plane.open_runtime_decision = _open_runtime_decision
    control_plane.apply_runtime_decision = _apply_runtime_decision

    agent = object.__new__(OrchestratorAgent)
    agent.agent_type = AgentType.ORCHESTRATOR
    agent.agent_name = "orchestrator"
    agent.logger = logging.getLogger("test.orchestrator.main_loop")
    agent._memory_services = memory_services
    agent._orchestration_state = state_adapter
    agent._orchestration_observation = observation_adapter
    agent._audio_delivery_gate = audio_gate
    agent._runtime_controller = runtime_controller
    agent._orchestration_protocol = OrchestrationProtocol()
    agent._orchestration_control_plane = control_plane
    agent._context_contract_assembler = SimpleNamespace(
        assemble_agent_context=lambda **kwargs: {},
        build_script_review_boundary_draft=lambda **kwargs: {},
    )
    agent._workflow_completion_adapter = SimpleNamespace(
        build_persistence_payload=lambda workflow_id: {},
        publish_completed=_async_return_json({"final_video_url": ""}),
        publish_failed=_async_return_json({}),
        build_runtime_summary_output=lambda **kwargs: dict(kwargs),
    )
    agent._orchestration_runtime_resume_bootstrap_facade = SimpleNamespace(
        resolve_runtime_resume_context=lambda **kwargs: SimpleNamespace(
            runtime_session_id=None,
            runtime_session_status="",
            runtime_input_payload={},
            script_gate_id=None,
            latest_script_decision_exists=False,
            latest_script_decision_actor_type="",
            script_resume_action="",
            runtime_resume_checkpoint=None,
            resume_anchor_agent=None,
        )
    )
    agent._last_audio_route_payload = {}
    video_agent_output = video_output or {
        "success": True,
        "orchestration_report": _make_explicit_report(
            boundary_event="scene_video_completed",
            gate_triggers=list(gate_triggers),
            artifacts=[{"kind": "shared_fact", "ref": "scene_outputs.video"}],
        ),
    }
    configured_video_outputs = (
        list(video_outputs) if video_outputs is not None else [video_agent_output]
    )

    agent.agents = {
        AgentType.VIDEO_GENERATOR: _StubWorkflowAgent(
            "video_generator",
            configured_video_outputs,
        ),
        AgentType.AUDIO_GENERATOR: _StubWorkflowAgent(
            "audio_generator",
            [
                {
                    "success": True,
                    "orchestration_report": _make_explicit_report(
                        boundary_event="bgm_generated",
                        gate_triggers=[],
                        artifacts=[{"kind": "shared_fact", "ref": "project.background_music"}],
                    ),
                }
            ],
        ),
    }

    async def _update_progress(*args, **kwargs):
        return None

    async def _prepare_agent_context(
        workflow_data,
        agent_type,
        workflow_id,
        runtime_input_payload=None,
        execution_contract=None,
    ):
        return dict(workflow_data)

    async def _llm_select_candidate_agents(*args, **kwargs):
        return [AgentType.VIDEO_GENERATOR, AgentType.AUDIO_GENERATOR], "test-selection"

    async def _llm_decompose_tasks(*args, **kwargs):
        task_specs = {
            AgentType.VIDEO_GENERATOR: {
                "run": True,
                "order": 0,
                "scope": {"workflow_id": "wf-mainloop-1"},
            },
            AgentType.AUDIO_GENERATOR: {
                "run": False,
                "order": 1,
                "scope": {"workflow_id": "wf-mainloop-1"},
            },
        }
        return task_specs, {}

    async def _llm_decide_runtime_decision(**kwargs):
        runtime_calls["llm"].append(kwargs)
        if runtime_decision_mode == "raise_runtime_error":
            raise RuntimeError("synthetic_runtime_decision_failure")
        if runtime_decision_mode == "raise_agent_error":
            raise AgentError("synthetic_runtime_decision_failure")
        if runtime_decision_mode == "abort":
            return {
                "action": "abort",
                "reason": "synthetic_runtime_abort",
                "facts": {"gate_events": kwargs.get("gate_events") or []},
            }
        return {
            "action": "activate_from_standby",
            "target_agent": AgentType.AUDIO_GENERATOR,
            "reason": "audio_missing_or_unknown",
            "facts": {"gate_events": kwargs.get("gate_events") or []},
        }

    async def _publish_completed(**kwargs):
        return {"final_video_url": ""}

    async def _publish_failed(**kwargs):
        return {}

    async def _should_retry_step(*args, **kwargs):
        return retry_failed_step

    agent._get_video_audio_capability = lambda: {
        "provider": "",
        "supports_native_audio": False,
        "native_audio_param_name": "generate_audio",
        "native_audio_default_enabled": None,
    }
    agent._llm_select_candidate_agents = _llm_select_candidate_agents
    agent._llm_decompose_tasks = _llm_decompose_tasks
    agent._build_execution_queue = lambda task_specs, candidate_agents=None: [
        AgentType.VIDEO_GENERATOR
    ]
    agent._build_standby_agents = lambda task_specs, candidate_agents=None: [
        AgentType.AUDIO_GENERATOR
    ]
    agent._update_progress = _update_progress
    agent._prepare_agent_context = _prepare_agent_context
    agent._llm_decide_runtime_decision = _llm_decide_runtime_decision
    agent._should_retry_step = _should_retry_step
    agent._store_creative_guidance_from_output = _publish_failed
    agent._is_image_step_completed = lambda workflow_id: False
    agent._is_video_step_completed = lambda workflow_id: False
    agent._workflow_completion_adapter = SimpleNamespace(
        build_persistence_payload=lambda workflow_id: {},
        publish_completed=_publish_completed,
        publish_failed=_publish_failed,
        build_runtime_summary_output=lambda **kwargs: dict(kwargs),
    )

    return agent, _FakeWorkflowTask("wf-mainloop-1"), runtime_calls, state_calls


def test_runtime_audio_facts_detect_all_scene_audio(monkeypatch):
    evaluator = AudioDeliveryGateEvaluator(memory_services=SimpleNamespace(short_term=object()))

    wm = _build_video_wm(
        total_scenes=2,
        scene_records={
            1: {"scene_number": 1, "video_path": "/tmp/s1.mp4"},
            2: {"scene_number": 2, "video_path": "/tmp/s2.mp4"},
        },
    )
    monkeypatch.setattr(
        audio_gate_module, "get_mas_working_memory", lambda workflow_id, service=None: wm
    )
    monkeypatch.setattr(audio_gate_module.os.path, "exists", lambda _: True)
    monkeypatch.setattr(evaluator, "_probe_video_audio_stream", lambda _: True)

    facts = evaluator._collect_runtime_video_audio_facts("wf-1")
    assert facts["all_have_audio"] is True


def test_runtime_audio_facts_marks_unknown_when_path_unavailable(monkeypatch):
    evaluator = AudioDeliveryGateEvaluator(memory_services=SimpleNamespace(short_term=object()))

    wm = _build_video_wm(
        total_scenes=2,
        scene_records={
            1: {"scene_number": 1, "video_path": "/tmp/s1.mp4"},
            2: {"scene_number": 2, "video_url": "https://example.com/s2.mp4"},
        },
    )
    monkeypatch.setattr(
        audio_gate_module, "get_mas_working_memory", lambda workflow_id, service=None: wm
    )
    monkeypatch.setattr(audio_gate_module.os.path, "exists", lambda _: True)
    monkeypatch.setattr(evaluator, "_probe_video_audio_stream", lambda _: True)

    facts = evaluator._collect_runtime_video_audio_facts("wf-2")
    assert facts["all_have_audio"] is False
    assert facts["unknown"] >= 1


def test_runtime_audio_facts_detects_silent_scene(monkeypatch):
    evaluator = AudioDeliveryGateEvaluator(memory_services=SimpleNamespace(short_term=object()))

    wm = _build_video_wm(
        total_scenes=2,
        scene_records={
            1: {"scene_number": 1, "video_path": "/tmp/s1.mp4"},
            2: {"scene_number": 2, "video_path": "/tmp/s2.mp4"},
        },
    )
    monkeypatch.setattr(
        audio_gate_module, "get_mas_working_memory", lambda workflow_id, service=None: wm
    )
    monkeypatch.setattr(audio_gate_module.os.path, "exists", lambda _: True)
    monkeypatch.setattr(
        evaluator, "_probe_video_audio_stream", lambda path: path.endswith("s1.mp4")
    )

    facts = evaluator._collect_runtime_video_audio_facts("wf-3")
    assert facts["without_audio"] == 1


def test_evaluate_global_bgm_mix_delivery_returns_fail_when_mix_missing(monkeypatch):
    evaluator = AudioDeliveryGateEvaluator(memory_services=SimpleNamespace(short_term=object()))
    monkeypatch.setattr(
        audio_gate_module,
        "assess_composer_bgm_prereq",
        lambda workflow_id, service=None: {"eligible": True, "reason": None},
    )
    monkeypatch.setattr(
        audio_gate_module,
        "assess_composer_mix_delivery",
        lambda workflow_id, mix_type, service=None: {
            "subtask_state": "partial",
            "reason": "mix_receipt_missing",
        },
    )

    gate_result = evaluator.evaluate_global_bgm_mix_delivery("wf-bgm-1")
    assert gate_result["result"] == "fail"
    assert gate_result["recommended_action"] == "activate_bgm_mix"
    assert gate_result["facts"]["eligible"] is True
    assert gate_result["facts"]["delivery_complete"] is False


def test_orchestration_state_adapter_build_audio_contract_writes_no_compat_projection(monkeypatch):
    adapter = OrchestrationStateAdapter(memory_services=SimpleNamespace(short_term=object()))

    writes = {}

    def _capture_write(workflow_id, key, value, service=None):
        writes[key] = value

    monkeypatch.setattr(
        "app.services.orchestration_state_adapter.write_shared_fact", _capture_write
    )

    audio_contract = adapter.build_audio_contract(
        workflow_state_id="wf-plan-1",
        input_data={"audio_policy": "adaptive"},
    )

    assert audio_contract["policy"] == "adaptive"
    assert writes["workflow.contract.audio"]["policy"] == "adaptive"
    assert "workflow.diagnostics.compat.plan_snapshot" not in writes
    assert "workflow.diagnostics.compat.activation_pool_snapshot" not in writes
    assert "workflow.plan" not in writes
    assert "workflow.activation_pool" not in writes


def test_orchestration_state_adapter_rejects_forbidden_runtime_control_state_projection():
    adapter = OrchestrationStateAdapter(memory_services=SimpleNamespace(short_term=object()))

    with pytest.raises(ValueError, match="Forbidden runtime control state projection key"):
        adapter._write_workflow_projection(
            "wf-plan-guard",
            "workflow.session.current",
            {"status": "running"},
        )


def test_build_execution_queue_and_standby_agents_follow_llm_task_specs():
    agent = object.__new__(OrchestratorAgent)
    agent._orchestration_state = OrchestrationStateAdapter(
        memory_services=SimpleNamespace(short_term=object())
    )
    task_specs = {
        AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
        AgentType.VIDEO_GENERATOR: {"run": True, "order": 2},
        AgentType.VIDEO_COMPOSER: {"run": True, "order": 3},
        AgentType.AUDIO_GENERATOR: {"run": False, "order": 4},
        AgentType.QUALITY_CHECKER: {"run": True, "order": 5},
    }

    active = agent._build_execution_queue(
        task_specs,
        candidate_agents=[
            AgentType.CONCEPT_PLANNER,
            AgentType.VIDEO_GENERATOR,
            AgentType.VIDEO_COMPOSER,
            AgentType.AUDIO_GENERATOR,
            AgentType.QUALITY_CHECKER,
        ],
    )
    standby = agent._build_standby_agents(
        task_specs,
        candidate_agents=[
            AgentType.CONCEPT_PLANNER,
            AgentType.VIDEO_GENERATOR,
            AgentType.VIDEO_COMPOSER,
            AgentType.AUDIO_GENERATOR,
            AgentType.QUALITY_CHECKER,
        ],
    )

    assert [item.value for item in active] == [
        AgentType.CONCEPT_PLANNER.value,
        AgentType.VIDEO_GENERATOR.value,
        AgentType.VIDEO_COMPOSER.value,
        AgentType.QUALITY_CHECKER.value,
    ]
    assert [item.value for item in standby] == [AgentType.AUDIO_GENERATOR.value]


def test_build_execution_queue_falls_back_to_candidate_order_when_order_missing():
    queue = OrchestrationQueuePolicy.build_execution_queue(
        candidate_agents=[
            AgentType.VIDEO_GENERATOR,
            AgentType.VIDEO_COMPOSER,
            AgentType.QUALITY_CHECKER,
        ],
        task_specs={
            AgentType.VIDEO_GENERATOR: {"run": True},
            AgentType.QUALITY_CHECKER: {"run": True},
            AgentType.VIDEO_COMPOSER: {"run": True},
        },
    )

    assert queue == [
        AgentType.VIDEO_GENERATOR,
        AgentType.VIDEO_COMPOSER,
        AgentType.QUALITY_CHECKER,
    ]


def test_build_execution_queue_moves_script_consumers_after_script_writer():
    queue = OrchestrationQueuePolicy.build_execution_queue(
        candidate_agents=[
            AgentType.CONCEPT_PLANNER,
            AgentType.IMAGE_GENERATOR,
            AgentType.SCRIPT_WRITER,
            AgentType.QUALITY_CHECKER,
        ],
        task_specs={
            AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
            AgentType.IMAGE_GENERATOR: {"run": True, "order": 1},
            AgentType.SCRIPT_WRITER: {"run": True, "order": 5},
            AgentType.QUALITY_CHECKER: {"run": True, "order": 6},
        },
    )

    assert queue == [
        AgentType.CONCEPT_PLANNER,
        AgentType.SCRIPT_WRITER,
        AgentType.IMAGE_GENERATOR,
        AgentType.QUALITY_CHECKER,
    ]


def test_audio_agent_gate_is_no_longer_driven_by_workflow_plan(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.audio.plan")
    agent._last_audio_route_payload = {}
    agent._orchestration_observation = OrchestrationObservationAdapter(
        memory_services=SimpleNamespace(short_term=object())
    )

    def _read_shared_fact(workflow_id, key, default=None, service=None):
        if key == "workflow.contract.audio":
            return {"policy": "adaptive"}
        return {}

    monkeypatch.setattr(orchestrator_module, "read_shared_fact", _read_shared_fact)

    agent._emit_pre_dispatch_diagnostics(AgentType.AUDIO_GENERATOR, "wf-plan-2")
    assert agent._last_audio_route_payload == {}


def test_orchestrator_resolve_task_runtime_hints_uses_assignment_contract():
    runtime_hints = OrchestratorAgent._resolve_task_runtime_hints(
        {
            "runtime_hints": {"compose_mode": "bgm"},
        }
    )
    assert runtime_hints == {"compose_mode": "bgm"}


def test_audio_agent_gate_no_longer_emits_llm_task_spec_route_payload(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.audio.plan_missing")
    agent._last_audio_route_payload = {}
    agent._orchestration_observation = OrchestrationObservationAdapter(
        memory_services=SimpleNamespace(short_term=object())
    )

    monkeypatch.setattr(orchestrator_module, "read_shared_fact", lambda *args, **kwargs: {})
    agent._emit_pre_dispatch_diagnostics(AgentType.AUDIO_GENERATOR, "wf-5")
    assert agent._last_audio_route_payload == {}


def test_orchestration_protocol_requires_explicit_subagent_report():
    protocol = OrchestrationProtocol()

    with pytest.raises(
        OrchestrationProtocolError, match="must return explicit orchestration_report"
    ):
        protocol.build_subagent_report(
            workflow_state_id="wf-protocol-1",
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_result=_make_agent_result(),
            execution_id="exec-1",
        )


def test_orchestration_protocol_prefers_explicit_subagent_report():
    protocol = OrchestrationProtocol()

    report = protocol.build_subagent_report(
        workflow_state_id="wf-protocol-explicit",
        agent_type=AgentType.VIDEO_COMPOSER,
        agent_result=_make_agent_result(
            {
                "success": True,
                "reflection_summary": "compose ok",
            },
            report={
                "status": "completed",
                "boundary_event": "custom_boundary",
                "gate_triggers": ["workflow_video_audio_delivery"],
                "artifacts": [{"kind": "shared_fact", "ref": "custom.ref"}],
                "reflection": {
                    "completion_state": "completed",
                    "reported_gaps": [],
                    "reported_hints": ["prefer_custom_report"],
                },
            },
        ),
        execution_id="exec-explicit",
    )

    assert report["boundary_event"] == "custom_boundary"
    assert report["gate_triggers"] == ["workflow_video_audio_delivery"]
    assert report["artifacts"] == [{"kind": "shared_fact", "ref": "custom.ref"}]
    assert report["reflection"]["reported_hints"] == ["prefer_custom_report"]
    assert "summary" not in report["reflection"]


def test_orchestration_protocol_uses_explicit_report_status_as_single_outcome():
    protocol = OrchestrationProtocol()
    report = _make_explicit_report(
        boundary_event="scene_video_completed",
        gate_triggers=[],
    )
    report["reflection"]["completion_state"] = "partial"

    normalized = protocol.build_subagent_report(
        workflow_state_id="wf-protocol-single-outcome",
        agent_type=AgentType.VIDEO_GENERATOR,
        agent_result=_make_agent_result(
            {"success": False, "subtask_state": "partial"},
            report=report,
        ),
        execution_id="exec-single-outcome",
    )

    assert normalized["status"] == "completed"
    assert normalized["reflection"]["completion_state"] == "partial"


def test_orchestration_protocol_rejects_non_successful_report_status():
    protocol = OrchestrationProtocol()
    report = _make_explicit_report(
        boundary_event="scene_video_completed",
        gate_triggers=[],
    )
    report["status"] = "partial"

    with pytest.raises(OrchestrationProtocolError) as exc_info:
        protocol.build_subagent_report(
            workflow_state_id="wf-protocol-unsuccessful",
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_result=_make_agent_result({"success": True}, report=report),
            execution_id="exec-unsuccessful",
        )

    assert exc_info.value.reason_code == "orchestration_report_not_successful"


def test_agent_success_path_does_not_publish_before_runtime_boundary_succeeds():
    agent = object.__new__(OrchestratorAgent)
    agent.logger = logging.getLogger("test.orchestrator.success_boundary")
    agent._orchestration_protocol = OrchestrationProtocol()
    agent._current_execution_id = lambda: "exec-success-boundary"

    async def _fail_runtime_boundary(**_kwargs):
        raise AgentError("runtime boundary rejected the result")

    agent._finalize_successful_agent_runtime_boundary = _fail_runtime_boundary
    agent._store_composer_outputs = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("authoritative composer outputs must not be published")
    )
    workflow_results = {}
    workflow_data = {}
    subagent = _StubWorkflowAgent(
        "video_composer",
        [
            _make_agent_result(
                {
                    "success": True,
                    "final_video_path": "stale.mp4",
                    "final_video_url": "https://example.com/stale.mp4",
                },
                report=_make_explicit_report(
                    boundary_event="final_video_composed",
                    gate_triggers=[],
                ),
            )
        ],
    )

    with pytest.raises(AgentError) as exc_info:
        asyncio.run(
            agent._execute_agent_success_path(
                agent=subagent,
                request=AgentExecutionRequest(
                    task=AgentTaskReference(
                        task_id="task-success-boundary",
                        task_type="video_composition",
                    ),
                    agent_type=AgentType.VIDEO_COMPOSER.value,
                    input_data=JsonObjectPayload.empty(),
                    workflow_state_id="wf-success-boundary",
                ),
                workflow_state_id="wf-success-boundary",
                workflow_results=workflow_results,
                workflow_data=workflow_data,
                current_agent=AgentType.VIDEO_COMPOSER,
                audio_contract={},
                candidate_agents=[AgentType.VIDEO_COMPOSER],
                standby_agents=[],
                replan_count=0,
                max_replans=1,
                current_index=0,
                execution_queue=[AgentType.VIDEO_COMPOSER],
                task_specs={AgentType.VIDEO_COMPOSER: {"run": True, "order": 0}},
                conditional_task_specs={},
                runtime_session_id=None,
                runtime_node_key=None,
                attempt_id=None,
                lease_token=None,
                attempt_trigger_reason="initial",
                script_trigger_reason="initial",
            )
        )

    assert "runtime boundary rejected" in str(exc_info.value)
    assert workflow_results == {}
    assert workflow_data == {}


def test_runtime_success_boundary_consumes_authoritative_empty_standby_collection():
    agent = object.__new__(OrchestratorAgent)
    agent.logger = logging.getLogger("test.orchestrator.empty_standby")

    async def _runtime_cycle(**_kwargs):
        return {
            "runtime_decision": {
                "action": "activate_from_standby",
                "reason": "audio_missing_or_unknown",
            },
            "apply_result": {
                "status": "activated",
                "target_agent": AgentType.AUDIO_GENERATOR,
                "standby_agents": [],
                "replan_count": 1,
            },
            "decision_ack": {},
        }

    agent._evaluate_runtime_boundary_cycle = _runtime_cycle
    result = asyncio.run(
        agent._finalize_successful_agent_runtime_boundary(
            workflow_state_id="wf-empty-standby",
            task_id="task-empty-standby",
            current_agent=AgentType.VIDEO_GENERATOR,
            agent_result=_make_agent_result(
                {"success": True},
                report=_make_explicit_report(
                    boundary_event="scene_video_completed",
                    gate_triggers=["workflow_video_audio_delivery"],
                ),
            ),
            normalized_report=_make_explicit_report(
                boundary_event="scene_video_completed",
                gate_triggers=["workflow_video_audio_delivery"],
            ),
            agent_output={"success": True},
            audio_contract={},
            candidate_agents=[AgentType.VIDEO_GENERATOR, AgentType.AUDIO_GENERATOR],
            standby_agents=[AgentType.AUDIO_GENERATOR],
            replan_count=0,
            max_replans=1,
            current_index=0,
            execution_queue=[AgentType.VIDEO_GENERATOR, AgentType.AUDIO_GENERATOR],
            task_specs={
                AgentType.VIDEO_GENERATOR: {"run": True, "order": 0},
                AgentType.AUDIO_GENERATOR: {"run": False, "order": 1},
            },
            conditional_task_specs={},
            runtime_session_id=None,
            runtime_node_key=None,
            attempt_id=None,
            lease_token=None,
            attempt_trigger_reason="initial",
            script_trigger_reason="initial",
        )
    )

    assert result.standby_agents == ()
    assert result.replan_count == 1


@pytest.mark.parametrize(
    ("explicit_report", "match"),
    [
        (
            {
                "status": "completed",
                "boundary_event": 1,
                "gate_triggers": [],
                "artifacts": [],
                "reflection": {
                    "completion_state": "completed",
                    "reported_gaps": [],
                    "reported_hints": [],
                },
            },
            "field boundary_event must be a string",
        ),
        (
            {
                "status": "completed",
                "boundary_event": "scene_video_completed",
                "gate_triggers": "workflow_video_audio_delivery",
                "artifacts": [],
                "reflection": {
                    "completion_state": "completed",
                    "reported_gaps": [],
                    "reported_hints": [],
                },
            },
            "field gate_triggers must be list\\[str\\]",
        ),
        (
            {
                "status": "completed",
                "boundary_event": "scene_video_completed",
                "gate_triggers": ["workflow_video_audio_delivery"],
                "artifacts": ["scene_outputs.video"],
                "reflection": {
                    "completion_state": "completed",
                    "reported_gaps": [],
                    "reported_hints": [],
                },
            },
            "artifacts\\[0\\] must be a dict",
        ),
        (
            {
                "status": "completed",
                "boundary_event": "scene_video_completed",
                "gate_triggers": ["workflow_video_audio_delivery"],
                "artifacts": [],
                "reflection": [],
            },
            "field reflection must be a dict",
        ),
    ],
)
def test_orchestration_protocol_rejects_malformed_explicit_report_fields(
    explicit_report,
    match,
):
    protocol = OrchestrationProtocol()

    with pytest.raises(OrchestrationProtocolError, match=match):
        protocol.build_subagent_report(
            workflow_state_id="wf-protocol-malformed",
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_result=_make_agent_result(
                {"success": True},
                report=explicit_report,
            ),
            execution_id="exec-malformed",
        )


def test_orchestrator_runtime_boundary_cycle_fails_fast_on_protocol_violation():
    agent = object.__new__(OrchestratorAgent)
    agent.logger = logging.getLogger("test.orchestrator.protocol.fail_fast")
    agent._orchestration_protocol = OrchestrationProtocol()
    agent._runtime_controller = SimpleNamespace(
        collect_boundary_gate_events=lambda **kwargs: [],
        apply_runtime_decision=lambda **kwargs: {},
    )

    with pytest.raises(AgentError, match="Runtime protocol violated"):
        asyncio.run(
            agent._evaluate_runtime_boundary_cycle(
                workflow_state_id="wf-protocol-2",
                current_agent=AgentType.VIDEO_GENERATOR,
                agent_result=_make_agent_result(),
                audio_contract={"policy": "adaptive"},
                candidate_agents=[AgentType.VIDEO_GENERATOR, AgentType.AUDIO_GENERATOR],
                standby_agents=[AgentType.AUDIO_GENERATOR],
                replan_count=0,
                max_replans=2,
                current_index=0,
                execution_queue=[AgentType.VIDEO_GENERATOR],
                task_specs={AgentType.VIDEO_GENERATOR: {"run": True, "order": 0}},
                conditional_task_specs={},
            )
        )


def _build_legacy_decision_agent(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent.logger = logging.getLogger("test.orchestrator.legacy_decision")
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.prompt_manager = SimpleNamespace(render_template=lambda *args, **kwargs: "template")
    agent.get_system_instructions = lambda: {}
    monkeypatch.setattr(
        "app.agents.adapters.state.agent_outputs.assess_agent_delivery",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "app.agents.adapters.state.mas_state.build_mas_state_view",
        lambda *args, **kwargs: {},
    )
    return agent


def test_legacy_orchestrator_decision_rejects_malformed_json(monkeypatch):
    agent = _build_legacy_decision_agent(monkeypatch)

    async def _llm_function_call(**_kwargs):
        return {"approach": "text_response", "content": "not-json"}

    agent.llm_function_call = _llm_function_call

    with pytest.raises(AgentError, match="orchestrator_decision_parse_failed"):
        asyncio.run(agent._decide_next_step_llm(AgentType.VIDEO_GENERATOR, "wf-decision-1"))


def test_legacy_orchestrator_decision_rejects_failed_control_tool(monkeypatch):
    agent = _build_legacy_decision_agent(monkeypatch)

    async def _llm_function_call(**_kwargs):
        return {
            "approach": "function_call_plan",
            "tool_calls": [{"function": "orchestrator_control.proceed_next", "arguments": {}}],
        }

    async def _execute_tool_calls(_calls):
        return [
            {
                "tool": "orchestrator_control_proceed_next",
                "success": False,
                "error": "synthetic control failure",
            }
        ]

    agent.llm_function_call = _llm_function_call
    agent.execute_tool_calls = _execute_tool_calls

    with pytest.raises(AgentError, match="orchestrator_decision_tool_failed"):
        asyncio.run(agent._decide_next_step_llm(AgentType.VIDEO_GENERATOR, "wf-decision-2"))


def test_legacy_orchestrator_decision_rejects_empty_result(monkeypatch):
    agent = _build_legacy_decision_agent(monkeypatch)

    async def _llm_function_call(**_kwargs):
        return {"approach": "function_call_plan", "tool_calls": []}

    agent.llm_function_call = _llm_function_call

    with pytest.raises(AgentError, match="orchestrator_decision_missing"):
        asyncio.run(agent._decide_next_step_llm(AgentType.VIDEO_GENERATOR, "wf-decision-3"))


def test_orchestrator_runtime_boundary_cycle_skips_runtime_llm_without_gate_event():
    agent = object.__new__(OrchestratorAgent)
    agent.logger = logging.getLogger("test.orchestrator.no_gate")
    agent._orchestration_protocol = OrchestrationProtocol()
    agent._orchestration_control_plane = SimpleNamespace(
        open_runtime_decision=lambda **kwargs: {
            "status": "no_gate",
            "reason": "no_boundary_gate_event",
            "apply_result": {
                "status": "continue",
                "reason": "no_boundary_gate_event",
                "replan_count": 0,
            },
            "decision_ack": {},
        },
    )

    async def _should_not_run_llm(**kwargs):
        raise AssertionError("runtime LLM should not run without gate events")

    agent._llm_decide_runtime_decision = _should_not_run_llm

    result = asyncio.run(
        agent._evaluate_runtime_boundary_cycle(
            workflow_state_id="wf-no-gate-1",
            current_agent=AgentType.VIDEO_GENERATOR,
            agent_result=_make_agent_result(
                {"success": True},
                report=_make_explicit_report(
                    boundary_event="scene_video_completed",
                    gate_triggers=[],
                ),
            ),
            audio_contract={"policy": "adaptive"},
            candidate_agents=[AgentType.VIDEO_GENERATOR, AgentType.AUDIO_GENERATOR],
            standby_agents=[AgentType.AUDIO_GENERATOR],
            replan_count=0,
            max_replans=2,
            current_index=0,
            execution_queue=[AgentType.VIDEO_GENERATOR],
            task_specs={AgentType.VIDEO_GENERATOR: {"run": True, "order": 0}},
            conditional_task_specs={},
        )
    )

    assert result["runtime_decision"] == {}
    assert result["apply_result"]["status"] == "continue"
    assert result["apply_result"]["reason"] == "no_boundary_gate_event"
    assert result["decision_ack"] == {}


def test_orchestrator_runtime_boundary_cycle_delegates_open_and_apply_to_control_plane():
    agent = object.__new__(OrchestratorAgent)
    agent.logger = logging.getLogger("test.orchestrator.control_plane_handoff")
    agent._orchestration_protocol = OrchestrationProtocol()
    calls = {}

    def _open_runtime_decision(**kwargs):
        calls["open"] = kwargs
        return {
            "status": "ready",
            "decision_request": {
                "report": kwargs["report"],
                "gate_events": [
                    _make_gate_result(without_audio=1, reason="audio_missing_or_unknown")
                ],
            },
        }

    def _apply_runtime_decision(**kwargs):
        calls["apply"] = kwargs
        return {
            "apply_result": {
                "status": "activated",
                "target_agent": AgentType.AUDIO_GENERATOR,
                "standby_agents": [],
                "queue_changed": True,
                "replan_count": 1,
            },
            "decision_ack": {"contract_version": "v1"},
        }

    agent._orchestration_control_plane = SimpleNamespace(
        open_runtime_decision=_open_runtime_decision,
        apply_runtime_decision=_apply_runtime_decision,
    )

    async def _runtime_decision(**kwargs):
        calls["llm"] = kwargs
        return {
            "action": "activate_from_standby",
            "target_agent": AgentType.AUDIO_GENERATOR,
            "reason": "audio_missing_or_unknown",
            "facts": {"gate_events": kwargs["gate_events"]},
        }

    agent._llm_decide_runtime_decision = _runtime_decision

    result = asyncio.run(
        agent._evaluate_runtime_boundary_cycle(
            workflow_state_id="wf-handoff-1",
            current_agent=AgentType.VIDEO_GENERATOR,
            agent_result=_make_agent_result(
                {"success": True},
                report=_make_explicit_report(
                    boundary_event="scene_video_completed",
                    gate_triggers=["workflow_video_audio_delivery"],
                ),
            ),
            audio_contract={"policy": "adaptive"},
            candidate_agents=[
                AgentType.VIDEO_GENERATOR,
                AgentType.AUDIO_GENERATOR,
                AgentType.QUALITY_CHECKER,
            ],
            standby_agents=[AgentType.AUDIO_GENERATOR],
            replan_count=0,
            max_replans=2,
            current_index=0,
            execution_queue=[AgentType.VIDEO_GENERATOR, AgentType.QUALITY_CHECKER],
            task_specs={
                AgentType.VIDEO_GENERATOR: {"run": True, "order": 0},
                AgentType.AUDIO_GENERATOR: {"run": False, "order": 1},
                AgentType.QUALITY_CHECKER: {"run": True, "order": 2},
            },
            conditional_task_specs={},
        )
    )

    assert calls["open"]["current_agent"] == AgentType.VIDEO_GENERATOR
    assert calls["llm"]["gate_events"][0]["gate_name"] == "workflow_video_audio_delivery"
    assert calls["apply"]["runtime_decision"]["action"] == "activate_from_standby"
    assert result["apply_result"]["status"] == "activated"
    assert result["decision_ack"]["contract_version"] == "v1"


def test_orchestrator_main_loop_runs_runtime_true_chain_via_control_plane(monkeypatch):
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=["workflow_video_audio_delivery"],
    )

    result = asyncio.run(_run_main_loop(agent, task))

    assert result["status"] == "completed"
    assert len(runtime_calls["open"]) == 2
    assert len(runtime_calls["llm"]) == 1
    assert len(runtime_calls["apply"]) == 1
    assert AgentType.AUDIO_GENERATOR.value in result["results"]
    assert len(state_calls["trace"]) == 1
    assert state_calls["trace"][0]["record"]["target_agent"] == AgentType.AUDIO_GENERATOR.value


def test_orchestrator_main_loop_skips_runtime_llm_when_no_gate_event(monkeypatch):
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=[],
    )

    result = asyncio.run(_run_main_loop(agent, task))

    assert result["status"] == "completed"
    assert len(runtime_calls["open"]) == 1
    assert runtime_calls["llm"] == []
    assert runtime_calls["apply"] == []
    assert AgentType.AUDIO_GENERATOR.value not in result["results"]
    assert state_calls["trace"] == []


def test_orchestrator_main_loop_fails_fast_when_runtime_decision_errors(monkeypatch):
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=["workflow_video_audio_delivery"],
        runtime_decision_mode="raise_runtime_error",
    )

    with pytest.raises(
        AgentError, match="Runtime decision evaluation failed: synthetic_runtime_decision_failure"
    ):
        asyncio.run(_run_main_loop(agent, task))

    assert len(runtime_calls["open"]) == 1
    assert len(runtime_calls["llm"]) == 1
    assert runtime_calls["apply"] == []
    assert state_calls["trace"] == []


def test_orchestrator_main_loop_fails_fast_when_report_missing(monkeypatch):
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=["workflow_video_audio_delivery"],
        video_output={"success": True},
    )

    with pytest.raises(AgentError, match="Runtime protocol violated"):
        asyncio.run(_run_main_loop(agent, task))

    assert runtime_calls["open"] == []
    assert runtime_calls["llm"] == []
    assert runtime_calls["apply"] == []
    assert state_calls["trace"] == []


def test_orchestrator_main_loop_fails_fast_when_report_field_malformed(monkeypatch):
    malformed_output = {
        "success": True,
        "orchestration_report": _make_explicit_report(
            boundary_event="scene_video_completed",
            gate_triggers=[],
        ),
    }
    malformed_output["orchestration_report"]["gate_triggers"] = "workflow_video_audio_delivery"
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=[],
        video_output=malformed_output,
    )

    with pytest.raises(
        AgentError,
        match="Runtime protocol violated: Subagent video_generator orchestration_report field gate_triggers must be list\\[str\\]",
    ):
        asyncio.run(_run_main_loop(agent, task))

    assert runtime_calls["open"] == []
    assert runtime_calls["llm"] == []
    assert runtime_calls["apply"] == []
    assert state_calls["trace"] == []


def test_orchestrator_video_retry_runs_the_same_runtime_gate_cycle(monkeypatch):
    retry_output = {
        "success": True,
        "orchestration_report": _make_explicit_report(
            boundary_event="scene_video_completed",
            gate_triggers=["workflow_video_audio_delivery"],
            artifacts=[{"kind": "shared_fact", "ref": "scene_outputs.video"}],
        ),
    }
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=[],
        video_outputs=[RuntimeError("temporary video failure"), retry_output],
        retry_failed_step=True,
    )

    result = asyncio.run(_run_main_loop(agent, task))

    assert result["status"] == "completed"
    assert runtime_calls["open"][0]["current_agent"] == AgentType.VIDEO_GENERATOR
    assert runtime_calls["open"][0]["report"]["gate_triggers"] == ["workflow_video_audio_delivery"]
    assert len(runtime_calls["llm"]) == 1
    assert len(runtime_calls["apply"]) == 1
    assert len(state_calls["trace"]) == 1
    assert agent.agents[AgentType.VIDEO_GENERATOR]._outputs == []
    assert agent.agents[AgentType.AUDIO_GENERATOR]._outputs == []


def test_orchestrator_main_loop_aborts_workflow_on_runtime_abort_decision(monkeypatch):
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=["workflow_video_audio_delivery"],
        runtime_decision_mode="abort",
    )

    with pytest.raises(
        AgentError, match="Workflow halted by runtime decision: synthetic_runtime_abort"
    ):
        asyncio.run(_run_main_loop(agent, task))

    assert len(runtime_calls["open"]) == 1
    assert len(runtime_calls["llm"]) == 1
    assert len(runtime_calls["apply"]) == 1
    assert len(state_calls["trace"]) == 1
    assert state_calls["trace"][0]["record"]["action"] == "abort"


def test_orchestrator_main_loop_fails_fast_when_scheduled_agent_lacks_task_spec(monkeypatch):
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=[],
    )

    async def _missing_audio_task_spec(*args, **kwargs):
        return {
            AgentType.VIDEO_GENERATOR: {
                "run": True,
                "order": 0,
                "scope": {"workflow_id": "wf-mainloop-1"},
            }
        }, {}

    agent._llm_decompose_tasks = _missing_audio_task_spec
    agent._build_execution_queue = lambda task_specs, candidate_agents=None: [
        AgentType.VIDEO_GENERATOR,
        AgentType.AUDIO_GENERATOR,
    ]

    with pytest.raises(AgentError, match="Missing task_spec for scheduled agent: audio_generator"):
        asyncio.run(_run_main_loop(agent, task))

    assert len(runtime_calls["open"]) == 1
    assert runtime_calls["llm"] == []
    assert runtime_calls["apply"] == []
    assert state_calls["trace"] == []


def test_orchestrator_main_loop_fails_fast_when_gate_trigger_unknown(monkeypatch):
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=["unknown_runtime_gate"],
    )

    with pytest.raises(
        AgentError,
        match="Runtime control-plane violated: Unknown gate trigger: unknown_runtime_gate",
    ):
        asyncio.run(_run_main_loop(agent, task))

    assert len(runtime_calls["open"]) == 1
    assert runtime_calls["llm"] == []
    assert runtime_calls["apply"] == []
    assert state_calls["trace"] == []


def test_orchestrator_main_loop_fails_fast_when_gate_trigger_unauthorized(monkeypatch):
    agent, task, runtime_calls, state_calls = _build_main_loop_runtime_harness(
        monkeypatch,
        gate_triggers=["workflow_global_bgm_mix_delivery"],
    )

    with pytest.raises(
        AgentError,
        match=(
            "Runtime control-plane violated: Unauthorized gate trigger: "
            "workflow_global_bgm_mix_delivery"
        ),
    ):
        asyncio.run(_run_main_loop(agent, task))

    assert len(runtime_calls["open"]) == 1
    assert runtime_calls["llm"] == []
    assert runtime_calls["apply"] == []
    assert state_calls["trace"] == []


def test_control_plane_open_runtime_decision_collects_boundary_gate_events_for_video(monkeypatch):
    observation_adapter = SimpleNamespace(
        build_audio_route_payload=lambda **kwargs: {
            "route_source": "control_plane.boundary_trigger",
            "route_id": "wf-protocol-1:boundary",
            "policy": "adaptive",
        },
        persist_audio_gate_observation=lambda **kwargs: None,
    )
    audio_gate = SimpleNamespace(
        evaluate_workflow_video_audio=lambda workflow_id: _make_gate_result(
            without_audio=1,
            reason="audio_missing_or_unknown",
        ),
        evaluate_global_bgm_mix_delivery=lambda workflow_id: {
            "gate_name": "workflow_global_bgm_mix_delivery",
            "result": "pass",
            "reason_code": "all_good",
            "facts": {},
        },
    )
    control_plane = OrchestrationControlPlane(
        memory_services=SimpleNamespace(short_term=object()),
        protocol=OrchestrationProtocol(),
        orchestration_state=OrchestrationStateAdapter(
            memory_services=SimpleNamespace(short_term=object())
        ),
        audio_delivery_gate=audio_gate,
        observation_adapter=observation_adapter,
        runtime_controller=SimpleNamespace(apply_runtime_decision=lambda **kwargs: {}),
    )

    payload = control_plane.open_runtime_decision(
        workflow_state_id="wf-protocol-1",
        current_agent=AgentType.VIDEO_GENERATOR,
        standby_agents=[AgentType.AUDIO_GENERATOR],
        report={
            "boundary_event": "scene_video_completed",
            "gate_triggers": ["workflow_video_audio_delivery"],
            "agent_type": AgentType.VIDEO_GENERATOR.value,
        },
        audio_contract={"need_global_bgm": False},
        replan_count=0,
        max_replans=2,
        execution_id="exec-1",
    )

    assert payload is not None
    assert payload["status"] == "ready"
    assert len(payload["decision_request"]["gate_events"]) == 1
    assert (
        payload["decision_request"]["gate_events"][0]["gate_name"]
        == "workflow_video_audio_delivery"
    )


def test_control_plane_open_runtime_decision_collects_authorized_bgm_mix_gate():
    control_plane = OrchestrationControlPlane(
        memory_services=SimpleNamespace(short_term=object()),
        protocol=OrchestrationProtocol(),
        orchestration_state=OrchestrationStateAdapter(
            memory_services=SimpleNamespace(short_term=object())
        ),
        audio_delivery_gate=SimpleNamespace(
            evaluate_workflow_video_audio=lambda workflow_id: {},
            evaluate_global_bgm_mix_delivery=lambda workflow_id: {
                "gate_name": "workflow_global_bgm_mix_delivery",
                "result": "fail",
                "reason_code": "mix_receipt_missing",
                "facts": {"eligible": True, "delivery_complete": False},
            },
        ),
        observation_adapter=SimpleNamespace(
            build_audio_route_payload=lambda **kwargs: {},
            persist_audio_gate_observation=lambda **kwargs: None,
        ),
        runtime_controller=SimpleNamespace(apply_runtime_decision=lambda **kwargs: {}),
    )

    payload = control_plane.open_runtime_decision(
        workflow_state_id="wf-protocol-bgm-gate",
        current_agent=AgentType.VIDEO_COMPOSER,
        standby_agents=[AgentType.AUDIO_GENERATOR],
        report={
            "boundary_event": "compose_completed",
            "gate_triggers": ["workflow_global_bgm_mix_delivery"],
            "agent_type": AgentType.VIDEO_COMPOSER.value,
        },
        audio_contract={"need_global_bgm": True},
        replan_count=0,
        max_replans=2,
        execution_id="exec-bgm-gate",
    )

    assert payload["status"] == "ready"
    assert (
        payload["decision_request"]["gate_events"][0]["gate_name"]
        == "workflow_global_bgm_mix_delivery"
    )


def test_control_plane_open_runtime_decision_skips_gate_collection_for_non_boundary_agent(
    monkeypatch,
):
    audio_gate = SimpleNamespace(
        evaluate_workflow_video_audio=lambda workflow_id: (_ for _ in ()).throw(
            AssertionError("audio gate should not run")
        ),
        evaluate_global_bgm_mix_delivery=lambda workflow_id: (_ for _ in ()).throw(
            AssertionError("bgm gate should not run")
        ),
    )
    control_plane = OrchestrationControlPlane(
        memory_services=SimpleNamespace(short_term=object()),
        protocol=OrchestrationProtocol(),
        orchestration_state=OrchestrationStateAdapter(
            memory_services=SimpleNamespace(short_term=object())
        ),
        audio_delivery_gate=audio_gate,
        observation_adapter=SimpleNamespace(
            build_audio_route_payload=lambda **kwargs: {},
            persist_audio_gate_observation=lambda **kwargs: None,
        ),
        runtime_controller=SimpleNamespace(apply_runtime_decision=lambda **kwargs: {}),
    )

    payload = control_plane.open_runtime_decision(
        workflow_state_id="wf-protocol-2",
        current_agent=AgentType.CONCEPT_PLANNER,
        standby_agents=[],
        report={
            "boundary_event": "",
            "gate_triggers": [],
            "agent_type": AgentType.CONCEPT_PLANNER.value,
        },
        audio_contract={"need_global_bgm": True},
        replan_count=0,
        max_replans=2,
        execution_id="exec-2",
    )

    assert payload["status"] == "no_gate"
    assert payload["apply_result"]["reason"] == "no_boundary_gate_event"


def test_control_plane_open_runtime_decision_fails_fast_on_unknown_gate_trigger():
    control_plane = OrchestrationControlPlane(
        memory_services=SimpleNamespace(short_term=object()),
        protocol=OrchestrationProtocol(),
        orchestration_state=OrchestrationStateAdapter(
            memory_services=SimpleNamespace(short_term=object())
        ),
        audio_delivery_gate=SimpleNamespace(
            evaluate_workflow_video_audio=lambda workflow_id: {},
            evaluate_global_bgm_mix_delivery=lambda workflow_id: {},
        ),
        observation_adapter=SimpleNamespace(
            build_audio_route_payload=lambda **kwargs: {},
            persist_audio_gate_observation=lambda **kwargs: None,
        ),
        runtime_controller=SimpleNamespace(apply_runtime_decision=lambda **kwargs: {}),
    )

    with pytest.raises(
        OrchestrationControlPlaneError, match="Unknown gate trigger: unknown_runtime_gate"
    ):
        control_plane.open_runtime_decision(
            workflow_state_id="wf-protocol-unknown-gate",
            current_agent=AgentType.VIDEO_GENERATOR,
            standby_agents=[AgentType.AUDIO_GENERATOR],
            report={
                "boundary_event": "scene_video_completed",
                "gate_triggers": ["unknown_runtime_gate"],
                "agent_type": AgentType.VIDEO_GENERATOR.value,
            },
            audio_contract={"need_global_bgm": False},
            replan_count=0,
            max_replans=2,
            execution_id="exec-unknown-gate",
        )


def test_control_plane_open_runtime_decision_fails_fast_on_unauthorized_known_gate_trigger():
    control_plane = OrchestrationControlPlane(
        memory_services=SimpleNamespace(short_term=object()),
        protocol=OrchestrationProtocol(),
        orchestration_state=OrchestrationStateAdapter(
            memory_services=SimpleNamespace(short_term=object())
        ),
        audio_delivery_gate=SimpleNamespace(
            evaluate_workflow_video_audio=lambda workflow_id: (_ for _ in ()).throw(
                AssertionError("known gate handler should not run when authority check fails")
            ),
            evaluate_global_bgm_mix_delivery=lambda workflow_id: (_ for _ in ()).throw(
                AssertionError("known gate handler should not run when authority check fails")
            ),
        ),
        observation_adapter=SimpleNamespace(
            build_audio_route_payload=lambda **kwargs: {},
            persist_audio_gate_observation=lambda **kwargs: None,
        ),
        runtime_controller=SimpleNamespace(apply_runtime_decision=lambda **kwargs: {}),
    )

    with pytest.raises(
        OrchestrationControlPlaneError,
        match=(
            "Unauthorized gate trigger: workflow_global_bgm_mix_delivery "
            "for agent=video_generator boundary_event=scene_video_completed"
        ),
    ):
        control_plane.open_runtime_decision(
            workflow_state_id="wf-protocol-unauthorized-gate",
            current_agent=AgentType.VIDEO_GENERATOR,
            standby_agents=[AgentType.AUDIO_GENERATOR],
            report={
                "boundary_event": "scene_video_completed",
                "gate_triggers": ["workflow_global_bgm_mix_delivery"],
                "agent_type": AgentType.VIDEO_GENERATOR.value,
            },
            audio_contract={"need_global_bgm": True},
            replan_count=0,
            max_replans=2,
            execution_id="exec-unauthorized-gate",
        )


def test_orchestration_protocol_builds_runtime_decision_request():
    protocol = OrchestrationProtocol()

    payload = protocol.build_runtime_decision_request(
        workflow_state_id="wf-decision-1",
        current_agent=AgentType.VIDEO_GENERATOR,
        standby_agents=[AgentType.AUDIO_GENERATOR],
        report={"boundary_event": "scene_video_completed"},
        gate_events=[_make_gate_result(without_audio=1, reason="audio_missing_or_unknown")],
        replan_count=1,
        max_replans=2,
    )

    assert payload["current_agent"] == AgentType.VIDEO_GENERATOR.value
    assert payload["standby_candidates"] == [AgentType.AUDIO_GENERATOR.value]
    assert payload["replan_budget"] == {"used": 1, "max": 2}


def test_llm_runtime_decision_activates_audio_from_standby(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.replan.activate")
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json(
            {"action": "activate_from_standby", "target_agent": AgentType.AUDIO_GENERATOR.value}
        )
    )

    decision = asyncio.run(
        agent._llm_decide_runtime_decision(
            workflow_state_id="wf-replan-1",
            current_agent=AgentType.VIDEO_GENERATOR,
            standby_agents=[AgentType.AUDIO_GENERATOR],
            report={"agent_type": AgentType.VIDEO_GENERATOR.value},
            gate_events=[
                _make_gate_result(
                    without_audio=1,
                    reason="audio_missing_or_unknown",
                )
            ],
            replan_count=0,
            max_replans=2,
        )
    )

    assert decision["action"] == "activate_from_standby"
    assert decision["target_agent"] == AgentType.AUDIO_GENERATOR
    assert len(decision["facts"]["gate_events"]) == 1


def test_llm_candidate_selection_returns_dynamic_subset(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.candidate_selection")
    agent.prompt_manager = get_prompt_manager()
    agent.get_system_instructions = lambda: {"primary_role": "工作流编排器"}
    agent.agents = {
        AgentType.VIDEO_GENERATOR: object(),
        AgentType.VOICE_SYNTHESIZER: object(),
        AgentType.VIDEO_COMPOSER: object(),
    }
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json(
            {
                "candidate_agents": [
                    AgentType.VIDEO_GENERATOR.value,
                    AgentType.VIDEO_COMPOSER.value,
                ],
                "selection_rationale": "native audio is sufficient for this task",
            }
        )
    )

    selected, rationale = asyncio.run(
        agent._llm_select_candidate_agents(
            workflow_data={
                "user_prompt": "make a silent scenic video",
                "audio_contract": {"allow_silence": True, "need_voiceover": False},
                "audio_capability": {"supports_native_audio": True},
            },
            workflow_id="wf-candidate-selection-1",
        )
    )

    assert selected == [AgentType.VIDEO_GENERATOR, AgentType.VIDEO_COMPOSER]
    assert rationale == "native audio is sufficient for this task"


def test_llm_candidate_selection_rejects_unknown_agent(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.candidate_selection.unknown")
    agent.prompt_manager = get_prompt_manager()
    agent.get_system_instructions = lambda: {"primary_role": "工作流编排器"}
    agent.agents = {
        AgentType.VIDEO_GENERATOR: object(),
        AgentType.VIDEO_COMPOSER: object(),
    }
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json(
            {
                "candidate_agents": [
                    AgentType.VIDEO_GENERATOR.value,
                    "nonexistent_agent",
                ],
                "selection_rationale": "invalid result",
            }
        )
    )

    with pytest.raises(AgentError, match="unknown agents"):
        asyncio.run(
            agent._llm_select_candidate_agents(
                workflow_data={
                    "user_prompt": "make a video",
                    "audio_contract": {"allow_silence": True},
                    "audio_capability": {"supports_native_audio": False},
                },
                workflow_id="wf-candidate-selection-unknown",
            )
        )


def test_llm_task_decomposition_fails_fast_when_expected_agent_missing(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.decompose.coverage")
    agent.prompt_manager = get_prompt_manager()
    agent.get_system_instructions = lambda: {"primary_role": "工作流编排器"}
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json(
            {
                "agents": [
                    {
                        "agent": AgentType.VIDEO_GENERATOR.value,
                        "run": True,
                        "mission": "generate scene video segments",
                        "deliverable": "scene video clips",
                        "constraints": [],
                        "order": 0,
                        "runtime_hints": {},
                    }
                ],
            }
        )
    )

    with pytest.raises(
        AgentError,
        match="LLM task decomposition is required but failed: LLM task decomposition missing task_specs for agents: audio_generator",
    ):
        asyncio.run(
            agent._llm_decompose_tasks(
                {"user_prompt": "make a short video"},
                "wf-coverage-1",
                candidate_agents=[AgentType.VIDEO_GENERATOR, AgentType.AUDIO_GENERATOR],
            )
        )


def test_llm_task_decomposition_rejects_non_candidate_agent_spec(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.decompose.non_candidate")
    agent.prompt_manager = get_prompt_manager()
    agent.get_system_instructions = lambda: {"primary_role": "工作流编排器"}
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json(
            {
                "agents": [
                    {
                        "agent": AgentType.VIDEO_GENERATOR.value,
                        "run": True,
                        "mission": "generate scene video segments",
                        "deliverable": "scene video clips",
                        "constraints": [],
                        "order": 0,
                        "runtime_hints": {},
                    },
                    {
                        "agent": AgentType.VOICE_SYNTHESIZER.value,
                        "run": False,
                        "mission": "produce narration",
                        "deliverable": "voice track",
                        "constraints": [],
                        "order": 1,
                        "runtime_hints": {},
                    },
                ],
            }
        )
    )

    with pytest.raises(
        AgentError,
        match="non-candidate agents: voice_synthesizer",
    ):
        asyncio.run(
            agent._llm_decompose_tasks(
                {"user_prompt": "make a short video"},
                "wf-non-candidate-1",
                candidate_agents=[AgentType.VIDEO_GENERATOR],
            )
        )


def test_llm_task_decomposition_rejects_task_spec_type_coercion(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.decompose.types")
    agent.prompt_manager = get_prompt_manager()
    agent.get_system_instructions = lambda: {"primary_role": "工作流编排器"}
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json(
            {
                "agents": [
                    {
                        "agent": AgentType.VIDEO_GENERATOR.value,
                        "run": True,
                        "mission": {"text": "generate scene video segments"},
                        "deliverable": "scene video clips",
                        "constraints": [],
                        "order": 0,
                        "runtime_hints": {},
                    }
                ],
                "conditional_tasks": [],
            }
        )
    )

    with pytest.raises(AgentError, match="continuation_spec_field_type_invalid"):
        asyncio.run(
            agent._llm_decompose_tasks(
                {"user_prompt": "make a short video"},
                "wf-invalid-task-spec-type",
                candidate_agents=[AgentType.VIDEO_GENERATOR],
            )
        )


def test_llm_task_decomposition_preserves_runtime_hints(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.decompose.runtime_hints")
    agent.prompt_manager = get_prompt_manager()
    agent.get_system_instructions = lambda: {"primary_role": "工作流编排器"}
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json(
            {
                "agents": [
                    {
                        "agent": AgentType.VIDEO_GENERATOR.value,
                        "run": True,
                        "mission": "generate native-audio scene videos",
                        "deliverable": "scene video clips with native audio",
                        "constraints": [],
                        "order": 0,
                        "runtime_hints": {"generate_audio": True},
                    },
                    {
                        "agent": AgentType.VIDEO_COMPOSER.value,
                        "run": False,
                        "mission": "compose final video when activated",
                        "deliverable": "final composed video",
                        "constraints": [],
                        "order": 1,
                        "runtime_hints": {"compose_mode": "compose"},
                    },
                ],
                "conditional_tasks": [
                    {
                        "task_id": "bgm_mix",
                        "agent": AgentType.VIDEO_COMPOSER.value,
                        "mission": "mix background music into the composed video",
                        "deliverable": "bgm-mixed final video",
                        "constraints": [],
                        "trigger": "global_bgm_missing",
                        "runtime_hints": {"compose_mode": "bgm"},
                    }
                ],
            }
        )
    )

    task_specs, conditional_task_specs = asyncio.run(
        agent._llm_decompose_tasks(
            {"user_prompt": "make a short video"},
            "wf-runtime-overrides-1",
            candidate_agents=[AgentType.VIDEO_GENERATOR, AgentType.VIDEO_COMPOSER],
        )
    )

    assert task_specs[AgentType.VIDEO_GENERATOR]["runtime_hints"] == {"generate_audio": True}
    assert task_specs[AgentType.VIDEO_COMPOSER]["runtime_hints"] == {"compose_mode": "compose"}
    assert conditional_task_specs["bgm_mix"]["runtime_hints"] == {"compose_mode": "bgm"}


def test_llm_runtime_decision_fails_fast_when_action_missing(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.replan.missing_action")
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json({"reason": "missing_action"})
    )

    with pytest.raises(AgentError, match="Runtime replan missing action"):
        asyncio.run(
            agent._llm_decide_runtime_decision(
                workflow_state_id="wf-replan-missing-action",
                current_agent=AgentType.VIDEO_GENERATOR,
                standby_agents=[AgentType.AUDIO_GENERATOR],
                report={"agent_type": AgentType.VIDEO_GENERATOR.value},
                gate_events=[_make_gate_result(without_audio=1, reason="audio_missing_or_unknown")],
                replan_count=0,
                max_replans=2,
            )
        )


def test_llm_runtime_decision_fails_fast_when_llm_call_errors(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.replan.fail_fast")

    async def _raise_failure(*args, **kwargs):
        raise RuntimeError("synthetic_provider_failure")

    agent.get_llm = lambda role: SimpleNamespace(chat_completion=_raise_failure)

    with pytest.raises(
        AgentError, match="Runtime replan LLM decision failed: synthetic_provider_failure"
    ):
        asyncio.run(
            agent._llm_decide_runtime_decision(
                workflow_state_id="wf-replan-fail-1",
                current_agent=AgentType.VIDEO_GENERATOR,
                standby_agents=[AgentType.AUDIO_GENERATOR],
                report={"agent_type": AgentType.VIDEO_GENERATOR.value},
                gate_events=[
                    _make_gate_result(
                        without_audio=1,
                        reason="audio_missing_or_unknown",
                    )
                ],
                replan_count=0,
                max_replans=2,
            )
        )


def test_llm_runtime_decision_aborts_when_budget_exhausted(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.replan.abort")
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json(
            {"action": "activate_from_standby", "target_agent": AgentType.AUDIO_GENERATOR.value}
        )
    )

    decision = asyncio.run(
        agent._llm_decide_runtime_decision(
            workflow_state_id="wf-replan-2",
            current_agent=AgentType.VIDEO_GENERATOR,
            standby_agents=[AgentType.AUDIO_GENERATOR],
            report={"agent_type": AgentType.VIDEO_GENERATOR.value},
            gate_events=[
                _make_gate_result(
                    without_audio=1,
                    reason="audio_missing_or_unknown",
                )
            ],
            replan_count=2,
            max_replans=2,
        )
    )

    assert decision["action"] == "abort"
    assert decision["reason"] == "replan_budget_exhausted"


def test_llm_runtime_decision_activates_composer_for_bgm_mix(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=object())
    agent.logger = logging.getLogger("test.orchestrator.replan.bgm")
    agent.get_llm = lambda role: SimpleNamespace(
        chat_completion=_async_return_json(
            {"action": "activate_from_standby", "target_agent": AgentType.VIDEO_COMPOSER.value}
        )
    )

    decision = asyncio.run(
        agent._llm_decide_runtime_decision(
            workflow_state_id="wf-replan-bgm-1",
            current_agent=AgentType.AUDIO_GENERATOR,
            standby_agents=[AgentType.VIDEO_COMPOSER],
            report={"agent_type": AgentType.AUDIO_GENERATOR.value},
            gate_events=[
                _make_gate_result(
                    all_have_audio=True,
                    reason="all_have_audio",
                ),
                {
                    "gate_name": "workflow_global_bgm_mix_delivery",
                    "result": "fail",
                    "reason_code": "mix_receipt_missing",
                    "facts": {
                        "eligible": True,
                        "delivery_complete": False,
                        "bgm_prereq": {"eligible": True, "reason": None},
                        "bgm_delivery": {
                            "subtask_state": "partial",
                            "reason": "mix_receipt_missing",
                        },
                    },
                },
            ],
            replan_count=0,
            max_replans=2,
        )
    )

    assert decision["action"] == "activate_from_standby"
    assert decision["target_agent"] == AgentType.VIDEO_COMPOSER
    assert len(decision["facts"]["gate_events"]) == 2


def test_state_adapter_appends_replan_trace_without_compat_projection(monkeypatch):
    adapter = OrchestrationStateAdapter(memory_services=SimpleNamespace(short_term=object()))

    writes = {}

    def _capture_write(workflow_id, key, value, service=None):
        writes[key] = value

    monkeypatch.setattr(
        "app.services.orchestration_state_adapter.write_shared_fact", _capture_write
    )
    monkeypatch.setattr(
        "app.services.orchestration_state_adapter.read_shared_fact",
        lambda *args, **kwargs: [],
    )

    adapter.append_replan_trace(
        workflow_state_id="wf-replan-3",
        record={
            "action": "activate_from_standby",
            "target_agent": AgentType.AUDIO_GENERATOR.value,
            "reason": "contract_disallow_silence_runtime_gap",
        },
    )

    assert writes["workflow.replan_trace"][-1]["action"] == "activate_from_standby"
    assert writes["workflow.replan_trace"][-1]["target_agent"] == AgentType.AUDIO_GENERATOR.value
    assert writes["workflow.replan_trace"][-1]["reason"] == "contract_disallow_silence_runtime_gap"
    assert "workflow.diagnostics.compat.audio_route_snapshot" not in writes
    assert "workflow.diagnostics.compat.activation_pool_snapshot" not in writes
    assert "workflow.audio_route" not in writes
    assert "workflow.activation_pool" not in writes


def test_queue_policy_build_execution_queue_requires_explicit_task_spec():
    queue = OrchestrationQueuePolicy.build_execution_queue(
        candidate_agents=[
            AgentType.VIDEO_GENERATOR,
            AgentType.AUDIO_GENERATOR,
            AgentType.QUALITY_CHECKER,
        ],
        task_specs={
            AgentType.VIDEO_GENERATOR: {"run": True, "order": 0},
            AgentType.AUDIO_GENERATOR: {"run": False, "order": 1},
        },
    )
    standby = OrchestrationQueuePolicy.build_standby_agents(
        candidate_agents=[
            AgentType.VIDEO_GENERATOR,
            AgentType.AUDIO_GENERATOR,
            AgentType.QUALITY_CHECKER,
        ],
        task_specs={
            AgentType.VIDEO_GENERATOR: {"run": True, "order": 0},
            AgentType.AUDIO_GENERATOR: {"run": False, "order": 1},
        },
    )

    assert queue == [AgentType.VIDEO_GENERATOR]
    assert standby == [AgentType.AUDIO_GENERATOR]


def test_queue_policy_insert_agent_into_execution_queue_respects_task_spec_order():
    execution_queue = [
        AgentType.CONCEPT_PLANNER,
        AgentType.VIDEO_GENERATOR,
        AgentType.QUALITY_CHECKER,
    ]
    task_specs = {
        AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
        AgentType.VIDEO_GENERATOR: {"run": True, "order": 1},
        AgentType.AUDIO_GENERATOR: {"run": False, "order": 2},
        AgentType.QUALITY_CHECKER: {"run": True, "order": 3},
    }

    changed = OrchestrationQueuePolicy.insert_agent_into_execution_queue(
        execution_queue,
        current_index=1,
        agent_type=AgentType.AUDIO_GENERATOR,
        task_specs=task_specs,
    )

    assert changed is True
    assert execution_queue == [
        AgentType.CONCEPT_PLANNER,
        AgentType.VIDEO_GENERATOR,
        AgentType.AUDIO_GENERATOR,
        AgentType.QUALITY_CHECKER,
    ]


def test_queue_policy_insert_agent_into_execution_queue_defers_script_consumers_until_after_pending_script_writer():
    execution_queue = [
        AgentType.CONCEPT_PLANNER,
        AgentType.SCRIPT_WRITER,
        AgentType.QUALITY_CHECKER,
    ]
    task_specs = {
        AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
        AgentType.IMAGE_GENERATOR: {"run": False, "order": 1},
        AgentType.SCRIPT_WRITER: {"run": True, "order": 5},
        AgentType.QUALITY_CHECKER: {"run": True, "order": 6},
    }

    changed = OrchestrationQueuePolicy.insert_agent_into_execution_queue(
        execution_queue,
        current_index=0,
        agent_type=AgentType.IMAGE_GENERATOR,
        task_specs=task_specs,
    )

    assert changed is True
    assert execution_queue == [
        AgentType.CONCEPT_PLANNER,
        AgentType.SCRIPT_WRITER,
        AgentType.IMAGE_GENERATOR,
        AgentType.QUALITY_CHECKER,
    ]


def test_observation_adapter_persists_audio_gate_observation(monkeypatch):
    adapter = OrchestrationObservationAdapter(memory_services=SimpleNamespace(short_term=object()))

    writes = {}

    def _capture_write(workflow_id, key, value, service=None):
        writes[key] = value

    monkeypatch.setattr(
        "app.services.orchestration_observation_adapter.write_shared_fact", _capture_write
    )

    route_payload = adapter.build_audio_route_payload(
        workflow_state_id="wf-obs-1",
        route={},
        contract={"policy": "adaptive"},
        should_run=True,
        decision_basis="boundary_trigger",
        execution_id="exec-1",
    )
    gate_result = _make_gate_result(without_audio=1, reason="audio_missing_or_unknown")
    adapter.persist_audio_gate_observation(
        workflow_state_id="wf-obs-1",
        route_payload=route_payload,
        gate_result=gate_result,
    )

    assert route_payload["policy"] == "adaptive"
    assert (
        writes["workflow.diagnostics.audio_delivery_gate"]["reason_code"]
        == "audio_missing_or_unknown"
    )
    assert (
        writes["workflow.diagnostics.audio_route"]["route_payload"]["route_source"]
        == "control_plane.boundary_trigger"
    )
    assert "decision_basis" not in writes["workflow.diagnostics.audio_route"]["route_payload"]
    assert "decision_reason" not in writes["workflow.diagnostics.audio_route"]["route_payload"]


def test_runtime_controller_applies_activation_outside_orchestrator():
    writes = {}

    state_adapter = SimpleNamespace(
        append_replan_trace=lambda **kwargs: writes.setdefault("trace", kwargs),
    )
    controller = OrchestrationRuntimeController(
        memory_services=SimpleNamespace(short_term=object()),
        orchestration_state=state_adapter,
    )
    updated_queue = [
        AgentType.CONCEPT_PLANNER,
        AgentType.VIDEO_GENERATOR,
        AgentType.AUDIO_GENERATOR,
        AgentType.QUALITY_CHECKER,
    ]
    updated_task_specs = {
        AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
        AgentType.VIDEO_GENERATOR: {"run": True, "order": 1},
        AgentType.AUDIO_GENERATOR: {
            "run": True,
            "order": 2,
            "scope": {"workflow_id": "wf-apply-1"},
        },
        AgentType.QUALITY_CHECKER: {"run": True, "order": 3},
    }
    result = controller.apply_runtime_decision(
        workflow_state_id="wf-apply-1",
        current_agent=AgentType.VIDEO_GENERATOR,
        apply_payload={
            "action": "activate_from_standby",
            "target_agent": AgentType.AUDIO_GENERATOR,
            "reason": "audio_missing_or_unknown",
            "facts": {
                "gate_events": [
                    _make_gate_result(without_audio=1, reason="audio_missing_or_unknown")
                ]
            },
            "execution_queue": updated_queue,
            "task_specs": updated_task_specs,
            "candidate_agents": updated_queue,
            "standby_agents": [],
            "queue_changed": True,
            "replan_count": 1,
        },
    )

    assert result["status"] == "activated"
    assert result["target_agent"] == AgentType.AUDIO_GENERATOR
    assert result["task_specs"][AgentType.AUDIO_GENERATOR]["run"] is True
    assert result["execution_queue"] == updated_queue
    assert writes["trace"]["record"]["queue_changed"] is True
    assert result["replan_count"] == 1
    assert result["standby_agents"] == []


def test_runtime_controller_rejects_unknown_apply_action():
    controller = OrchestrationRuntimeController(
        memory_services=SimpleNamespace(short_term=object()),
        orchestration_state=SimpleNamespace(
            append_replan_trace=lambda **kwargs: None,
        ),
    )

    with pytest.raises(
        OrchestrationRuntimeControllerError, match="Unsupported apply action: pause"
    ):
        controller.apply_runtime_decision(
            workflow_state_id="wf-apply-unknown-action",
            current_agent=AgentType.VIDEO_GENERATOR,
            apply_payload={
                "action": "pause",
                "reason": "invalid",
                "facts": {},
                "replan_count": 0,
            },
        )


def test_control_plane_apply_requires_preplanned_task_spec():
    called = {"controller_apply": 0}

    control_plane = OrchestrationControlPlane(
        memory_services=SimpleNamespace(short_term=object()),
        protocol=OrchestrationProtocol(),
        runtime_controller=SimpleNamespace(
            apply_runtime_decision=lambda **kwargs: called.__setitem__("controller_apply", 1)
        ),
    )

    with pytest.raises(OrchestrationControlPlaneError, match="missing preplanned task_spec"):
        control_plane.apply_runtime_decision(
            workflow_state_id="wf-apply-missing-spec",
            current_agent=AgentType.VIDEO_GENERATOR,
            current_index=1,
            runtime_decision={
                "action": "activate_from_standby",
                "target_agent": AgentType.AUDIO_GENERATOR,
                "reason": "audio_missing_or_unknown",
                "facts": {
                    "gate_events": [
                        _make_gate_result(without_audio=1, reason="audio_missing_or_unknown")
                    ]
                },
            },
            execution_queue=[
                AgentType.CONCEPT_PLANNER,
                AgentType.VIDEO_GENERATOR,
                AgentType.QUALITY_CHECKER,
            ],
            task_specs={
                AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
                AgentType.VIDEO_GENERATOR: {"run": True, "order": 1},
                AgentType.QUALITY_CHECKER: {"run": True, "order": 3},
            },
            candidate_agents=[
                AgentType.CONCEPT_PLANNER,
                AgentType.VIDEO_GENERATOR,
                AgentType.QUALITY_CHECKER,
                AgentType.AUDIO_GENERATOR,
            ],
            conditional_task_specs={},
            standby_agents=[AgentType.AUDIO_GENERATOR],
            replan_count=0,
        )

    assert called["controller_apply"] == 0


def test_control_plane_apply_requires_explicit_action():
    called = {"controller_apply": 0}

    control_plane = OrchestrationControlPlane(
        memory_services=SimpleNamespace(short_term=object()),
        protocol=OrchestrationProtocol(),
        runtime_controller=SimpleNamespace(
            apply_runtime_decision=lambda **kwargs: called.__setitem__("controller_apply", 1)
        ),
    )

    with pytest.raises(OrchestrationControlPlaneError, match="runtime_decision missing action"):
        control_plane.apply_runtime_decision(
            workflow_state_id="wf-apply-missing-action",
            current_agent=AgentType.VIDEO_GENERATOR,
            current_index=1,
            runtime_decision={
                "reason": "missing_action",
                "facts": {},
            },
            execution_queue=[AgentType.VIDEO_GENERATOR],
            task_specs={AgentType.VIDEO_GENERATOR: {"run": True, "order": 0}},
            candidate_agents=[AgentType.VIDEO_GENERATOR],
            conditional_task_specs={},
            standby_agents=[],
            replan_count=0,
        )

    assert called["controller_apply"] == 0


def test_control_plane_apply_uses_conditional_task_spec_for_activation():
    captured = {}

    def _capture_apply(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "status": "activated",
            "target_agent": kwargs["apply_payload"]["target_agent"],
            "execution_queue": kwargs["apply_payload"]["execution_queue"],
            "task_specs": kwargs["apply_payload"]["task_specs"],
            "queue_changed": kwargs["apply_payload"]["queue_changed"],
            "standby_agents": kwargs["apply_payload"]["standby_agents"],
            "replan_count": kwargs["apply_payload"]["replan_count"],
        }

    control_plane = OrchestrationControlPlane(
        memory_services=SimpleNamespace(short_term=object()),
        protocol=OrchestrationProtocol(),
        runtime_controller=SimpleNamespace(apply_runtime_decision=_capture_apply),
    )

    control_plane.apply_runtime_decision(
        workflow_state_id="wf-conditional-spec",
        current_agent=AgentType.VIDEO_GENERATOR,
        current_index=1,
        runtime_decision={
            "action": "activate_from_standby",
            "target_agent": AgentType.VIDEO_COMPOSER,
            "reason": "global_bgm_missing",
            "facts": {
                "llm_output": {"task_id": "bgm_mix"},
                "gate_events": [
                    _make_gate_result(without_audio=1, reason="audio_missing_or_unknown")
                ],
            },
        },
        execution_queue=[
            AgentType.CONCEPT_PLANNER,
            AgentType.VIDEO_GENERATOR,
            AgentType.QUALITY_CHECKER,
        ],
        task_specs={
            AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
            AgentType.VIDEO_GENERATOR: {"run": True, "order": 1},
            AgentType.VIDEO_COMPOSER: {
                "run": False,
                "order": 2,
                "mission": "compose the final video when activated",
                "deliverable": "final composed video",
                "constraints": [],
                "runtime_hints": {"compose_mode": "compose"},
            },
            AgentType.QUALITY_CHECKER: {"run": True, "order": 3},
        },
        candidate_agents=[
            AgentType.CONCEPT_PLANNER,
            AgentType.VIDEO_GENERATOR,
            AgentType.VIDEO_COMPOSER,
            AgentType.QUALITY_CHECKER,
        ],
        conditional_task_specs={
            "bgm_mix": {
                "agent": AgentType.VIDEO_COMPOSER.value,
                "mission": "mix background music into the composed video",
                "deliverable": "bgm-mixed final video",
                "constraints": [],
                "trigger": "global_bgm_missing",
                "runtime_hints": {"compose_mode": "bgm"},
            }
        },
        standby_agents=[AgentType.VIDEO_COMPOSER],
        replan_count=0,
    )

    target_spec = captured["kwargs"]["apply_payload"]["task_specs"][AgentType.VIDEO_COMPOSER]
    assert target_spec["run"] is True
    assert target_spec["mission"] == "mix background music into the composed video"
    assert target_spec["deliverable"] == "bgm-mixed final video"
    assert target_spec["runtime_hints"] == {"compose_mode": "bgm"}
    assert target_spec["conditional_task_id"] == "bgm_mix"


def _async_return_json(payload):
    async def _runner(*args, **kwargs):
        return {"content": __import__("json").dumps(payload, ensure_ascii=False)}

    return _runner


@pytest.mark.asyncio
async def test_composition_probe_clip_has_audio_detects_audio_stream(monkeypatch):
    tool = object.__new__(CompositionTool)
    monkeypatch.setattr(composition_module.os.path, "exists", lambda _: True)

    ffmpeg = _StubFFmpegTool(
        {"/tmp/clip.mp4": {"audio_codec": "aac", "sample_rate": 48000, "channels": 2}}
    )
    result = await tool._probe_clip_has_audio(ffmpeg, "/tmp/clip.mp4")
    assert result is True


@pytest.mark.asyncio
async def test_composition_probe_clip_has_audio_returns_none_when_probe_fails(monkeypatch):
    tool = object.__new__(CompositionTool)
    monkeypatch.setattr(composition_module.os.path, "exists", lambda _: True)

    ffmpeg = _StubFFmpegTool({"/tmp/clip.mp4": RuntimeError("probe failed")})
    result = await tool._probe_clip_has_audio(ffmpeg, "/tmp/clip.mp4")
    assert result is None


@pytest.mark.asyncio
async def test_composition_preserve_audio_requires_all_clips_with_audio_in_adaptive(monkeypatch):
    tool = object.__new__(CompositionTool)
    monkeypatch.setattr(settings, "COMPOSER_PRESERVE_SOURCE_AUDIO_DEFAULT", False, raising=False)

    async def _probe_all_audio(_ffmpeg_tool, _clip_path):
        return {"has_audio": True, "audio_codec": "aac", "sample_rate": 48000, "channels": 2}

    monkeypatch.setattr(tool, "_probe_clip_audio_profile", _probe_all_audio)
    preserve = await tool._resolve_preserve_source_audio(
        {},
        clips=["/tmp/s1.mp4", "/tmp/s2.mp4"],
        ffmpeg_tool=object(),
    )
    assert preserve is True

    async def _probe_partial(_ffmpeg_tool, clip_path):
        if clip_path.endswith("s1.mp4"):
            return {"has_audio": True, "audio_codec": "aac", "sample_rate": 48000, "channels": 2}
        return None

    monkeypatch.setattr(tool, "_probe_clip_audio_profile", _probe_partial)
    preserve_unknown = await tool._resolve_preserve_source_audio(
        {},
        clips=["/tmp/s1.mp4", "/tmp/s2.mp4"],
        ffmpeg_tool=object(),
    )
    assert preserve_unknown is False

    async def _probe_incompatible(_ffmpeg_tool, clip_path):
        if clip_path.endswith("s1.mp4"):
            return {"has_audio": True, "audio_codec": "aac", "sample_rate": 48000, "channels": 2}
        return {"has_audio": True, "audio_codec": "aac", "sample_rate": 44100, "channels": 2}

    monkeypatch.setattr(tool, "_probe_clip_audio_profile", _probe_incompatible)
    preserve_incompatible = await tool._resolve_preserve_source_audio(
        {},
        clips=["/tmp/s1.mp4", "/tmp/s2.mp4"],
        ffmpeg_tool=object(),
    )
    assert preserve_incompatible is False


@pytest.mark.asyncio
async def test_composition_explicit_and_default_fallback(monkeypatch):
    tool = object.__new__(CompositionTool)
    monkeypatch.setattr(settings, "COMPOSER_PRESERVE_SOURCE_AUDIO_DEFAULT", True, raising=False)

    preserve_explicit = await tool._resolve_preserve_source_audio(
        {"preserve_audio": True},
        clips=[],
        ffmpeg_tool=object(),
    )
    assert preserve_explicit is True

    preserve_no_clips = await tool._resolve_preserve_source_audio(
        {},
        clips=[],
        ffmpeg_tool=object(),
    )
    assert preserve_no_clips is True

    async def _probe_all_audio(_ffmpeg_tool, _clip_path):
        return {"has_audio": True, "audio_codec": "aac", "sample_rate": 48000, "channels": 2}

    monkeypatch.setattr(tool, "_probe_clip_audio_profile", _probe_all_audio)
    preserve_all_audio = await tool._resolve_preserve_source_audio(
        {},
        clips=["/tmp/s1.mp4"],
        ffmpeg_tool=object(),
    )
    assert preserve_all_audio is True
