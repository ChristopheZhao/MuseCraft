"""Executable ownership rules for scheduler-neutral application execution."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = BACKEND_ROOT / "app" / "services"
TRANSPORT_MODULES = (
    SERVICES_ROOT / "task_queue.py",
    SERVICES_ROOT / "project_job_queue.py",
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(_source(path), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_queue_adapters_do_not_own_persistence_or_runtime_semantics():
    forbidden_source_markers = {
        "create_engine",
        "sessionmaker",
        "SessionLocal",
        "RuntimeSessionService",
        "get_queue_execution_block_reason",
        "resolve_generation_mode",
        "TaskStatus",
        "Task.",
    }
    for path in TRANSPORT_MODULES:
        source = _source(path)
        imports = _imported_modules(path)
        assert not any(
            module == "sqlalchemy" or module.startswith("sqlalchemy.") for module in imports
        )
        assert not any(module == "models" or module.endswith(".models") for module in imports)
        assert forbidden_source_markers.isdisjoint(source.split())
        for marker in forbidden_source_markers:
            assert marker not in source, f"{path.name} owns forbidden boundary marker {marker}"


def test_execution_host_is_typed_and_has_no_route_or_store_decisions():
    path = SERVICES_ROOT / "queued_task_execution_host.py"
    source = _source(path)
    forbidden_markers = (
        "GenerationMode",
        "RuntimeSessionService",
        "SessionLocal",
        "build_agent_execution_request",
        "OrchestratorAgent",
        "EpisodeOrchestratorAgent",
        "SeriesPlannerAgent",
        "task:",
        "db:",
        "route:",
    )
    for marker in forbidden_markers:
        assert marker not in source
    assert "request: AgentExecutionRequest" in source
    assert "executor: AgentExecutor" in source
    assert "-> AgentExecutionResult" in source


def test_transport_entrypoints_carry_public_string_identifiers():
    celery_source = _source(SERVICES_ROOT / "celery_app.py")
    assert "def process_video_task(self, task_id: str)" in celery_source
    assert "def process_project_job(self, task_id: str)" in celery_source

    task_api_source = _source(BACKEND_ROOT / "app" / "api" / "v1" / "endpoints" / "tasks.py")
    project_api_source = _source(BACKEND_ROOT / "app" / "api" / "v1" / "endpoints" / "projects.py")
    assert (
        "def _schedule_task_execution(background_tasks: BackgroundTasks, task_id: str)"
        in task_api_source
    )
    assert "_schedule_task_execution(background_tasks, task.id)" not in task_api_source
    assert "background_tasks.add_task(task_queue.queue_task, task.id)" not in project_api_source
