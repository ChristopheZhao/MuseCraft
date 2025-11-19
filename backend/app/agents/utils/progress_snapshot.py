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
    - 使用 WorkingMemory（源自 Shared WM）事实，不依赖 Agent 内部状态。
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

            wm = None
            try:
                wm = getattr(self, 'wm', None)
            except Exception:
                wm = None
            summary: Dict[str, Any] = {"total": 0, "pending": 0, "completed": 0, "failed": 0}
            # executed scenes for this round (delta view)
            executed_scene_ids: List[int] = []

            if wm is not None:
                try:
                    s, facts = wm.classify_scenes()
                    # normalize summary
                    summary = {
                        "total": _safe_int((s or {}).get("total")),
                        "pending": _safe_int((s or {}).get("pending")),
                        "completed": _safe_int((s or {}).get("completed")),
                        "failed": _safe_int((s or {}).get("failed")),
                    }
                    # derive this-round executed scene ids from last_round_results (if available)
                    try:
                        lrr = list(ictx.get("last_round_results", []) or [])
                        for it in lrr:
                            if not isinstance(it, dict):
                                continue
                            sn = it.get("scene_number")
                            if isinstance(sn, int) or (isinstance(sn, str) and str(sn).isdigit()):
                                val = int(sn)
                                if val not in executed_scene_ids:
                                    executed_scene_ids.append(val)
                    except Exception:
                        pass
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

            # 尽量从 WM 推导回合执行的轻量视图
            try:
                executed_scene_ids = []
                if wm is not None and hasattr(wm, 'latest_iteration_artifacts'):
                    arts = wm.latest_iteration_artifacts(limit=8)
                    for it in arts or []:
                        sn = it.get('scene_number') if isinstance(it, dict) else None
                        if isinstance(sn, int) or (isinstance(sn, str) and str(sn).isdigit()):
                            val = int(sn)
                            if val not in executed_scene_ids:
                                executed_scene_ids.append(val)
            except Exception:
                pass
            wf_id = getattr(self, 'workflow_state_id', '') or ""
            snapshot = {
                "wf_id": str(wf_id),
                "agent": getattr(self, "agent_name", "unknown"),
                "iteration": iteration,
                "totals": summary,
                "round": {
                    "executed_scene_ids": executed_scene_ids,
                },
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
