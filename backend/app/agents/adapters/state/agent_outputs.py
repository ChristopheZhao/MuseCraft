"""MAS deliverables helpers (facts-based, no decisions).

目的：
- Orchestrator 统一从 MAS WorkingMemory（SoT）读取各 agent 的交付产物；
- 避免在各个 agent 子类的 finalize 中重复“聚合/回读”逻辑；
- 为调度/验收/持久化提供统一入口（不依赖 agent_output 的偶然字段）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING, Union

from ...utils.memory_helpers import get_mas_working_memory
from ....models import AgentType

if TYPE_CHECKING:
    from ...memory.short_term.service import WorkingMemoryService
    from ...memory.short_term.working_memory import WorkingMemory


AgentKey = Union[AgentType, str]


_AGENT_OUTPUT_KEY_MAP: Dict[str, str] = {
    # Scene-level buckets
    AgentType.IMAGE_GENERATOR.value: "scene_outputs.image",
    AgentType.VIDEO_GENERATOR.value: "scene_outputs.video",
    AgentType.VOICE_SYNTHESIZER.value: "scene_outputs.voice",
    # Project-level deliverables
    AgentType.AUDIO_GENERATOR.value: "project.background_music",
    AgentType.VIDEO_COMPOSER.value: "project.final_video",
    # Planning / scripts
    AgentType.CONCEPT_PLANNER.value: "project.concept_plan",
    AgentType.SCRIPT_WRITER.value: "project.scene_scripts",
}


def _agent_key(agent: AgentKey) -> str:
    if isinstance(agent, AgentType):
        return agent.value
    return str(agent or "")


def get_agent_output_key(agent: AgentKey) -> Optional[str]:
    """Return the MAS WM key for an agent's deliverable SoT."""
    key = _AGENT_OUTPUT_KEY_MAP.get(_agent_key(agent))
    return key if isinstance(key, str) and key else None


def get_agent_outputs_from_mas(
    workflow_id: str,
    agent: AgentKey,
    *,
    service: "WorkingMemoryService",
) -> Any:
    """Fetch agent deliverables from MAS WM (SoT).

    Notes:
    - Returns the raw WM payload (dict/list/str/...) stored under the mapped key.
    - This is intentionally "facts-only": no normalization, no business decisions.
    """
    wf_id = str(workflow_id or "")
    if not wf_id:
        return {}
    key = get_agent_output_key(agent)
    if not key:
        return {}
    wm = get_mas_working_memory(wf_id, service=service)
    try:
        return wm.get(key, {})
    except Exception:
        return {}


def has_project_artifact(value: Any, *, url_key: str = "url", path_key: str = "path") -> bool:
    if not isinstance(value, dict):
        return False
    return bool(str(value.get(path_key) or "").strip() or str(value.get(url_key) or "").strip())


def has_background_music(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(str(value.get("audio_path") or "").strip() or str(value.get("audio_url") or "").strip())


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _scene_numbers_from_bucket(bucket: Any) -> set[int]:
    out: set[int] = set()
    if not isinstance(bucket, dict):
        return out
    for k, v in bucket.items():
        sn = _coerce_int(k)
        if sn is None and isinstance(v, dict):
            sn = _coerce_int(v.get("scene_number"))
        if sn is None:
            continue
        out.add(sn)
    return out


def assess_agent_delivery(
    workflow_id: str,
    agent: AgentKey,
    *,
    service: "WorkingMemoryService",
) -> Dict[str, Any]:
    """Assess whether an agent's deliverable exists in MAS WM.

    This is an orchestrator-side acceptance helper. It does NOT encode LLM decisions;
    it only checks presence of deliverable facts in the SoT.
    """
    wf_id = str(workflow_id or "")
    if not wf_id:
        return {"subtask_state": "error", "pending": 0, "completed": 0, "total": 0}

    agent_key = _agent_key(agent)
    wm = get_mas_working_memory(wf_id, service=service)

    # Scene overview for expected scene count
    overview = wm.get("scene_overview", {}) if wm is not None else {}
    scenes = overview.get("scenes") if isinstance(overview, dict) else []
    total = len(scenes) if isinstance(scenes, list) else 0

    if agent_key == AgentType.VIDEO_COMPOSER.value:
        fv = wm.get("project.final_video", {}) if wm is not None else {}
        ok = has_project_artifact(fv, url_key="url", path_key="path")
        return {"subtask_state": "complete" if ok else "partial", "pending": 0 if ok else 1, "completed": 1 if ok else 0, "total": 1}

    if agent_key == AgentType.AUDIO_GENERATOR.value:
        bgm = wm.get("project.background_music", {}) if wm is not None else {}
        ok = has_background_music(bgm)
        return {"subtask_state": "complete" if ok else "partial", "pending": 0 if ok else 1, "completed": 1 if ok else 0, "total": 1}

    if agent_key == AgentType.SCRIPT_WRITER.value:
        scripts = wm.get("project.scene_scripts", {}) if wm is not None else {}
        completed = len(scripts) if isinstance(scripts, dict) else 0
        pending = max(total - completed, 0) if total else 0
        st = "complete" if total and pending == 0 else ("partial" if completed else "partial")
        return {"subtask_state": st, "pending": pending, "completed": completed, "total": total}

    if agent_key == AgentType.CONCEPT_PLANNER.value:
        concept = wm.get("project.concept_plan", {}) if wm is not None else {}
        ok = isinstance(concept, dict) and bool(concept)
        return {"subtask_state": "complete" if ok else "partial", "pending": 0 if ok else 1, "completed": 1 if ok else 0, "total": 1}

    # Scene-level buckets: use presence in scene_outputs.<kind>, with image reuse via overview.image_url.
    if agent_key == AgentType.IMAGE_GENERATOR.value:
        bucket = wm.get("scene_outputs.image", {}) if wm is not None else {}
        done = _scene_numbers_from_bucket(bucket)
        # reuse images already present in overview
        if isinstance(scenes, list):
            for s in scenes:
                if not isinstance(s, dict):
                    continue
                sn = _coerce_int(s.get("scene_number"))
                if sn is None:
                    continue
                if sn in done:
                    continue
                if str(s.get("image_url") or "").strip():
                    done.add(sn)
        completed = len(done)
        pending = max(total - completed, 0) if total else 0
        st = "complete" if total and pending == 0 else ("partial" if completed else "partial")
        return {"subtask_state": st, "pending": pending, "completed": completed, "total": total}

    if agent_key == AgentType.VIDEO_GENERATOR.value:
        bucket = wm.get("scene_outputs.video", {}) if wm is not None else {}
        done = _scene_numbers_from_bucket(bucket)
        completed = len(done)
        pending = max(total - completed, 0) if total else 0
        st = "complete" if total and pending == 0 else ("partial" if completed else "partial")
        return {"subtask_state": st, "pending": pending, "completed": completed, "total": total}

    if agent_key == AgentType.VOICE_SYNTHESIZER.value:
        bucket = wm.get("scene_outputs.voice", {}) if wm is not None else {}
        done = _scene_numbers_from_bucket(bucket)

        # If voice_plan provides per-scene guidance, only count narratable scenes as expected.
        try:
            voice_plan = wm.get("project.voice_plan", {}) if wm is not None else {}
        except Exception:
            voice_plan = {}
        if isinstance(voice_plan, dict) and voice_plan:
            enabled = bool(voice_plan.get("enabled", True))
            mode = str(voice_plan.get("mode", "") or "").strip().lower()
            if not enabled or mode == "none":
                return {"subtask_state": "complete", "pending": 0, "completed": 0, "total": 0}
            guidance = voice_plan.get("scene_guidance") or []
            if isinstance(guidance, list) and guidance:
                expected: set[int] = set()
                for g in guidance:
                    if not isinstance(g, dict):
                        continue
                    if g.get("should_narrate", True) is False:
                        continue
                    sn = _coerce_int(g.get("scene_number"))
                    if sn is None:
                        continue
                    expected.add(sn)
                if expected:
                    completed = len(done & expected)
                    pending = max(len(expected) - completed, 0)
                    st = "complete" if pending == 0 else ("partial" if completed else "partial")
                    return {"subtask_state": st, "pending": pending, "completed": completed, "total": len(expected)}

        completed = len(done)
        pending = max(total - completed, 0) if total else 0
        st = "complete" if total and pending == 0 else ("partial" if completed else "partial")
        return {"subtask_state": st, "pending": pending, "completed": completed, "total": total}

    return {"subtask_state": "partial", "pending": 0, "completed": 0, "total": total}


__all__ = [
    "get_agent_output_key",
    "get_agent_outputs_from_mas",
    "assess_agent_delivery",
    "has_project_artifact",
    "has_background_music",
]
