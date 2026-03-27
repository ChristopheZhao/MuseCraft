"""
Explicit project-level workflow job contract.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


PROJECT_JOB_KIND_KEY = "job_kind"
PROJECT_JOB_HANDLER_KEY = "handler_key"

PROJECT_JOB_KIND_WORKFLOW = "project_workflow"
PROJECT_JOB_HANDLER_PLAN_PROJECT = "plan_project"


def attach_project_plan_contract(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    """Attach the explicit planning job contract to a project payload."""

    contract_payload = dict(payload or {})
    contract_payload[PROJECT_JOB_KIND_KEY] = PROJECT_JOB_KIND_WORKFLOW
    contract_payload[PROJECT_JOB_HANDLER_KEY] = PROJECT_JOB_HANDLER_PLAN_PROJECT
    return contract_payload


def resolve_project_job_contract(payload: Dict[str, Any] | None) -> Tuple[str, str]:
    """Resolve the explicit project-job routing contract from task payload."""

    contract_payload = dict(payload or {})
    job_kind = str(contract_payload.get(PROJECT_JOB_KIND_KEY) or "").strip()
    handler_key = str(contract_payload.get(PROJECT_JOB_HANDLER_KEY) or "").strip()
    if not job_kind or not handler_key:
        raise ValueError("Project planning task missing explicit job_kind/handler_key contract")
    return job_kind, handler_key


def is_project_plan_contract(job_kind: str, handler_key: str) -> bool:
    return (
        job_kind == PROJECT_JOB_KIND_WORKFLOW
        and handler_key == PROJECT_JOB_HANDLER_PLAN_PROJECT
    )
