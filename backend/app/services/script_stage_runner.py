"""
Explicit stage runner for the script phase.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from sqlalchemy.orm import Session

from ..agents import ConceptPlannerAgent, ScriptWriterAgent
from ..agents.utils.llm_policy import LLMPolicyManager
from ..agents.utils.memory_helpers import agent_scope, get_mas_working_memory, mas_scope
from ..models import Task
from .memory_provider import MemoryServices, build_memory_services
from .script_review_contract import get_script_review_contract


class ScriptStageRunner:
    """Runs concept_planner/script_writer without depending on orchestrator private helpers."""

    def __init__(self, memory_services: MemoryServices | None = None):
        self._memory_services = memory_services or build_memory_services()
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "llm_policies.yaml")
        self._llm_policy = LLMPolicyManager(policy_file)
        self._concept_planner = ConceptPlannerAgent(
            llms=self._llm_policy.build_llms_for_agent("concept_planner"),
            memory_services=self._memory_services,
        )
        self._script_writer = ScriptWriterAgent(
            llms=self._llm_policy.build_llms_for_agent("script_writer"),
            memory_services=self._memory_services,
        )

    def _ensure_mas_memory(self, workflow_id: str) -> None:
        self._memory_services.short_term.create_or_get(workflow_id, mas_scope(workflow_id))

    def _ensure_agent_memory(self, workflow_id: str, agent_name: str) -> None:
        shared_view = get_mas_working_memory(workflow_id, service=self._memory_services.short_term)
        scope = agent_scope(workflow_id, agent_name)
        try:
            self._memory_services.short_term.reset(scope, workflow_id)
        except Exception:
            pass
        self._memory_services.short_term.create_or_get(
            workflow_id,
            scope,
            owner_agent=agent_name,
            shared_view=shared_view,
        )

    def _build_stage_input(self, task: Task, session_input_payload: Dict[str, Any], workflow_id: str) -> Dict[str, Any]:
        merged = dict(task.input_parameters or {})
        for key, value in dict(session_input_payload or {}).items():
            if key == "runtime_contracts":
                continue
            merged[key] = value
        merged["workflow_state_id"] = workflow_id
        review_contract = get_script_review_contract(session_input_payload)
        if review_contract:
            merged["script_review_contract"] = review_contract
        return merged

    async def run_initial(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        return await self._run_concept_then_script(
            task=task,
            workflow_id=workflow_id,
            session_input_payload=session_input_payload,
            db=db,
        )

    async def run_replan(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        return await self._run_concept_then_script(
            task=task,
            workflow_id=workflow_id,
            session_input_payload=session_input_payload,
            db=db,
        )

    async def run_revision(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        self._ensure_mas_memory(workflow_id)
        self._ensure_agent_memory(workflow_id, self._script_writer.agent_name)
        script_input = self._build_stage_input(task, session_input_payload, workflow_id)
        script_output = await self._script_writer.execute(
            task=task,
            input_data=script_input,
            db=db,
            execution_order=2,
        )
        return {
            "concept_output": None,
            "script_output": script_output,
        }

    async def _run_concept_then_script(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        self._ensure_mas_memory(workflow_id)

        base_input = self._build_stage_input(task, session_input_payload, workflow_id)

        self._ensure_agent_memory(workflow_id, self._concept_planner.agent_name)
        concept_output = await self._concept_planner.execute(
            task=task,
            input_data=dict(base_input),
            db=db,
            execution_order=1,
        )

        self._ensure_agent_memory(workflow_id, self._script_writer.agent_name)
        script_input = dict(base_input)
        script_input.update(concept_output or {})
        script_output = await self._script_writer.execute(
            task=task,
            input_data=script_input,
            db=db,
            execution_order=2,
        )
        return {
            "concept_output": concept_output,
            "script_output": script_output,
        }
