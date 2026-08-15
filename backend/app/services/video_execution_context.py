from __future__ import annotations

from typing import Any, Callable, Dict, Optional


ValidationErrorFactory = Callable[[str], Exception]


def merge_video_execution_context_into_params(
    params: Dict[str, Any],
    context: Optional[Dict[str, Any]],
    *,
    validation_error_factory: Optional[ValidationErrorFactory] = None,
) -> Dict[str, Any]:
    merged = dict(params or {})
    ctx = context if isinstance(context, dict) else {}

    def _raise_validation_error(message: str) -> None:
        if validation_error_factory is not None:
            raise validation_error_factory(message)
        raise ValueError(message)

    execution_contract = ctx.get("execution_contract")
    if not isinstance(execution_contract, dict):
        _raise_validation_error("execution_contract is required")
    if "workflow_state_id" in ctx:
        _raise_validation_error(
            "redundant workflow_state_id outside execution_contract is not supported"
        )
    constraints = execution_contract.get("constraints")
    if not isinstance(constraints, dict):
        constraints = {}

    explicit_workflow_state_id = merged.get("workflow_state_id")
    if explicit_workflow_state_id is not None and (
        type(explicit_workflow_state_id) is not str
        or not explicit_workflow_state_id
        or explicit_workflow_state_id != explicit_workflow_state_id.strip()
    ):
        _raise_validation_error("workflow_state_id must be a canonical string when provided")
    bound_workflow_state_id = execution_contract.get("workflow_state_id")
    if (
        type(bound_workflow_state_id) is not str
        or not bound_workflow_state_id
        or bound_workflow_state_id != bound_workflow_state_id.strip()
    ):
        _raise_validation_error(
            "execution_contract.workflow_state_id must be a canonical non-empty string"
        )
    if (
        explicit_workflow_state_id
        and bound_workflow_state_id
        and explicit_workflow_state_id != bound_workflow_state_id
    ):
        _raise_validation_error("workflow_state_id conflicts with execution context")
    if bound_workflow_state_id:
        merged["workflow_state_id"] = bound_workflow_state_id

    explicit_generate_audio = merged.get("generate_audio")
    bound_generate_audio = constraints.get("generate_audio")
    if type(bound_generate_audio) is bool:
        if explicit_generate_audio is not None and type(explicit_generate_audio) is not bool:
            _raise_validation_error("generate_audio must be boolean when provided")
        if (
            type(explicit_generate_audio) is bool
            and explicit_generate_audio != bound_generate_audio
        ):
            _raise_validation_error("generate_audio conflicts with execution context")
        merged["generate_audio"] = bound_generate_audio

    return merged
