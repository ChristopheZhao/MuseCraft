import asyncio
from types import SimpleNamespace

from app.agents.script_writer import ScriptWriterAgent
from app.agents.memory.short_term.working_memory import SceneSnapshot


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
