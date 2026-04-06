import logging
from types import SimpleNamespace

from app.agents.orchestrator import OrchestratorAgent
from app.models import AgentType


def test_store_composer_outputs_derives_public_final_video_url(monkeypatch):
    captured = {}

    def _capture_write(workflow_id, key, value, service=None):
        captured[key] = value

    agent = object.__new__(OrchestratorAgent)
    agent.logger = logging.getLogger("test.orchestrator.store_composer_outputs")
    agent._memory_services = SimpleNamespace(
        short_term=object(),
        global_service=object(),
        long_term=object(),
    )

    monkeypatch.setattr("app.agents.orchestrator.write_shared_fact", _capture_write)
    monkeypatch.setattr("app.agents.orchestrator.build_local_public_url", lambda path: "/files/outputs/videos/final.mp4")
    monkeypatch.setattr(
        "app.agents.orchestrator.probe_local_video_metadata_sync",
        lambda path: {"duration": 45.2, "format": "mp4"} if path == "/tmp/final.mp4" else {},
    )

    agent._store_composer_outputs(
        "wf-123",
        {
            "final_video_path": "/tmp/final.mp4",
            "mix_receipt": {"output_path": "/tmp/final.mp4"},
        },
    )

    assert captured["project.final_video"]["url"] == "/files/outputs/videos/final.mp4"
    assert captured["project.final_video"]["path"] == "/tmp/final.mp4"
    assert captured["project.final_video"]["metadata"]["duration"] == 45.2


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
