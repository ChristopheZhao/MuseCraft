from __future__ import annotations

"""Logging helpers for ReAct agents."""

from typing import Any, Dict, List


def summarize_observation(state: Any) -> str:
    """Generate a lightweight observation summary for logs."""
    try:
        if isinstance(state, dict):
            return f"State: {len(state)} observations"
        if isinstance(state, list):
            return f"State(list): {len(state)} items"
        return "State: recorded"
    except Exception:
        return "State: recorded"


def summarize_plan(action_plan: Any) -> str:
    """Generate a plan summary for logs."""
    try:
        if isinstance(action_plan, dict) and action_plan.get("tool_calls"):
            tcs = action_plan.get("tool_calls") or []
            return f"Plan: {len(tcs)} tool calls"
        if isinstance(action_plan, dict) and action_plan.get("action"):
            return f"Plan: action={action_plan.get('action')}"
        if isinstance(action_plan, dict) and action_plan.get("strategy"):
            return f"Plan: {action_plan.get('strategy')}"
        return "Plan: prepared"
    except Exception:
        return "Plan: prepared"


def summarize_action_result(action_result: Any) -> str:
    """Generate a neutral action result summary for logs."""
    try:
        if hasattr(action_result, 'success'):
            ok = getattr(action_result, 'success')
            return f"Result: {'ok' if ok else 'fail'} (output)"

        if isinstance(action_result, dict):
            total_calls = 0
            succ = 0
            fail = 0
            artifacts = 0
            try:
                ecs = action_result.get('executed_calls') or []
                if isinstance(ecs, list):
                    total_calls = len(ecs)
                    succ = sum(1 for c in ecs if isinstance(c, dict) and c.get('success'))
                    fail = max(0, total_calls - succ)
                    for c in ecs:
                        if not isinstance(c, dict):
                            continue
                        payload = c.get('result')
                        if hasattr(payload, 'result'):
                            payload = getattr(payload, 'result')
                        if isinstance(payload, dict) and (
                            payload.get('file_path')
                            or payload.get('image_url')
                            or payload.get('video_url')
                            or payload.get('audio_url')
                        ):
                            artifacts += 1
            except Exception:
                pass

            gens = action_result.get('generation_results') if isinstance(action_result, dict) else None
            scene_ids = []
            completed_videos = 0
            try:
                for g in gens or []:
                    if not isinstance(g, dict):
                        continue
                    if g.get('success') and (g.get('video_url') or g.get('video_path')):
                        completed_videos += 1
                    sn = g.get('scene_number')
                    if sn is not None:
                        try:
                            scene_ids.append(int(sn))
                        except Exception:
                            pass
            except Exception:
                pass
            scene_ids = sorted(list({s for s in scene_ids if isinstance(s, int)}))

            if total_calls or gens:
                parts: List[str] = [
                    f"calls={total_calls}, ok={succ}, fail={fail}",
                    f"artifacts={artifacts}",
                ]
                if completed_videos:
                    parts.append(f"videos_completed={completed_videos}")
                if scene_ids:
                    preview = ",".join(map(str, scene_ids[:6]))
                    parts.append(f"scenes={preview}")
                return "Result: " + "; ".join(parts)

            keys = list(action_result.keys())
            return f"Result: dict[{len(keys)}]"

        if isinstance(action_result, list):
            return f"Result: list[{len(action_result)}]"
        if isinstance(action_result, str):
            return f"Result: str[{len(action_result)}]"
        return "Result: recorded"
    except Exception:
        return "Result: recorded"

