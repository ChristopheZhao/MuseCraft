import json
import logging
from types import SimpleNamespace

import pytest

from app.agents.adapters.memory_views import build_quality_checker_context
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.quality_checker import QualityCheckerAgent
from app.agents.utils.memory_helpers import write_shared_fact
from app.core.config import settings
from app.models import AgentType
from app.services.context_assembler import ContextContractAssembler


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def test_build_quality_checker_context_normalizes_boundary_from_mas_wm(monkeypatch):
    service = _build_service()
    workflow_id = "wf-quality-boundary"

    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", "/tmp/final_outputs")
    monkeypatch.setattr(
        "app.agents.adapters.memory_views.probe_local_video_metadata_sync",
        lambda path: {
            "duration": 45.2,
            "format": "mp4",
            "file_size": 17030496,
            "file_size_mb": 16.24,
            "resolution": "1920x1080",
        }
        if path == "/tmp/final_outputs/videos/final.mp4"
        else {},
    )

    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {"overview": "original brief", "scenes": [{"scene_number": 1}]},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "project.final_video",
        {"url": "/files/outputs/videos/final.mp4"},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {
            "2": {"scene_number": 2, "duration_sec": 5.0},
            "1": {"scene_number": 1, "duration_sec": 10.0},
        },
        service=service,
    )

    result = build_quality_checker_context(workflow_id, service=service)
    context = result["context"]
    diagnostics = result["diagnostics"]

    assert context["final_video"]["path"] == "/tmp/final_outputs/videos/final.mp4"
    assert context["final_video"]["url"] == "/files/outputs/videos/final.mp4"
    assert context["concept_plan"]["overview"] == "original brief"
    assert context["original_requirements"]["overview"] == "original brief"
    assert context["video_metadata"]["duration"] == 45.2
    assert context["video_metadata"]["format"] == "mp4"
    assert context["composition_timeline"] == [
        {"scene_number": 1, "start": 0.0, "end": 10.0, "duration": 10.0},
        {"scene_number": 2, "start": 10.0, "end": 15.0, "duration": 5.0},
    ]
    assert diagnostics["status"] == "resolved_with_fallbacks"
    assert diagnostics["concept_plan_source"] == "project.concept_plan"
    assert diagnostics["timeline_source"] == "scene_outputs.video"
    assert diagnostics["video_metadata_source"] == "local_probe"


def test_context_assembler_projects_quality_checker_static_context(monkeypatch):
    service = _build_service()
    workflow_id = "wf-quality-assembler"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", "/tmp/final_outputs")
    monkeypatch.setattr(
        "app.agents.adapters.memory_views.probe_local_video_metadata_sync",
        lambda _path: {"duration": 12.5, "format": "mp4"},
    )

    write_shared_fact(
        workflow_id,
        "project.final_video",
        {"url": "/files/outputs/videos/final.mp4"},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 1, "duration": 12.5}]},
        service=service,
    )

    boundary = assembler.assemble_agent_context(
        agent_type=AgentType.QUALITY_CHECKER,
        workflow_state_id=workflow_id,
        workflow_data={},
    )

    assert boundary["static_context"]["final_video"]["path"] == "/tmp/final_outputs/videos/final.mp4"
    assert boundary["static_context"]["video_metadata"]["duration"] == 12.5
    assert boundary["_assembler_diagnostics"]["quality_checker_context"]["status"] == "resolved_with_fallbacks"


@pytest.mark.asyncio
async def test_ai_content_analysis_renders_original_requirements_and_video_metadata(monkeypatch):
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.prompt")

    captured = {}

    def _render_prompt(name, **kwargs):
        captured["template"] = name
        captured.update(kwargs)
        return "quality prompt"

    async def _llm_function_call(**_kwargs):
        return {
            "content": json.dumps(
                {
                    "overall_assessment": "ok",
                    "quality_score": 8.0,
                },
                ensure_ascii=False,
            )
        }

    class _ModelConfig:
        temperature = 0.3
        max_tokens = 1000

    class _AIConfig:
        def get_model_for_agent(self, _agent_name):
            return "test-model"

        def get_model_config(self, _model_name):
            return _ModelConfig()

    class _PromptManager:
        def render_template(self, *_args, **_kwargs):
            return ""

    agent.render_prompt = _render_prompt
    agent.llm_function_call = _llm_function_call

    monkeypatch.setattr("app.core.ai_config.get_ai_config", lambda: _AIConfig())
    monkeypatch.setattr("app.core.prompt_manager.get_prompt_manager", lambda: _PromptManager())

    result = await agent._ai_content_analysis(
        concept_plan={"overview": "effective plan"},
        composition_timeline=[{"scene_number": 1, "duration": 10.0}],
        original_requirements={"overview": "original brief"},
        video_metadata={"duration": 12.5, "format": "mp4"},
    )

    assert result["overall_assessment"] == "ok"
    assert captured["template"] == "video_quality_analysis"
    assert json.loads(captured["concept_plan"])["overview"] == "effective plan"
    assert json.loads(captured["original_requirements"])["overview"] == "original brief"
    assert json.loads(captured["video_metadata"])["duration"] == 12.5
