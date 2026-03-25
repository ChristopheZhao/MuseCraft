import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.base import AgentError
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.orchestrator import OrchestratorAgent
from app.agents.utils.memory_helpers import write_shared_fact
from app.models import AgentType
from app.services.context_assembler import ContextContractAssembler


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def _seed_stale_script_facts(service: WorkingMemoryService, workflow_id: str) -> None:
    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {"overview": "stale overview", "roles": [{"name": "Stale Han Li"}]},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 99, "visual_description": "stale scene"}]},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "project.scene_scripts",
        {99: {"script_text": "stale script"}},
        service=service,
    )

def _build_script_deliverable_ref(tmp_path: Path, workflow_id: str) -> dict:
    payload_path = Path(tmp_path) / "script_payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {
                    "overview": "published overview",
                    "roles": [{"name": "Published Han Li"}],
                    "scenes": [{"scene_number": 1, "title": "Immortal cave"}],
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
                "scene_scripts": {
                    "1": {
                        "script_text": "published script",
                        "voice_over_text": "published voice",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {
        "type": "published_deliverable",
        "deliverable_id": 7,
        "deliverable_type": "script",
        "scope_type": "episode",
        "scope_id": "episode",
        "attempt_id": 11,
        "revision_no": 0,
        "payload_ref": str(payload_path),
        "summary": {"total_scenes": 1},
        "is_candidate": False,
        "is_approved": True,
    }


def test_image_generator_context_uses_published_deliverable_as_single_stage_source(tmp_path):
    service = _build_service()
    workflow_id = "wf-image-boundary"

    # Stale live WM facts should not leak into image static context once a published
    # script deliverable exists for the workflow.
    _seed_stale_script_facts(service, workflow_id)
    script_ref = _build_script_deliverable_ref(tmp_path, workflow_id)

    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=service)
    agent.logger = logging.getLogger("test_orchestrator_image_context_boundary")
    agent._context_contract_assembler = ContextContractAssembler(
        memory_services=SimpleNamespace(short_term=service)
    )
    agent._context_contract_assembler._persist_scene_info_ref = (
        lambda **kwargs: "/tmp/scene_info_ref.json"
    )

    agent_input = asyncio.run(
        agent._prepare_agent_context(
            {},
            AgentType.IMAGE_GENERATOR,
            workflow_id,
            runtime_input_payload={"published_deliverables": {"script": script_ref}},
        )
    )

    static_context = agent_input["static_context"]
    assert "scene_overview" not in static_context
    assert "scene_scripts" not in static_context
    assert static_context["concept_plan"]["overview"] == "published overview"
    assert static_context["scene_info_ref"] == "/tmp/scene_info_ref.json"
    assert static_context["scenes_to_generate"][0]["script_text"] == "published script"


def test_prepare_agent_context_prefers_runtime_input_published_deliverable_without_projection(tmp_path):
    service = _build_service()
    workflow_id = "wf-image-runtime-input-boundary"
    _seed_stale_script_facts(service, workflow_id)
    script_ref = _build_script_deliverable_ref(tmp_path, workflow_id)

    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=service)
    agent.logger = logging.getLogger("test_orchestrator_image_context_boundary")
    agent._context_contract_assembler = ContextContractAssembler(
        memory_services=SimpleNamespace(short_term=service)
    )
    agent._context_contract_assembler._persist_scene_info_ref = (
        lambda **kwargs: "/tmp/runtime_input_scene_info_ref.json"
    )

    agent_input = asyncio.run(
        agent._prepare_agent_context(
            {},
            AgentType.IMAGE_GENERATOR,
            workflow_id,
            runtime_input_payload={"published_deliverables": {"script": script_ref}},
        )
    )

    static_context = agent_input["static_context"]
    assert static_context["concept_plan"]["overview"] == "published overview"
    assert static_context["scene_info_ref"] == "/tmp/runtime_input_scene_info_ref.json"
    assert static_context["scenes_to_generate"][0]["script_text"] == "published script"
    assert static_context["scenes_to_generate"][0]["scene_number"] == 1


def test_audio_generator_context_prefers_published_script_payload(tmp_path):
    service = _build_service()
    workflow_id = "wf-audio-boundary"
    _seed_stale_script_facts(service, workflow_id)
    script_ref = _build_script_deliverable_ref(tmp_path, workflow_id)
    write_shared_fact(
        workflow_id,
        "project.audio_requirements",
        {"sfx_required": False, "music_style": "published-safe"},
        service=service,
    )

    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))
    boundary = assembler.assemble_agent_context(
        agent_type=AgentType.AUDIO_GENERATOR,
        workflow_state_id=workflow_id,
        workflow_data={},
        runtime_input_payload={"published_deliverables": {"script": script_ref}},
    )

    static_context = boundary["static_context"]
    assert static_context["scene_overview"]["scenes"][0]["scene_number"] == 1
    assert static_context["scene_overview"]["scenes"][0]["visual_description"] == "published scene"
    assert static_context["scene_scripts"][1]["script_text"] == "published script"
    assert static_context["audio_requirements"]["music_style"] == "published-safe"


def test_voice_synthesizer_context_prefers_published_script_payload(tmp_path):
    service = _build_service()
    workflow_id = "wf-voice-boundary"
    _seed_stale_script_facts(service, workflow_id)
    script_ref = _build_script_deliverable_ref(tmp_path, workflow_id)

    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))
    boundary = assembler.assemble_agent_context(
        agent_type=AgentType.VOICE_SYNTHESIZER,
        workflow_state_id=workflow_id,
        workflow_data={},
        runtime_input_payload={"published_deliverables": {"script": script_ref}},
    )

    static_context = boundary["static_context"]
    assert static_context["roles_context"]["roles"][0]["name"] == "Published Han Li"
    assert static_context["scene_overview"]["scenes"][0]["visual_description"] == "published scene"
    assert static_context["scenes_to_synthesize"][0]["scene_number"] == 1
    assert static_context["scenes_to_synthesize"][0]["voice_over_text"] == "published voice"


def test_prepare_agent_context_requires_runtime_input_published_deliverable(tmp_path):
    service = _build_service()
    workflow_id = "wf-image-boundary-required"
    _seed_stale_script_facts(service, workflow_id)

    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=service)
    agent.logger = logging.getLogger("test_orchestrator_image_context_boundary")
    agent._context_contract_assembler = ContextContractAssembler(
        memory_services=SimpleNamespace(short_term=service)
    )

    with pytest.raises(AgentError, match="missing_runtime_input_ref"):
        asyncio.run(
            agent._prepare_agent_context(
                {},
                AgentType.IMAGE_GENERATOR,
                workflow_id,
                runtime_input_payload={},
            )
        )


def test_prepare_agent_context_pins_boundary_reads_to_runtime_input_payload(tmp_path):
    service = _build_service()
    workflow_id = "wf-image-runtime-payload-pinned"
    _seed_stale_script_facts(service, workflow_id)
    runtime_script_ref = _build_script_deliverable_ref(tmp_path, workflow_id)

    stale_payload_path = Path(tmp_path) / "stale_script_payload.json"
    stale_payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {"overview": "mutated workflow payload"},
                "scene_overview": {"scenes": [{"scene_number": 9, "visual_description": "mutated scene"}]},
                "scene_scripts": {"9": {"script_text": "mutated script"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    stale_workflow_ref = {
        **runtime_script_ref,
        "deliverable_id": 99,
        "payload_ref": str(stale_payload_path),
        "summary": {"total_scenes": 1},
    }

    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=service)
    agent.logger = logging.getLogger("test_orchestrator_image_context_boundary")
    agent._context_contract_assembler = ContextContractAssembler(
        memory_services=SimpleNamespace(short_term=service)
    )
    agent._context_contract_assembler._persist_scene_info_ref = (
        lambda **kwargs: "/tmp/runtime_payload_pinned_scene_info_ref.json"
    )

    agent_input = asyncio.run(
        agent._prepare_agent_context(
            {"published_deliverables": {"script": stale_workflow_ref}},
            AgentType.IMAGE_GENERATOR,
            workflow_id,
            runtime_input_payload={"published_deliverables": {"script": runtime_script_ref}},
        )
    )

    static_context = agent_input["static_context"]
    assert static_context["concept_plan"]["overview"] == "published overview"
    assert static_context["scenes_to_generate"][0]["scene_number"] == 1
    assert static_context["scenes_to_generate"][0]["script_text"] == "published script"
