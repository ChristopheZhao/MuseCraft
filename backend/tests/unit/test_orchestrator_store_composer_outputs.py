import logging
from types import SimpleNamespace

import pytest

from app.agents.base import AgentError
from app.agents.orchestrator import OrchestratorAgent
from app.agents.utils.memory_helpers import ensure_mas_working_memory
from app.domain import AgentType
from app.services.memory_provider import build_memory_services


def test_store_composer_outputs_derives_public_final_video_url(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    agent.logger = logging.getLogger("test.orchestrator.store_composer_outputs")
    agent._memory_services = build_memory_services()
    shared = ensure_mas_working_memory(
        "wf-123",
        service=agent.short_term_service,
    )

    monkeypatch.setattr(
        "app.agents.orchestrator.build_local_public_url",
        lambda path: "/files/outputs/videos/final.mp4",
    )
    monkeypatch.setattr(
        "app.agents.orchestrator.probe_local_video_metadata_sync",
        lambda path: {"duration": 45.2, "format": "mp4"} if path == "/tmp/final.mp4" else {},
    )

    rollback = agent._store_composer_outputs(
        "wf-123",
        {
            "final_video_path": "/tmp/final.mp4",
            "mix_receipt": {"output_path": "/tmp/final.mp4"},
        },
    )

    final_video = shared.get("project.final_video")
    assert final_video["url"] == "/files/outputs/videos/final.mp4"
    assert final_video["path"] == "/tmp/final.mp4"
    assert final_video["metadata"]["duration"] == 45.2

    rollback()

    assert shared.get("project.final_video") is None
    assert shared.get("project.final_video_mix") is None


def test_store_composer_outputs_rolls_back_partial_shared_write(monkeypatch):
    class _FailingSharedMemory:
        def __init__(self):
            self.data = {"project.final_video": {"path": "/tmp/old.mp4"}}
            self.fail_mix_once = True

        def list_keys(self):
            return list(self.data)

        def get(self, key, default=None):
            return self.data.get(key, default)

        def put(self, key, value):
            if key == "project.final_video_mix" and self.fail_mix_once:
                self.fail_mix_once = False
                raise RuntimeError("mix write failed")
            self.data[key] = value

        def delete(self, key):
            self.data.pop(key, None)

    shared = _FailingSharedMemory()
    agent = object.__new__(OrchestratorAgent)
    agent.logger = logging.getLogger("test.orchestrator.store_composer_outputs.rollback")
    agent._memory_services = SimpleNamespace(short_term=object())
    monkeypatch.setattr(
        "app.agents.orchestrator.get_mas_working_memory",
        lambda *_args, **_kwargs: shared,
    )

    with pytest.raises(AgentError, match="Authoritative composer publication failed"):
        agent._store_composer_outputs(
            "wf-partial-publication",
            {
                "final_video_path": "/tmp/new.mp4",
                "mix_receipt": {"output_path": "/tmp/new.mp4"},
            },
        )

    assert shared.data == {"project.final_video": {"path": "/tmp/old.mp4"}}


def test_record_agent_output_routes_video_composer_through_shared_handoff(monkeypatch):
    agent = object.__new__(OrchestratorAgent)
    workflow_results = {}
    workflow_data = {}
    captured = {}

    monkeypatch.setattr(
        agent,
        "_store_composer_outputs",
        lambda workflow_id, agent_output: captured.update(
            {"workflow_id": workflow_id, "agent_output": dict(agent_output)}
        ),
    )

    output = {
        "final_video_path": "/tmp/final.mp4",
        "final_video_url": "/files/outputs/videos/final.mp4",
    }
    agent._record_agent_output(
        workflow_id="wf-123",
        agent_type=AgentType.VIDEO_COMPOSER,
        workflow_results=workflow_results,
        workflow_data=workflow_data,
        agent_output=output,
    )

    assert workflow_results["video_composer"] == output
    assert workflow_data["final_video_path"] == "/tmp/final.mp4"
    assert captured["workflow_id"] == "wf-123"
    assert captured["agent_output"]["final_video_url"] == "/files/outputs/videos/final.mp4"


def test_orchestrator_has_no_creative_guidance_second_writer():
    assert not hasattr(OrchestratorAgent, "_store_creative_guidance_from_output")
