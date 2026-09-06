"""Application composition root for the MAS control-plane orchestrator."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from ..agents.orchestrator import OrchestratorAgent
from ..core.database import SessionLocal
from ..services.context_assembler import ContextContractAssembler
from ..services.memory_provider import MemoryServices, build_memory_services
from ..services.orchestration_runtime_resume_bootstrap_facade import (
    OrchestrationRuntimeResumeBootstrapFacade,
)
from ..services.orchestration_runtime_transition_facade import OrchestrationRuntimeTransitionFacade
from ..services.orchestration_state_adapter import OrchestrationStateAdapter
from .scene_info_reference_preparation import FileSceneInfoReferencePreparationAdapter


def build_orchestrator_agent(
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    memory_services: MemoryServices | None = None,
) -> OrchestratorAgent:
    memory = memory_services or build_memory_services()
    orchestration_state = OrchestrationStateAdapter(memory)
    context_assembler = ContextContractAssembler(memory)
    return OrchestratorAgent(
        memory_services=memory,
        runtime_transition_port=OrchestrationRuntimeTransitionFacade(
            context_contract_assembler=context_assembler,
            orchestration_state=orchestration_state,
            session_factory=session_factory,
        ),
        runtime_resume_port=OrchestrationRuntimeResumeBootstrapFacade(
            orchestration_state=orchestration_state,
            session_factory=session_factory,
        ),
        scene_info_reference_port=FileSceneInfoReferencePreparationAdapter(memory),
    )
