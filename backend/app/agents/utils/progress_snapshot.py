from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict


def _safe_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _summarize_action_result(action_result: Any) -> Dict[str, Any]:
    if not isinstance(action_result, dict):
        return {}
    executed_calls = action_result.get("executed_calls")
    summary: Dict[str, Any] = {}
    if isinstance(executed_calls, list):
        success_count = 0
        failure_count = 0
        for item in executed_calls:
            if not isinstance(item, dict):
                continue
            if item.get("success") is True:
                success_count += 1
            elif item.get("success") is False:
                failure_count += 1
        summary["executed_call_count"] = len(executed_calls)
        summary["successful_call_count"] = success_count
        summary["failed_call_count"] = failure_count

    processed = action_result.get("processed")
    if processed is not None:
        summary["processed"] = _safe_int(processed)

    subtask_state = action_result.get("subtask_state")
    if isinstance(subtask_state, str) and subtask_state.strip():
        summary["subtask_state"] = subtask_state.strip()

    loop_end_reason = action_result.get("loop_end_reason")
    if isinstance(loop_end_reason, str) and loop_end_reason.strip():
        summary["loop_end_reason"] = loop_end_reason.strip()

    return summary


def _summarize_reflection_result(reflection_result: Any) -> Dict[str, Any]:
    if not isinstance(reflection_result, dict):
        return {}
    summary: Dict[str, Any] = {}
    if reflection_result.get("success") is not None:
        summary["success"] = bool(reflection_result.get("success"))
    reflection_summary = reflection_result.get("reflection_summary")
    if isinstance(reflection_summary, str) and reflection_summary.strip():
        text = reflection_summary.strip()
        summary["reflection_summary"] = text[:160] if len(text) > 160 else text
    return summary


def emit_progress_snapshot(func):
    """Decorator: after a reflect call, emit a one-line structured audit digest.

    - Does not alter behavior or return value; failures are swallowed.
    - Logging-only for audit; never injected into planner input.
    - Uses only round-local action/reflection data; does not derive parallel progress state.
    """

    @wraps(func)
    async def _wrapped(self, *args, **kwargs):
        result = await func(self, *args, **kwargs)
        try:
            # Feature toggle (optional; defaults to True if absent)
            try:
                from ...core.config import settings as _cfg
                enabled = bool(getattr(_cfg, "ENABLE_PROGRESS_SNAPSHOT", True))
            except Exception:
                enabled = True
            if not enabled:
                return result

            # iteration index (best-effort from wrapper args)
            iteration = None
            try:
                if len(args) >= 4:
                    iteration = int(args[3])
                elif "iteration" in kwargs:
                    iteration = int(kwargs["iteration"])
            except Exception:
                iteration = None

            action_result = args[0] if len(args) >= 1 else kwargs.get("action_result")
            wf_id = getattr(self, 'workflow_state_id', '') or ""
            snapshot = {
                "wf_id": str(wf_id),
                "agent": getattr(self, "agent_name", "unknown"),
                "iteration": iteration,
                "action_result_summary": _summarize_action_result(action_result),
                "reflection_summary": _summarize_reflection_result(result),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            try:
                line = json.dumps(snapshot, ensure_ascii=False)
            except Exception:
                # fallback best-effort
                line = str(snapshot)
            self.logger.info("PROGRESS_SNAPSHOT " + line)
        except Exception:
            # non-intrusive
            pass
        return result

    return _wrapped
