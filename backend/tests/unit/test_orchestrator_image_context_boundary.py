import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.orchestrator import OrchestratorAgent
from app.agents.utils.memory_helpers import write_shared_fact
from app.models import AgentType
from app.services.published_deliverable_adapter import project_payload_deliverables_to_shared_wm


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def test_image_generator_context_uses_published_deliverable_as_single_stage_source(tmp_path):
    service = _build_service()
    workflow_id = "wf-image-boundary"

    # Stale live WM facts should not leak into image static context once a published
    # script deliverable exists for the workflow.
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
    project_payload_deliverables_to_shared_wm(
        workflow_id,
        {
            "published_deliverables": {
                "script": {
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
            }
        },
        service=service,
    )

    agent = object.__new__(OrchestratorAgent)
    agent._memory_services = SimpleNamespace(short_term=service)
    agent.logger = logging.getLogger("test_orchestrator_image_context_boundary")
    agent._persist_scene_info_ref = lambda **kwargs: "/tmp/scene_info_ref.json"

    agent_input = asyncio.run(
        agent._prepare_agent_context({}, AgentType.IMAGE_GENERATOR, workflow_id)
    )

    static_context = agent_input["static_context"]
    assert "scene_overview" not in static_context
    assert "scene_scripts" not in static_context
    assert static_context["concept_plan"]["overview"] == "published overview"
    assert static_context["scene_info_ref"] == "/tmp/scene_info_ref.json"
    assert static_context["scenes_to_generate"][0]["script_text"] == "published script"
