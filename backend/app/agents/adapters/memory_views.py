from __future__ import annotations

"""Shared memory view helpers for orchestrator → agent context construction."""

from typing import Any, Dict, List, Optional

from ..services.mas_shared_memory import get_shared_wm
from ..memory.short_term.workflow_facts import WorkflowFactStoreError
from .video import VideoMemoryAdapter
from ...services.memory_provider import get_memory_services


def load_scene_overview(workflow_id: str) -> Dict[str, Any]:
    """Return MAS working-memory projection for scenes/state."""
    try:
        shared_view = get_shared_wm().get_task(workflow_id)
    except Exception:
        return {}
    if shared_view is None:
        return {}
    adapter = VideoMemoryAdapter(shared_view)
    return adapter.build_fact_observation()


def load_scene_scripts(workflow_id: str) -> Dict[int, Dict[str, Any]]:
    """Fetch per-scene script facts from the workflow fact store."""
    store = _fact_store()
    if store is None:
        return {}
    try:
        payload = store.get(workflow_id, "project.scene_scripts", default={})
    except WorkflowFactStoreError:
        return {}
    return _normalize_scene_dict(payload)


def load_roles_context(workflow_id: str) -> Dict[str, Any]:
    """Return concept-level roles/settings context."""
    concept_plan = load_concept_plan(workflow_id)
    roles = concept_plan.get("roles")
    overview = {
        "concept_overview": concept_plan.get("overview") or concept_plan.get("story_overview") or "",
        "style": concept_plan.get("intelligent_style_design") or {},
        "roles": roles if isinstance(roles, list) else [],
    }
    return overview


def load_concept_plan(workflow_id: str) -> Dict[str, Any]:
    store = _fact_store()
    if store is None:
        return {}
    try:
        plan = store.get(workflow_id, "project.concept_plan", default={}) or {}
    except WorkflowFactStoreError:
        plan = {}
    return plan if isinstance(plan, dict) else {}


def build_media_agent_context(
    workflow_id: str,
    *,
    include_scripts: bool = True,
    include_roles: bool = False,
) -> Dict[str, Any]:
    """Convenience helper for orchestrator when preparing agent inputs."""
    context: Dict[str, Any] = {}
    overview = load_scene_overview(workflow_id)
    if overview:
        context["scene_overview"] = overview
    if include_scripts:
        scripts = load_scene_scripts(workflow_id)
        if scripts:
            context["scene_scripts"] = scripts
    if include_roles:
        roles_ctx = load_roles_context(workflow_id)
        if roles_ctx:
            context["roles_context"] = roles_ctx
    return context


def build_image_generation_context(workflow_id: str) -> Dict[str, Any]:
    """Aggregates concept/scene/script facts for ImageGenerator."""
    concept_plan = load_concept_plan(workflow_id)
    overview = load_scene_overview(workflow_id)
    scripts = load_scene_scripts(workflow_id)

    concept_scene_index: Dict[int, Dict[str, Any]] = {}
    target_map: Dict[int, str] = {}
    for scene in (concept_plan.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        try:
            sn = int(scene.get("scene_number"))
        except Exception:
            continue
        concept_scene_index[sn] = scene
        mode = (scene.get("generation_mode") or scene.get("image_generation_mode") or "").strip()
        if mode:
            target_map[sn] = mode.lower()

    scenes_to_generate: List[Dict[str, Any]] = []
    scenes_to_skip: List[Dict[str, Any]] = []
    for scene in (overview.get("scenes") if isinstance(overview, dict) else []) or []:
        if not isinstance(scene, dict):
            continue
        sn = _coerce_int(scene.get("scene_number"))
        if sn is None:
            continue
        script_entry = scripts.get(sn) if isinstance(scripts, dict) else {}
        concept_entry = concept_scene_index.get(sn, {})
        image_url = scene.get("image_url", "")
        mode = target_map.get(sn) or ("reuse" if image_url else "generate")
        payload = {
            "scene_number": sn,
            "title": concept_entry.get("title", ""),
            "visual_description": scene.get("visual_description", ""),
            "narrative_description": scene.get("narrative_description", ""),
            "duration": scene.get("duration", 0.0),
            "motion_beats": list(
                (script_entry or {}).get("motion_beats")
                or concept_entry.get("motion_beats")
                or scene.get("motion_beats", [])
            ),
            "characters_present": list((script_entry or {}).get("characters_present") or concept_entry.get("characters_present") or []),
            "character_descriptions": list((script_entry or {}).get("character_descriptions") or concept_entry.get("character_descriptions") or []),
            "script_text": (script_entry or {}).get("script_text", ""),
            "voice_over_text": (script_entry or {}).get("voice_over_text", ""),
            "background_music_style": (script_entry or {}).get("background_music_style", ""),
        }
        if mode in {"skip", "reuse"} or image_url:
            scenes_to_skip.append({"scene_number": sn, "reason": mode, "reuse_from": None})
        else:
            scenes_to_generate.append(payload)

    return {
        "context": {
            "task_type": "batch_image_generation",
            "workflow_state_id": workflow_id,
            "total_scenes": len(overview.get("scenes", [])) if isinstance(overview, dict) else 0,
            "scenes_to_generate": scenes_to_generate,
            "scenes_to_skip": scenes_to_skip,
            "concept_plan": concept_plan,
            "intelligent_style": concept_plan.get("intelligent_style_design") or {},
        }
    }


def extract_failed_scenes(overview: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return failed scene records from a scene overview projection."""
    if not isinstance(overview, dict):
        return []
    failed_payloads: List[Dict[str, Any]] = []
    for scene in (overview.get("scenes") or []):
        if not isinstance(scene, dict) or not scene.get("failed"):
            continue
        sn = _coerce_int(scene.get("scene_number"))
        if sn is None:
            continue
        reason = scene.get("failure_reason") or scene.get("reason") or "generation_failed"
        entry = {
            "scene_number": sn,
            "error": reason,
        }
        metadata = scene.get("metadata")
        if isinstance(metadata, dict) and metadata:
            entry["metadata"] = metadata
        failed_payloads.append(entry)
    return failed_payloads


def _normalize_scene_dict(payload: Any) -> Dict[int, Dict[str, Any]]:
    result: Dict[int, Dict[str, Any]] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            try:
                sn = int(key)
            except Exception:
                try:
                    sn = int(value.get("scene_number")) if isinstance(value, dict) else None
                except Exception:
                    sn = None
            if sn is None:
                continue
            if isinstance(value, dict):
                result[sn] = dict(value)
            else:
                result[sn] = {"value": value}
    elif isinstance(payload, list):
        for value in payload:
            if not isinstance(value, dict):
                continue
            sn_raw = value.get("scene_number")
            try:
                sn = int(sn_raw)
            except Exception:
                continue
            result[sn] = dict(value)
    return result


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _fact_store():
    services = get_memory_services()
    return getattr(services, "fact_store", None)


__all__ = [
    "load_scene_overview",
    "load_scene_scripts",
    "load_roles_context",
    "load_concept_plan",
    "build_media_agent_context",
    "build_image_generation_context",
    "extract_failed_scenes",
]
