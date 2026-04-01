from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy


def _normalize_task_assignment(task_ctx: Dict[str, Any]) -> Dict[str, Any]:
    assignment: Dict[str, Any] = {}
    if not isinstance(task_ctx, dict):
        return assignment
    agent = str(task_ctx.get("agent") or "").strip()
    if agent:
        assignment["agent"] = agent
    if task_ctx.get("run") is not None:
        assignment["run"] = bool(task_ctx.get("run"))
    mission = str(task_ctx.get("mission") or "").strip()
    if mission:
        assignment["mission"] = mission
    deliverable = str(task_ctx.get("deliverable") or "").strip()
    if deliverable:
        assignment["deliverable"] = deliverable
    constraints = task_ctx.get("constraints")
    if isinstance(constraints, list):
        assignment["constraints"] = [
            str(item).strip() for item in constraints if str(item or "").strip()
        ]
    runtime_hints = task_ctx.get("runtime_hints")
    if isinstance(runtime_hints, dict) and runtime_hints:
        assignment["runtime_hints"] = deepcopy(runtime_hints)
    order = task_ctx.get("order")
    if order is not None:
        assignment["order"] = order
    return assignment


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _sorted_unique(values: List[int]) -> List[int]:
    return sorted(set(values))


def _build_progress_diagnostic(
    *,
    reason: str,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    diagnostic: Dict[str, Any] = {
        "status": "degraded",
        "reason": reason,
    }
    if detail:
        diagnostic["detail"] = detail
    return diagnostic


def _extract_planned_scene_numbers(
    static_ctx: Dict[str, Any],
) -> Tuple[List[int], Optional[Dict[str, Any]]]:
    if not isinstance(static_ctx, dict):
        return [], None
    scene_info_ref = str(static_ctx.get("scene_info_ref") or "").strip()
    if not scene_info_ref:
        return [], None
    try:
        from ...services.scene_info_reference_service import load_scene_info_payload

        payload = load_scene_info_payload(scene_info_ref)
    except Exception as exc:
        return [], _build_progress_diagnostic(
            reason="scene_info_ref_load_failed",
            detail=type(exc).__name__,
        )
    scenes = payload.get("scenes_to_generate") if isinstance(payload, dict) else []
    if not isinstance(scenes, list):
        return [], _build_progress_diagnostic(
            reason="scene_info_payload_invalid",
        )
    planned: List[int] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_number = _coerce_int(scene.get("scene_number"))
        if scene_number is not None:
            planned.append(scene_number)
    return _sorted_unique(planned), None


def _build_receipt(
    *,
    iteration: Optional[int],
    scene_number: int,
    success: bool,
    error_type: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    receipt: Dict[str, Any] = {
        "scene_number": scene_number,
        "status": "succeeded" if success else "failed",
    }
    if iteration is not None:
        receipt["iteration"] = iteration
    if error_type:
        receipt["error_type"] = error_type
    if reason:
        receipt["reason"] = reason
    return receipt


def _extract_receipts_from_act_log(
    *,
    act_log: List[Dict[str, Any]],
    iteration: Optional[int],
) -> List[Dict[str, Any]]:
    receipts: List[Dict[str, Any]] = []
    for item in act_log:
        if not isinstance(item, dict):
            continue
        scene_number = _coerce_int(item.get("scene_number"))
        success = item.get("success")
        if scene_number is None or not isinstance(success, bool):
            continue
        error_type = str(item.get("error_type") or "").strip() or None
        reason = str(item.get("error") or "").strip() or None
        receipts.append(
            _build_receipt(
                iteration=iteration,
                scene_number=scene_number,
                success=success,
                error_type=error_type,
                reason=reason,
            )
        )
    return receipts


def _extract_receipts_from_executed_calls(
    *,
    executed_calls: List[Dict[str, Any]],
    iteration: Optional[int],
) -> List[Dict[str, Any]]:
    receipts: List[Dict[str, Any]] = []
    for item in executed_calls:
        if not isinstance(item, dict):
            continue
        success = item.get("success")
        if not isinstance(success, bool):
            continue
        args = item.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        scene_number = _coerce_int(args.get("scene_number"))
        if scene_number is None:
            scene_number = _coerce_int(item.get("scene_number"))
        if scene_number is None:
            continue
        error_type = str(item.get("error_type") or "").strip() or None
        reason = str(item.get("error") or "").strip() or None
        receipts.append(
            _build_receipt(
                iteration=iteration,
                scene_number=scene_number,
                success=success,
                error_type=error_type,
                reason=reason,
            )
        )
    return receipts


def _extract_execution_receipts(iteration_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(iteration_context, dict):
        return []
    obs_records = iteration_context.get("obs_records")
    if not isinstance(obs_records, list):
        return []

    receipts: List[Dict[str, Any]] = []
    seen: set[Tuple[Optional[int], int, str]] = set()
    for record in obs_records:
        if not isinstance(record, dict):
            continue
        iteration = _coerce_int(record.get("iteration"))
        action_result = record.get("action_result")
        if not isinstance(action_result, dict):
            continue

        extracted: List[Dict[str, Any]] = []
        act_log = action_result.get("act_log")
        if isinstance(act_log, list) and act_log:
            extracted = _extract_receipts_from_act_log(
                act_log=act_log,
                iteration=iteration,
            )
        else:
            executed_calls = action_result.get("executed_calls")
            if isinstance(executed_calls, list) and executed_calls:
                extracted = _extract_receipts_from_executed_calls(
                    executed_calls=executed_calls,
                    iteration=iteration,
                )

        for receipt in extracted:
            scene_number = _coerce_int(receipt.get("scene_number"))
            status = str(receipt.get("status") or "").strip()
            if scene_number is None or not status:
                continue
            receipt_key = (_coerce_int(receipt.get("iteration")), scene_number, status)
            if receipt_key in seen:
                continue
            seen.add(receipt_key)
            receipts.append(receipt)
    return receipts


def _build_progress_read_model(
    *,
    static_ctx: Dict[str, Any],
    iteration_context: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    planned_scene_numbers, diagnostic = _extract_planned_scene_numbers(static_ctx)
    if not planned_scene_numbers:
        return {}, diagnostic

    planned_set = set(planned_scene_numbers)
    receipts = [
        receipt
        for receipt in _extract_execution_receipts(iteration_context)
        if _coerce_int(receipt.get("scene_number")) in planned_set
    ]
    successful_scene_numbers = _sorted_unique(
        [
            int(receipt["scene_number"])
            for receipt in receipts
            if receipt.get("status") == "succeeded"
        ]
    )
    successful_set = set(successful_scene_numbers)
    remaining_scene_numbers = [
        scene_number
        for scene_number in planned_scene_numbers
        if scene_number not in successful_set
    ]
    return (
        {
            "planned_scene_numbers": planned_scene_numbers,
            "successful_scene_numbers": successful_scene_numbers,
            "remaining_scene_numbers": remaining_scene_numbers,
            "recent_execution_receipts": receipts[-5:],
        },
        None,
    )


def build_plan_context(
    *,
    input_data: Dict[str, Any],
    iteration_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """统一构造 PLAN 输入上下文（task/static/iteration 分区）。"""
    ctx: Dict[str, Any] = {}
    diagnostics: Dict[str, Any] = {}
    try:
        if isinstance(input_data, dict):
            task_ctx = input_data.get("task") or {}
            if isinstance(task_ctx, dict) and task_ctx:
                # 使用深拷贝避免下游修改输入
                ctx["task"] = deepcopy(task_ctx)
                task_assignment = _normalize_task_assignment(task_ctx)
                if task_assignment:
                    ctx["task_assignment"] = task_assignment
            static_ctx = input_data.get("static_context") or {}
            if isinstance(static_ctx, dict) and static_ctx:
                ctx["static_context"] = deepcopy(static_ctx)
                progress_read_model, progress_diagnostic = _build_progress_read_model(
                    static_ctx=static_ctx,
                    iteration_context=iteration_context,
                )
                if progress_read_model:
                    ctx["progress_read_model"] = progress_read_model
                if progress_diagnostic:
                    diagnostics["progress_read_model"] = progress_diagnostic
            execution_contract = input_data.get("execution_contract") or {}
            if isinstance(execution_contract, dict) and execution_contract:
                ctx["execution_contract"] = deepcopy(execution_contract)
    except Exception as exc:
        diagnostics["plan_context"] = _build_progress_diagnostic(
            reason="plan_context_build_failed",
            detail=type(exc).__name__,
        )
    if isinstance(iteration_context, dict):
        ctx["iteration_context"] = deepcopy(iteration_context)
    if diagnostics:
        ctx["plan_context_diagnostics"] = diagnostics
    return ctx


__all__ = ["build_plan_context"]
