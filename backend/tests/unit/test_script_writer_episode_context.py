import asyncio
from types import SimpleNamespace

import pytest

from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.adapters.video.models import SceneSnapshot as VideoSceneSnapshot
from app.agents.base import AgentError
from app.agents.script_writer import ScriptWriterAgent
from app.agents.memory.short_term import SceneSnapshot
from app.agents.utils.memory_helpers import ensure_mas_working_memory, write_shared_fact


def test_script_writer_passes_episode_context(monkeypatch):
    agent = object.__new__(ScriptWriterAgent)
    service = WorkingMemoryService()
    agent._memory_services = SimpleNamespace(short_term=service, long_term=None)

    wf_id = "wf1"
    ensure_mas_working_memory(wf_id, service=service)
    wf_scenes = [
        SceneSnapshot(scene_number=1, visual_description="Scene", narrative_description="Battle", duration=10.0)
    ]
    concept_plan = {"genre_and_theme": {"theme": "loyalty"}}

    captured_params = []

    async def fake_execute_tool_calls(tool_calls, **_kwargs):
        function = tool_calls[0]["function"]
        name = function["name"]
        if name == "script_generation.generate_scene_scripts_batch":
            scene_params = function["arguments"]["scenes"][0]
            captured_params.append(scene_params)
            raise RuntimeError("stop after context capture")
        raise AssertionError(f"unexpected tool call: {name}")

    agent.execute_tool_calls = fake_execute_tool_calls
    agent.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
        debug=lambda *a, **k: None,
        exception=lambda *a, **k: None,
    )

    async def run():
        return await agent._batch_generate_scripts(
            scenes=wf_scenes,
            concept_plan=concept_plan,
            workflow_state_id=wf_id,
            task=None,
            episode_context={
                "episode_index": 1,
                "episode_count": 3,
                "sequence_index": 0,
                "title": "Episode 1",
                "summary": "赵子龙回马",
                "narrative_purpose": "Set up",
                "target_duration_seconds": 60,
                "approved_script": "00:00-00:10 战况紧急，赵子龙回马。",
            },
            project_context={
                "project_brief": "长坂坡忠勇叙事",
                "global_theme": "loyalty",
            },
            approved_script_text="00:00-00:10 战况紧急，赵子龙回马。",
        )

    try:
        asyncio.run(run())
    except AgentError as exc:
        assert "stop after context capture" in str(exc)

    assert captured_params, "script_writer should invoke tools"
    ctx_entry = captured_params[0]
    ctx = ctx_entry["context"]
    assert ctx["episode_context"]["title"] == "Episode 1"
    assert ctx["episode_context"]["episode_index"] == 1
    assert ctx["approved_script"].startswith("00:00-00:10")


def test_script_writer_uses_assembler_static_context_for_scene_inputs():
    service = WorkingMemoryService()
    workflow_id = "wf-script-fallback"
    ensure_mas_working_memory(workflow_id, service=service)

    agent = object.__new__(ScriptWriterAgent)
    agent._memory_services = SimpleNamespace(short_term=service)
    agent.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    agent._estimate_scene_count = lambda *_args, **_kwargs: 1

    captured = {}

    async def fake_batch_generate_scripts(
        scenes,
        concept_plan,
        workflow_state_id,
        task,
        **kwargs,
    ):
        captured["scenes"] = scenes
        captured["concept_plan"] = concept_plan
        captured["workflow_state_id"] = workflow_state_id
        return {"success": True, "scenes_generated": len(scenes)}

    agent._batch_generate_scripts = fake_batch_generate_scripts

    input_data = {
        "workflow_state_id": workflow_id,
        "static_context": {
            "concept_plan": {
                "overview": "凡人修仙传2预告",
            },
            "scene_overview": {
                "scenes": [
                    {
                        "scene_number": 1,
                        "duration": 10.0,
                        "visual_description": "韩立立于山巅，衣袍翻飞",
                        "narrative_description": "用第一幕建立史诗续作的开场气势",
                        "motion_beats": [{"start": 0.0, "end": 2.0, "visual_focus": "韩立抬头"}],
                    }
                ],
            },
        },
    }

    result = asyncio.run(agent._execute_impl(task=None, input_data=input_data, db=None))

    assert result["success"] is True
    assert result["execution_boundary"] == {
        "mode": "deterministic_mas_stage",
        "native_agent": False,
        "reason_code": "script_writer_deterministic_tool_sequence",
    }
    assert result["orchestration_report"]["boundary_event"] == "scene_script_completed"
    assert result["orchestration_report"]["gate_triggers"] == []
    assert result["orchestration_report"]["artifacts"] == [
        {"kind": "shared_fact", "ref": "project.scene_scripts"}
    ]
    assert (
        result["orchestration_report"]["reflection"]["reported_hints"]
        == ["script_writer_deterministic_tool_sequence"]
    )
    assert captured["workflow_state_id"] == workflow_id
    assert captured["concept_plan"]["overview"] == "凡人修仙传2预告"
    assert len(captured["scenes"]) == 1
    assert isinstance(captured["scenes"][0], VideoSceneSnapshot)
    assert captured["scenes"][0].scene_number == 1
    assert captured["scenes"][0].visual_description == "韩立立于山巅，衣袍翻飞"


def test_script_writer_partial_result_reports_deterministic_boundary():
    agent = object.__new__(ScriptWriterAgent)

    result = agent._attach_deterministic_boundary_report(
        {
            "success": False,
            "scenes_generated": 1,
            "total_scenes": 2,
            "failed_voice_scenes": [{"scene_number": 2, "reason": "voice_plan_missing"}],
        }
    )

    assert result["execution_boundary"]["mode"] == "deterministic_mas_stage"
    report = result["orchestration_report"]
    assert report["status"] == "partial"
    assert report["boundary_event"] == "scene_script_completed"
    assert report["reflection"]["completion_state"] == "partial"
    assert report["reflection"]["reported_gaps"] == ["scene_script_generation_incomplete"]


def test_script_writer_ignores_raw_scene_context_without_assembler_boundary():
    service = WorkingMemoryService()
    workflow_id = "wf-script-raw-ignored"
    ensure_mas_working_memory(workflow_id, service=service)

    agent = object.__new__(ScriptWriterAgent)
    agent._memory_services = SimpleNamespace(short_term=service)
    agent.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )

    scenes, concept_plan, fallback = agent._load_execution_scene_inputs(
        workflow_id,
        {
            "workflow_state_id": workflow_id,
            "concept_plan": {
                "overview": "raw payload should not be used",
                "scenes": [
                    {
                        "scene_number": 9,
                        "duration": 8.0,
                        "visual_description": "raw scene",
                        "narrative_description": "raw narrative",
                    }
                ],
            },
        },
    )

    assert scenes == []
    assert concept_plan == {}
    assert fallback is not None
    assert "missing_assembler_static_context" in fallback
    assert "raw_input_context_ignored" in fallback


def test_script_writer_reads_scene_overview_from_static_context_boundary():
    service = WorkingMemoryService()
    workflow_id = "wf-script-static-context"
    ensure_mas_working_memory(workflow_id, service=service)

    agent = object.__new__(ScriptWriterAgent)
    agent._memory_services = SimpleNamespace(short_term=service)
    agent.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )

    scenes, concept_plan, fallback = agent._load_execution_scene_inputs(
        workflow_id,
        {
            "workflow_state_id": workflow_id,
            "static_context": {
                "concept_plan": {"overview": "boundary overview"},
                "scene_overview": {
                    "scenes": [
                        {
                            "scene_number": 2,
                            "duration": 8.0,
                            "visual_description": "山门前灵光乍现",
                            "narrative_description": "第二幕承接初入修仙世界的震撼感",
                        }
                    ]
                },
            },
        },
    )

    assert fallback is None
    assert concept_plan == {"overview": "boundary overview"}
    assert len(scenes) == 1
    assert scenes[0].scene_number == 2
    assert scenes[0].narrative_description == "第二幕承接初入修仙世界的震撼感"


def test_script_writer_rejects_malformed_scene_scripts_slot():
    service = WorkingMemoryService()
    workflow_id = "wf-script-slot-malformed"
    ensure_mas_working_memory(workflow_id, service=service)
    write_shared_fact(
        workflow_id,
        "project.scene_scripts",
        ["not", "a", "dict"],
        service=service,
    )

    agent = object.__new__(ScriptWriterAgent)
    agent._memory_services = SimpleNamespace(short_term=service)

    with pytest.raises(AgentError, match="project.scene_scripts malformed"):
        agent._read_scene_scripts_slot(workflow_id)
