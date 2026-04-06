import asyncio
from types import SimpleNamespace

from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.adapters.video.models import SceneSnapshot as VideoSceneSnapshot
from app.agents.script_writer import ScriptWriterAgent
from app.agents.memory.short_term import SceneSnapshot
from app.agents.utils.memory_helpers import ensure_mas_working_memory, write_shared_fact


def test_script_writer_passes_episode_context(monkeypatch):
    agent = object.__new__(ScriptWriterAgent)

    wf_id = "wf1"
    wf_scenes = [
        SceneSnapshot(scene_number=1, visual_description="Scene", narrative_description="Battle", duration=10.0)
    ]
    concept_plan = {"genre_and_theme": {"theme": "loyalty"}}

    captured_params = []

    async def fake_use_tool(name, action, params):
        captured_params.append((name, action, params))
        return {
            "result": {
                "success": True,
                "script_text": "赵子龙回马",
                "voice_over_text": "赵子龙回马",
            }
        }

    agent.use_tool = fake_use_tool
    agent.logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)

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

    asyncio.run(run())

    assert captured_params, "script_writer should invoke tools"
    ctx_entry = next(
        (params for name, action, params in captured_params if action == "generate_scene_script"),
        None,
    )
    assert ctx_entry is not None, f"generate_scene_script should include context payload, got {captured_params}"
    ctx = ctx_entry["context"]
    assert ctx["episode_context"]["title"] == "Episode 1"
    assert ctx["episode_context"]["episode_index"] == 1
    assert ctx["approved_script"].startswith("00:00-00:10")


def test_script_writer_uses_input_concept_plan_when_scene_overview_missing():
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
        "concept_plan": {
            "overview": "凡人修仙传2预告",
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
    }

    result = asyncio.run(agent._execute_impl(task=None, input_data=input_data, db=None))

    assert result["success"] is True
    assert captured["workflow_state_id"] == workflow_id
    assert captured["concept_plan"]["overview"] == "凡人修仙传2预告"
    assert len(captured["scenes"]) == 1
    assert isinstance(captured["scenes"][0], VideoSceneSnapshot)
    assert captured["scenes"][0].scene_number == 1
    assert captured["scenes"][0].visual_description == "韩立立于山巅，衣袍翻飞"


def test_script_writer_reads_scene_overview_from_working_memory():
    service = WorkingMemoryService()
    workflow_id = "wf-script-wm"
    ensure_mas_working_memory(workflow_id, service=service)
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {
            "scenes": [
                {
                    "scene_number": 2,
                    "duration": 8.0,
                    "visual_description": "山门前灵光乍现",
                    "narrative_description": "第二幕承接初入修仙世界的震撼感",
                }
            ]
        },
        service=service,
    )

    agent = object.__new__(ScriptWriterAgent)
    agent._memory_services = SimpleNamespace(short_term=service)
    agent.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )

    scenes, concept_plan, fallback = agent._load_execution_scene_inputs(
        workflow_id,
        {"workflow_state_id": workflow_id},
    )

    assert fallback is None
    assert concept_plan == {}
    assert len(scenes) == 1
    assert scenes[0].scene_number == 2
    assert scenes[0].narrative_description == "第二幕承接初入修仙世界的震撼感"
