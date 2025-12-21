from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, List


def _safe_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def emit_progress_snapshot(func):
    """Decorator: after a reflect call, emit a one-line structured progress snapshot log.

    - Does not alter behavior or return value; failures are swallowed.
    - 只读派生：MAS 级 state view + Agent 级 iteration view（单一统计口径）。
    - Never injected into LLM; logging-only for audit.
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

            summary: Dict[str, Any] = {"total": 0, "pending": 0, "completed": 0, "failed": 0}
            agent_view: Dict[str, Any] = {}

            # totals：优先从 Shared WM 派生（事实化），不依赖 Agent WM 的内部实现
            try:
                from .memory_helpers import get_mas_working_memory
                from ..adapters.state.memory_state import build_memory_state
                from .iteration_view import build_agent_iteration_view

                wf_id = getattr(self, 'workflow_state_id', '') or ""
                service = getattr(self, 'short_term_service', None)
                shared = get_mas_working_memory(str(wf_id), service=service) if wf_id and service else None
                wm_state = build_memory_state(shared) if shared is not None else {}
                if isinstance(wm_state, dict):
                    summary = {
                        "total": _safe_int(wm_state.get("total_scenes")),
                        "pending": _safe_int(wm_state.get("pending_scenes")),
                        "completed": _safe_int(wm_state.get("completed_scenes")),
                        "failed": _safe_int(wm_state.get("failed_scenes")),
                    }
                # Agent iteration view（只读汇总，避免重复统计路径）
                if wf_id and service:
                    agent_view = build_agent_iteration_view(str(wf_id), getattr(self, 'agent_name', ''), service=service)
            except Exception:
                pass

            # iteration index (best-effort from wrapper args)
            iteration = None
            try:
                if len(args) >= 4:
                    iteration = int(args[3])
                elif "iteration" in kwargs:
                    iteration = int(kwargs["iteration"])
            except Exception:
                iteration = None

            wf_id = getattr(self, 'workflow_state_id', '') or ""
            snapshot = {
                "wf_id": str(wf_id),
                "agent": getattr(self, "agent_name", "unknown"),
                "iteration": iteration,
                "totals": summary,
                "agent_view": agent_view or {},
                "artifacts": None,
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
