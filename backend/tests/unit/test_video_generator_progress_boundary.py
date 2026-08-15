import asyncio
import logging

import pytest

from app.agents.utils.artifacts import (
    SceneOutputAuthorityError,
    finalize_scene_outputs,
    issue_scene_output_acceptance_receipts,
)
from app.agents.utils.memory_helpers import ensure_agent_working_memory, ensure_mas_working_memory
from app.agents.utils.plan_context import build_plan_context
from app.agents.video_generator import VideoGeneratorAgent
from app.services.memory_provider import build_memory_services


@pytest.fixture(autouse=True)
def _use_in_memory_long_term_store(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "dict")


def _make_bare_video_generator_agent():
    agent = object.__new__(VideoGeneratorAgent)
    agent.agent_name = "video_generator"
    agent.workflow_state_id = "wf-video-progress"
    agent._memory_services = build_memory_services()
    agent.logger = logging.getLogger("test.video_generator.progress")
    return agent


def _video_record(scene_number, *, workflow_state_id, path="", url=""):
    artifact = {
        "success": True,
        "scene_number": scene_number,
        "video_path": path,
        "video_url": url,
    }
    if path:
        artifact["metadata"] = {"storage": {"status": "persisted"}}
    artifacts, _receipts = issue_scene_output_acceptance_receipts(
        kind="video",
        artifacts=[artifact],
        workflow_state_id=workflow_state_id,
    )
    artifacts[0]["acceptance_receipt"]["accepted_at"] = (
        f"2026-07-25T00:00:0{scene_number}+00:00"
        if artifacts[0]["acceptance_receipt"]["status"] == "accepted"
        else ""
    )
    return artifacts[0]


def test_progress_read_model_ignores_helper_only_success(monkeypatch):
    services = build_memory_services()
    ensure_mas_working_memory("wf-video-helper", service=services.short_term)

    monkeypatch.setattr(
        "app.services.scene_info_reference_service.load_scene_info_payload",
        lambda _ref: {
            "scenes_to_generate": [
                {"scene_number": 1},
                {"scene_number": 2},
            ]
        },
    )

    ctx = build_plan_context(
        input_data={
            "workflow_state_id": "wf-video-helper",
            "static_context": {"scene_info_ref": "scene-info-ref"},
        },
        iteration_context={
            "obs_records": [
                {
                    "iteration": 0,
                    "action_result": {
                        "executed_calls": [
                            {
                                "success": True,
                                "args": {"scene_number": 1},
                                "tool": "video_prompt_composer.build_prompt",
                            }
                        ]
                    },
                }
            ]
        },
        workflow_state_id="wf-video-helper",
        service=services.short_term,
        progress_kind="video",
        include_execution_contract=False,
    )

    progress = ctx["progress_read_model"]
    assert progress["planned_scene_numbers"] == [1, 2]
    assert progress["successful_scene_numbers"] == []
    assert progress["remaining_scene_numbers"] == [1, 2]
    assert progress["recent_delivery_receipts"] == []
    assert progress["derived_from"] == []


def test_progress_read_model_uses_accepted_scene_outputs_with_provenance(monkeypatch):
    services = build_memory_services()
    shared = ensure_mas_working_memory("wf-video-accepted", service=services.short_term)
    shared.put(
        "scene_outputs.video",
        {
            1: _video_record(
                1,
                workflow_state_id="wf-video-accepted",
                path="/tmp/scene-1.mp4",
            ),
            2: _video_record(
                2,
                workflow_state_id="wf-video-accepted",
                url="https://example.com/scene-2.mp4",
            ),
        },
    )

    monkeypatch.setattr(
        "app.services.scene_info_reference_service.load_scene_info_payload",
        lambda _ref: {
            "scenes_to_generate": [
                {"scene_number": 1},
                {"scene_number": 2},
            ]
        },
    )

    ctx = build_plan_context(
        input_data={
            "workflow_state_id": "wf-video-accepted",
            "static_context": {"scene_info_ref": "scene-info-ref"},
        },
        iteration_context={
            "obs_records": [
                {
                    "iteration": 1,
                    "action_result": {
                        "delivery_receipts": [
                            {
                                "scene_number": 2,
                                "status": "accepted",
                                "delivery_surface": "scene_outputs.video",
                                "delivery_ref": "scene_outputs.video.2",
                                "accepted_at": "2026-04-02T12:00:00+00:00",
                            }
                        ]
                    },
                }
            ]
        },
        workflow_state_id="wf-video-accepted",
        service=services.short_term,
        progress_kind="video",
        include_execution_contract=False,
    )

    progress = ctx["progress_read_model"]
    assert progress["successful_scene_numbers"] == [1]
    assert progress["remaining_scene_numbers"] == [2]
    assert progress["derived_from"] == ["scene_outputs.video"]
    assert progress["last_receipt_watermark"] == "accepted:scene=1@2026-07-25T00:00:01+00:00"
    assert progress["max_staleness_seconds"] > 0
    diagnostics = ctx["plan_context_diagnostics"]["progress_read_model"]
    assert diagnostics["reason"] == "video_scene_outputs_not_accepted"
    assert "scene=2:acceptance_status_not_accepted" in diagnostics["detail"]


def test_video_generator_completion_gate_requires_accepted_delivery(monkeypatch):
    monkeypatch.setattr(
        "app.services.scene_info_reference_service.load_scene_info_payload",
        lambda _ref: {
            "scenes_to_generate": [
                {"scene_number": 1},
                {"scene_number": 2},
            ]
        },
    )
    agent = _make_bare_video_generator_agent()
    ensure_mas_working_memory("wf-video-progress", service=agent.short_term_service)

    decision = agent._accept_completion_request(
        stage="plan_contract",
        input_data={"workflow_state_id": "wf-video-progress"},
        plan_context={
            "progress_read_model": {
                "planned_scene_numbers": [1, 2],
            }
        },
        iteration_context=None,
        iteration=0,
        plan_contract={"task_complete": True},
    )

    assert decision["accepted"] is False
    assert decision["reason"] == "missing_delivery_acceptance"
    assert decision["missing_scene_numbers"] == [1, 2]


def test_video_generator_completion_gate_accepts_when_all_deliveries_exist():
    agent = _make_bare_video_generator_agent()
    shared = ensure_mas_working_memory("wf-video-progress", service=agent.short_term_service)
    shared.put(
        "scene_outputs.video",
        {
            1: _video_record(
                1,
                workflow_state_id="wf-video-progress",
                path="/tmp/scene-1.mp4",
            ),
            2: _video_record(
                2,
                workflow_state_id="wf-video-progress",
                path="/tmp/scene-2.mp4",
            ),
        },
    )

    decision = agent._accept_completion_request(
        stage="plan_contract",
        input_data={"workflow_state_id": "wf-video-progress"},
        plan_context={
            "progress_read_model": {
                "planned_scene_numbers": [1, 2],
            }
        },
        iteration_context=None,
        iteration=0,
        plan_contract={"task_complete": True},
    )

    assert decision["accepted"] is True
    assert decision["accepted_scene_numbers"] == [1, 2]


def test_video_generator_finalizer_reads_only_accepted_shared_scene_outputs(monkeypatch):
    agent = _make_bare_video_generator_agent()
    shared = ensure_mas_working_memory(
        "wf-video-progress",
        service=agent.short_term_service,
    )
    agent._wm_cache = ensure_agent_working_memory(
        "wf-video-progress",
        "video_generator",
        service=agent.short_term_service,
        shared_view=shared,
    )
    accepted = _video_record(
        1,
        workflow_state_id="wf-video-progress",
        path="/tmp/scene-1.mp4",
    )
    rejected = _video_record(
        2,
        workflow_state_id="wf-video-progress",
        url="https://example.com/scene-2.mp4",
    )
    shared.put(
        "scene_outputs.video",
        {
            1: accepted,
            2: rejected,
        },
    )

    async def _base_finalize(_self, final_action_result, _context):
        return dict(final_action_result or {})

    monkeypatch.setattr(
        VideoGeneratorAgent.__mro__[1],
        "_finalize_success_results",
        _base_finalize,
    )

    result = asyncio.run(
        agent._finalize_success_results(
            {},
            {"workflow_state_id": "wf-video-progress"},
        )
    )

    assert [item["scene_number"] for item in result["final_completed_scenes"]] == [1]
    assert result["orchestration_report"]["reflection"]["completed_scene_count"] == 1


def test_scene_finalizer_does_not_fallback_when_shared_authority_load_fails(monkeypatch):
    agent = _make_bare_video_generator_agent()
    local = ensure_agent_working_memory(
        "wf-video-progress",
        "video_generator",
        service=agent.short_term_service,
    )
    local.put(
        "scene_outputs.video",
        {
            1: _video_record(
                1,
                workflow_state_id="wf-video-progress",
                path="/tmp/stale-agent-scope.mp4",
            )
        },
    )
    monkeypatch.setattr(
        "app.agents.utils.artifacts.get_mas_working_memory",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("shared unavailable")),
    )

    with pytest.raises(SceneOutputAuthorityError) as exc_info:
        finalize_scene_outputs(
            kind="video",
            workflow_id="wf-video-progress",
            service=agent.short_term_service,
        )

    assert exc_info.value.reason_code == "scene_output_authority_load_failed"


def test_scene_finalizer_rejects_unbound_shared_authority():
    services = build_memory_services()
    local = ensure_agent_working_memory(
        "wf-video-unbound",
        "video_generator",
        service=services.short_term,
    )
    local.put(
        "scene_outputs.video",
        {
            1: _video_record(
                1,
                workflow_state_id="wf-video-unbound",
                path="/tmp/stale-agent-scope.mp4",
            )
        },
    )

    with pytest.raises(SceneOutputAuthorityError) as exc_info:
        finalize_scene_outputs(
            kind="video",
            workflow_id="wf-video-unbound",
        )

    assert exc_info.value.reason_code == "scene_output_authority_unbound"
