"""A2 ratchets for project authority, identity, and read-model separation."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
STORY_PLAN = BACKEND_ROOT / "app" / "core" / "story_plan.py"
AGENTS_INIT = BACKEND_ROOT / "app" / "agents" / "__init__.py"
TOOL_ALLOCATION = BACKEND_ROOT / "app" / "agents" / "tools" / "agent_tool_allocation.py"
QUEUED_EXECUTION = BACKEND_ROOT / "app" / "services" / "queued_execution_use_case.py"
ORCHESTRATOR = BACKEND_ROOT / "app" / "agents" / "orchestrator.py"
CONTEXT_ASSEMBLER = BACKEND_ROOT / "app" / "services" / "context_assembler.py"
MEMORY_WRITER = BACKEND_ROOT / "app" / "services" / "memory_writer.py"
EPISODE_EXECUTOR = BACKEND_ROOT / "app" / "services" / "episode_workflow_execution.py"

FORBIDDEN_PROJECT_AUTHORITY_FIELDS = {
    "episodes_runtime",
    "progress",
    "total_cost",
    "total_tokens",
    "completed_episodes",
}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _class_fields(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(_source(path), filename=str(path))
    target = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    fields: set[str] = set()
    for node in target.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields.add(node.target.id)
    return fields


def test_project_write_aggregate_contains_no_runtime_or_derived_fields():
    assert _class_fields(STORY_PLAN, "ProjectDefinition").isdisjoint(
        FORBIDDEN_PROJECT_AUTHORITY_FIELDS
    )


def test_episode_coordinator_is_not_registered_as_production_agent():
    for path in (AGENTS_INIT, TOOL_ALLOCATION, QUEUED_EXECUTION):
        source = _source(path)
        assert "EpisodeOrchestratorAgent" not in source
        assert "AgentType.EPISODE_ORCHESTRATOR" not in source


def test_project_authority_contract_is_versioned_and_query_model_is_separate():
    domain_contract = BACKEND_ROOT / "app" / "domain" / "project_definition.py"
    assert domain_contract.exists()
    source = _source(domain_contract)
    assert "class ProjectDefinitionStore(Protocol)" in source
    assert "expected_version" in source
    assert "project_version_conflict" in source
    assert "class ProjectExecutionReadModel" in source
    assert "save(" not in source.split("class ProjectExecutionReadModel", 1)[1]


def test_mas_orchestrator_is_control_plane_with_injected_runtime_ports():
    source = _source(ORCHESTRATOR)
    assert 'AGENT_EXECUTION_MODE = "mas_control_plane"' in source
    assert "runtime_transition_port: OrchestrationRuntimeTransitionPort" in source
    assert "runtime_resume_port: OrchestrationRuntimeResumePort" in source
    assert "OrchestrationRuntimeTransitionFacade(" not in source
    assert "OrchestrationRuntimeResumeBootstrapFacade(" not in source


def test_context_assembler_is_read_only_and_memory_receipts_are_typed():
    context_source = _source(CONTEXT_ASSEMBLER)
    assert "persist_scene_info_ref" not in context_source
    assert ".write_text(" not in context_source
    assert "open(" not in context_source

    memory_source = _source(MEMORY_WRITER)
    assert "class MemoryWriteReceipt" in memory_source
    assert "reason_code: MemoryWriteReason" in memory_source
    assert "monitoring_service" not in memory_source


def test_music_allocation_is_supplier_neutral():
    allocation = _source(TOOL_ALLOCATION)
    audio_block = allocation.split("AgentType.AUDIO_GENERATOR:", 1)[1].split("]", 1)[0]
    assert '"music_generation"' in audio_block
    assert "suno" not in audio_block.lower()


def test_episode_execution_adapter_does_not_choose_terminal_runtime_state():
    source = _source(EPISODE_EXECUTOR)
    execute_body = source.split("async def execute_episode", 1)[1]
    assert "TaskStatus.COMPLETED" not in execute_body
    assert "TaskStatus.FAILED" not in execute_body
    assert "_update_task_status" not in source


def test_project_wrapper_composes_the_same_mas_orchestrator_for_episode_children():
    source = _source(QUEUED_EXECUTION)
    factory_body = source.split("def _create_default_episode_coordinator", 1)[1]
    assert "orchestrator = build_orchestrator_agent()" in factory_body
    assert "PersistentEpisodeWorkflowExecutor(orchestrator=orchestrator)" in factory_body
    assert "EpisodeOrchestratorAgent" not in factory_body
