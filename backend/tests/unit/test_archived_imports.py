import importlib
import pytest


ARCHIVED_MODULES = [
    "app.agents.video_generator_old",
    "app.agents.video_generator_legacy",
    "app.agents.video_generator_old_loop",
    "app.agents.image_generator_old",
    "app.agents.image_generator_old_react",
    "app.agents.image_generator_simple",
    "app.agents.video_generator_llm_broken",
    "app.agents.script_writer_old_loop",
    "app.agents.script_writer_react_broken",
    "app.agents.concept_planner_old",
    "app.agents.function_call_agent_example",
]


@pytest.mark.parametrize("module_name", ARCHIVED_MODULES)
def test_archived_module_import_raises(module_name):
    with pytest.raises(ImportError):
        importlib.import_module(module_name)

