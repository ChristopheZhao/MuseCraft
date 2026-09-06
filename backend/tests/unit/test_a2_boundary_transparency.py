import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.base import BaseAgent
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.orchestrator import OrchestratorAgent
from app.agents.tools.agent_tool_allocation import get_agent_tools
from app.agents.tools.ai_services.music_generation_tool import MusicGenerationTool
from app.agents.tools.base_tool import ToolInput, ToolOutput
from app.domain import AgentType
from app.infrastructure.scene_info_reference_preparation import (
    FileSceneInfoReferencePreparationAdapter,
)
from app.services.context_reference_ports import SceneInfoReferencePreparationError
from app.services.memory_provider import build_memory_services
from app.services.scene_info_reference_service import SceneInfoReferencePersistenceError


def _script_ref(tmp_path: Path, workflow_id: str) -> dict:
    payload_path = tmp_path / "script.json"
    payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {
                    "overview": "published overview",
                    "scenes": [{"scene_number": 1, "title": "Opening"}],
                },
                "scene_overview": {
                    "scenes": [
                        {
                            "scene_number": 1,
                            "visual_description": "published scene",
                            "narrative_description": "published narrative",
                            "duration": 6.0,
                        }
                    ]
                },
                "scene_scripts": {"1": {"script_text": "published script"}},
            }
        ),
        encoding="utf-8",
    )
    return {
        "type": "published_deliverable",
        "deliverable_id": 1,
        "deliverable_type": "script",
        "scope_type": "episode",
        "scope_id": "episode",
        "attempt_id": 1,
        "revision_no": 1,
        "payload_ref": str(payload_path),
        "summary": {"total_scenes": 1},
        "is_candidate": False,
        "is_approved": True,
    }


def _reference_adapter() -> FileSceneInfoReferencePreparationAdapter:
    service = WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())
    return FileSceneInfoReferencePreparationAdapter(SimpleNamespace(short_term=service))


def test_scene_reference_write_occurs_before_context_assembly(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.infrastructure.scene_info_reference_preparation.persist_scene_info_ref",
        lambda **kwargs: captured.update(kwargs) or "/tmp/prepared-scene-info.json",
    )
    workflow_id = "wf-scene-reference-command"

    ref = _reference_adapter().prepare(
        workflow_state_id=workflow_id,
        agent_type=AgentType.IMAGE_GENERATOR,
        runtime_input_payload={
            "published_deliverables": {"script": _script_ref(tmp_path, workflow_id)}
        },
    )

    assert ref == "/tmp/prepared-scene-info.json"
    assert captured["workflow_id"] == workflow_id
    assert captured["agent_type"] is AgentType.IMAGE_GENERATOR
    assert captured["payload"]["scenes_to_generate"]


def test_scene_reference_persistence_failure_is_typed(tmp_path, monkeypatch):
    def _fail_persist(**_kwargs):
        raise SceneInfoReferencePersistenceError("disk full")

    monkeypatch.setattr(
        "app.infrastructure.scene_info_reference_preparation.persist_scene_info_ref",
        _fail_persist,
    )
    workflow_id = "wf-scene-reference-failure"

    with pytest.raises(SceneInfoReferencePreparationError) as caught:
        _reference_adapter().prepare(
            workflow_state_id=workflow_id,
            agent_type=AgentType.IMAGE_GENERATOR,
            runtime_input_payload={
                "published_deliverables": {"script": _script_ref(tmp_path, workflow_id)}
            },
        )

    assert caught.value.reason_code == "scene_info_reference_persistence_failed"


def test_orchestrator_construction_uses_injected_ports_without_database_composition(
    monkeypatch,
):
    database_calls = []

    def _forbidden_session_factory():
        database_calls.append("session")
        raise AssertionError("Orchestrator construction composed a database session")

    monkeypatch.setenv("MEMORY_BACKEND", "dict")
    monkeypatch.setattr(
        BaseAgent,
        "_load_tools",
        lambda self, names: setattr(self, "_available_tools", {}),
    )
    monkeypatch.setattr(
        "app.core.database.SessionLocal",
        _forbidden_session_factory,
    )
    injected_port = SimpleNamespace()

    orchestrator = OrchestratorAgent(
        memory_services=build_memory_services(),
        runtime_transition_port=injected_port,
        runtime_resume_port=injected_port,
        scene_info_reference_port=injected_port,
    )

    assert orchestrator.AGENT_EXECUTION_MODE == "mas_control_plane"
    assert orchestrator._runtime_transition_port is injected_port
    assert orchestrator._runtime_resume_port is injected_port
    assert database_calls == []


@pytest.mark.asyncio
async def test_music_tool_keeps_agent_contract_supplier_neutral(monkeypatch):
    class _Provider:
        _functional = True

        async def execute(self, _tool_input):
            return ToolOutput(
                success=True,
                result={"audio_url": "https://example.com/music.mp3"},
                execution_time=0.01,
            )

    monkeypatch.setattr(
        MusicGenerationTool,
        "_build_provider",
        lambda self, provider_name: _Provider(),
    )
    tool = MusicGenerationTool(config={"provider": "alternate-provider"})

    result = await tool._execute_impl(
        ToolInput(
            action="generate_background_music",
            parameters={"description": "restrained cinematic underscore"},
        )
    )

    assert "music_generation" in get_agent_tools(AgentType.AUDIO_GENERATOR)
    assert all(
        "suno" not in tool_name.lower() for tool_name in get_agent_tools(AgentType.AUDIO_GENERATOR)
    )
    assert result["provider"] == "alternate-provider"
