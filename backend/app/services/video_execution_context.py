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

    execution_contract = ctx.get("execution_contract")
    if not isinstance(execution_contract, dict):
        execution_contract = {}
    storage = execution_contract.get("storage")
    if not isinstance(storage, dict):
        storage = {}
    constraints = execution_contract.get("constraints")
    if not isinstance(constraints, dict):
        constraints = {}

    def _raise_validation_error(message: str) -> None:
        if validation_error_factory is not None:
            raise validation_error_factory(message)
        raise ValueError(message)

    explicit_workflow_state_id = str(merged.get("workflow_state_id") or "").strip()
    bound_workflow_state_id = str(
        storage.get("workflow_state_id") or ctx.get("workflow_state_id") or ""
    ).strip()
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
    if isinstance(bound_generate_audio, bool):
        if explicit_generate_audio is not None and not isinstance(explicit_generate_audio, bool):
            _raise_validation_error("generate_audio must be boolean when provided")
        if isinstance(explicit_generate_audio, bool) and explicit_generate_audio != bound_generate_audio:
            _raise_validation_error("generate_audio conflicts with execution context")
        merged["generate_audio"] = bound_generate_audio

    return merged
