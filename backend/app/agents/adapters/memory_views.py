from __future__ import annotations

"""Shared memory view helpers for orchestrator → agent context construction."""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .video import VideoMemoryAdapter
from ..utils.memory_helpers import get_mas_working_memory

if TYPE_CHECKING:
    from ..memory.short_term.service import WorkingMemoryService


def load_scene_overview(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[str, Any]:
    """Return MAS working-memory projection for scenes/state."""
    wm = get_mas_working_memory(str(workflow_id), service=service)
    if wm is None:
        return {}
    overview = wm.get("scene_overview", {})
    if isinstance(overview, dict) and overview:
        # Normalize: merge generated asset URLs from scene_outputs.* into overview view (do not mutate WM in-place)
        try:
            scenes = overview.get("scenes") if isinstance(overview, dict) else None
            if isinstance(scenes, list) and scenes:
                image_bucket = wm.get("scene_outputs.image", {}) or {}
                if isinstance(image_bucket, dict) and image_bucket:
                    updated_scenes: List[Dict[str, Any]] = []
                    for s in scenes:
                        if not isinstance(s, dict):
                            continue
                        sn = _coerce_int(s.get("scene_number"))
                        if sn is not None and not (s.get("image_url") or "").strip():
                            rec = image_bucket.get(sn) or image_bucket.get(str(sn))
                            if isinstance(rec, dict) and isinstance(rec.get("image_url"), str) and rec.get("image_url"):
                                s2 = dict(s)
                                s2["image_url"] = rec.get("image_url")
                                updated_scenes.append(s2)
                                continue
                        updated_scenes.append(s)
                    overview = dict(overview)
                    overview["scenes"] = updated_scenes
        except Exception:
            pass
        return overview
    # legacy path: adapt VideoMemoryAdapter over WM if snapshot present
    try:
        adapter = VideoMemoryAdapter(wm)
        return adapter.build_fact_observation()
    except Exception:
        return {}


def load_scene_scripts(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[int, Dict[str, Any]]:
    """Fetch per-scene script facts from the workflow fact store."""
    try:
        wm = get_mas_working_memory(workflow_id, service=service)
        payload = wm.get("project.scene_scripts", {})
        if isinstance(payload, dict):
            return _normalize_scene_dict(payload)
    except Exception:
        return {}
    return {}


def load_roles_context(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[str, Any]:
    """Return concept-level roles/settings context."""
    concept_plan = load_concept_plan(workflow_id, service=service)
    roles = concept_plan.get("roles")
    overview = {
        "concept_overview": concept_plan.get("overview") or concept_plan.get("story_overview") or "",
        "style": concept_plan.get("intelligent_style_design") or {},
        "roles": roles if isinstance(roles, list) else [],
    }
    return overview


def load_concept_plan(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[str, Any]:
    try:
        wm = get_mas_working_memory(workflow_id, service=service)
        plan = wm.get("project.concept_plan", {}) or {}
        if isinstance(plan, dict):
            return plan
    except Exception:
        pass
    return {}


def build_media_agent_context(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
    include_scripts: bool = True,
    include_roles: bool = False,
) -> Dict[str, Any]:
    """Convenience helper for orchestrator when preparing agent inputs."""
    context: Dict[str, Any] = {}
    overview = load_scene_overview(workflow_id, service=service)
    if overview:
        context["scene_overview"] = overview
    if include_scripts:
        scripts = load_scene_scripts(workflow_id, service=service)
        if scripts:
            context["scene_scripts"] = scripts
    if include_roles:
        roles_ctx = load_roles_context(workflow_id, service=service)
        if roles_ctx:
            context["roles_context"] = roles_ctx
    return context


def build_image_generation_context(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[str, Any]:
    """Aggregates concept/scene/script facts for ImageGenerator."""
    concept_plan = load_concept_plan(workflow_id, service=service)
    overview = load_scene_overview(workflow_id, service=service)
    scripts = load_scene_scripts(workflow_id, service=service)

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


def build_video_generation_context(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[str, Any]:
    """Aggregates concept/scene/script facts for VideoGenerator."""
    concept_plan = load_concept_plan(workflow_id, service=service)
    overview = load_scene_overview(workflow_id, service=service)
    scripts = load_scene_scripts(workflow_id, service=service)

    wm = get_mas_working_memory(workflow_id, service=service)
    video_bucket = wm.get("scene_outputs.video", {}) if wm is not None else {}

    concept_scene_index: Dict[int, Dict[str, Any]] = {}
    for scene in (concept_plan.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        try:
            sn = int(scene.get("scene_number"))
        except Exception:
            continue
        concept_scene_index[sn] = scene

    scenes_source = overview.get("scenes") if isinstance(overview, dict) else None
    if not scenes_source:
        scenes_source = concept_plan.get("scenes") or []

    scenes_to_generate: List[Dict[str, Any]] = []
    scenes_completed: List[Dict[str, Any]] = []
    scenes_blocked: List[Dict[str, Any]] = []
    for scene in scenes_source or []:
        if not isinstance(scene, dict):
            continue
        sn = _coerce_int(scene.get("scene_number"))
        if sn is None:
            continue
        script_entry = scripts.get(sn) if isinstance(scripts, dict) else {}
        concept_entry = concept_scene_index.get(sn, {})
        image_url = scene.get("image_url") or concept_entry.get("image_url") or ""

        video_rec = {}
        if isinstance(video_bucket, dict):
            video_rec = video_bucket.get(sn) or video_bucket.get(str(sn)) or {}
        if not isinstance(video_rec, dict):
            video_rec = {}
        video_url = video_rec.get("video_url") or video_rec.get("url") or ""
        video_path = video_rec.get("video_path") or video_rec.get("path") or video_rec.get("file_path") or ""

        if video_url or video_path:
            scenes_completed.append(
                {
                    "scene_number": sn,
                    "video_url": video_url,
                    "video_path": video_path,
                }
            )
            continue

        if not image_url:
            scenes_blocked.append(
                {
                    "scene_number": sn,
                    "reason": "missing_reference_image",
                }
            )
            continue

        depends_on_scene = (
            concept_entry.get("depends_on_scene")
            or scene.get("depends_on_scene")
            or concept_entry.get("depends_on")
            or scene.get("depends_on")
        )
        depends_on_scene = _coerce_int(depends_on_scene)
        payload = {
            "scene_number": sn,
            "title": concept_entry.get("title", ""),
            "visual_description": scene.get("visual_description", ""),
            "narrative_description": scene.get("narrative_description", ""),
            "duration": scene.get("duration", 0.0),
            "image_url": image_url,
            "motion_beats": list(
                (script_entry or {}).get("motion_beats")
                or concept_entry.get("motion_beats")
                or scene.get("motion_beats", [])
            ),
            "characters_present": list(
                (script_entry or {}).get("characters_present")
                or concept_entry.get("characters_present")
                or []
            ),
            "character_descriptions": list(
                (script_entry or {}).get("character_descriptions")
                or concept_entry.get("character_descriptions")
                or []
            ),
            "script_text": (script_entry or {}).get("script_text", ""),
            "voice_over_text": (script_entry or {}).get("voice_over_text", ""),
        }
        if depends_on_scene is not None:
            payload["depends_on_scene"] = depends_on_scene

        scenes_to_generate.append(payload)

    scene_numbers: List[int] = []
    for scene in scenes_to_generate:
        if not isinstance(scene, dict):
            continue
        sn = _coerce_int(scene.get("scene_number"))
        if sn is not None:
            scene_numbers.append(sn)

    scene_dependency_graph: List[Dict[str, Any]] = []
    for scene in scenes_source or []:
        if not isinstance(scene, dict):
            continue
        sn = _coerce_int(scene.get("scene_number"))
        if sn is None or (scene_numbers and sn not in scene_numbers):
            continue
        depends_on = (
            scene.get("depends_on_scene")
            or scene.get("depends_on")
        )
        depends_on = _coerce_int(depends_on)
        if depends_on is not None:
            scene_dependency_graph.append(
                {
                    "scene_number": sn,
                    "depends_on_scene": depends_on,
                }
            )

    task_overview = {
        "story_overview": concept_plan.get("overview") or concept_plan.get("story_overview") or "",
        "style": concept_plan.get("intelligent_style_design") or {},
        "roles": concept_plan.get("roles") or [],
        "total_scenes": len((overview.get("scenes") or []) if isinstance(overview, dict) else scenes_source or []),
        "scene_numbers": scene_numbers,
    }

    scene_info_payload = {
        "task_type": "batch_video_generation",
        "workflow_state_id": workflow_id,
        "total_scenes": len(scenes_source or []),
        "scenes_to_generate": scenes_to_generate,
        "concept_plan": concept_plan,
        "intelligent_style": concept_plan.get("intelligent_style_design") or {},
        "scene_overview": overview,
    }

    context = {
        "task_overview": task_overview,
        "scene_dependency_graph": scene_dependency_graph,
        "key_illustration": {
            "task_overview": "全局故事与风格/角色概览，仅用于规划",
            "scene_dependency_graph": "场景依赖关系，表示生成顺序",
        },
    }

    return {
        "context": context,
        "scene_info_payload": scene_info_payload,
    }


def build_voice_synthesis_context(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[str, Any]:
    """Aggregates concept/scene/script facts for VoiceSynthesizer."""
    concept_plan = load_concept_plan(workflow_id, service=service)
    overview = load_scene_overview(workflow_id, service=service)
    scripts = load_scene_scripts(workflow_id, service=service)
    roles_ctx = load_roles_context(workflow_id, service=service)

    wm = get_mas_working_memory(workflow_id, service=service)
    voice_bucket = wm.get("scene_outputs.voice", {}) if wm is not None else {}
    voice_plan = wm.get("project.voice_plan", {}) if wm is not None else {}

    def build_guidance_map(plan: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
        mapping: Dict[int, Dict[str, Any]] = {}
        entries = plan.get("scene_guidance") if isinstance(plan, dict) else None
        if not isinstance(entries, list):
            return mapping
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            scene_key = entry.get("scene_number") or entry.get("sceneIndex")
            try:
                scene_number = int(scene_key)
            except (TypeError, ValueError):
                continue
            should_raw = entry.get("should_narrate")
            if isinstance(should_raw, str):
                should_val = should_raw.strip().lower() not in {"false", "0", "no", "off"}
            else:
                should_val = should_raw
            raw_points = entry.get("key_points") or entry.get("topics") or entry.get("highlights") or []
            if isinstance(raw_points, str):
                key_points = [
                    seg.strip()
                    for seg in raw_points.replace("、", ",").split(",")
                    if seg.strip()
                ]
            elif isinstance(raw_points, list):
                key_points = [str(seg).strip() for seg in raw_points if str(seg).strip()]
            else:
                key_points = []
            mapping[scene_number] = {
                "scene_number": scene_number,
                "should_narrate": should_val,
                "objective": entry.get("objective") or entry.get("purpose") or "",
                "emotion": entry.get("emotion") or entry.get("tone") or "",
                "key_points": key_points,
                "pace_tag": str(entry.get("pace_tag", "")).strip().lower(),
                "target_char_count": entry.get("target_char_count"),
            }
        return mapping

    guidance_map = build_guidance_map(voice_plan) if isinstance(voice_plan, dict) else {}
    enabled = bool(voice_plan.get("enabled", True)) if isinstance(voice_plan, dict) else True
    mode = str(voice_plan.get("mode", "") or "").strip().lower() if isinstance(voice_plan, dict) else ""
    default_enabled = enabled and mode not in {"none", "off"}

    concept_scene_index: Dict[int, Dict[str, Any]] = {}
    for scene in (concept_plan.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        try:
            sn = int(scene.get("scene_number"))
        except Exception:
            continue
        concept_scene_index[sn] = scene

    scenes_source = overview.get("scenes") if isinstance(overview, dict) else None
    if not scenes_source:
        scenes_source = concept_plan.get("scenes") or []

    scenes_to_synthesize: List[Dict[str, Any]] = []
    scenes_completed: List[Dict[str, Any]] = []
    scenes_blocked: List[Dict[str, Any]] = []
    scenes_skipped: List[Dict[str, Any]] = []

    for scene in scenes_source or []:
        if not isinstance(scene, dict):
            continue
        sn = _coerce_int(scene.get("scene_number"))
        if sn is None:
            continue
        script_entry = scripts.get(sn) if isinstance(scripts, dict) else {}
        concept_entry = concept_scene_index.get(sn, {})
        guidance = dict(guidance_map.get(sn, {}) or {})
        pacing = scene.get("pacing_and_timing") or {}
        if isinstance(pacing, dict):
            if pacing.get("should_narrate") is not None:
                guidance["should_narrate"] = bool(pacing.get("should_narrate"))
            if pacing.get("pace_tag"):
                guidance["pace_tag"] = str(pacing.get("pace_tag")).strip().lower()
            if pacing.get("target_char_count") is not None:
                try:
                    guidance["target_char_count"] = int(pacing.get("target_char_count"))
                except (TypeError, ValueError):
                    guidance["target_char_count"] = pacing.get("target_char_count")
        scene_guidance = scene.get("voice_guidance")
        if isinstance(scene_guidance, dict):
            for key, value in scene_guidance.items():
                if value is not None:
                    guidance[key] = value

        should_narrate = guidance.get("should_narrate")
        if should_narrate is None:
            should_narrate = default_enabled

        voice_text = (
            (script_entry or {}).get("voice_over_text")
            or scene.get("voice_over_text")
            or (script_entry or {}).get("script_text")
            or scene.get("script_text")
            or ""
        )

        voice_rec = {}
        if isinstance(voice_bucket, dict):
            voice_rec = voice_bucket.get(sn) or voice_bucket.get(str(sn)) or {}
        if not isinstance(voice_rec, dict):
            voice_rec = {}
        has_asset = bool(
            voice_rec
            and (voice_rec.get("audio_path") or voice_rec.get("audio_url") or voice_rec.get("url"))
        )

        payload = {
            "scene_number": sn,
            "title": concept_entry.get("title", ""),
            "visual_description": scene.get("visual_description", ""),
            "narrative_description": scene.get("narrative_description", ""),
            "duration": scene.get("duration", 0.0),
            "voice_over_text": voice_text,
            "script_text": (script_entry or {}).get("script_text", "") or scene.get("script_text", ""),
            "voice_guidance": guidance,
            "should_narrate": bool(should_narrate),
            "has_voice_asset": has_asset,
            "existing_asset": voice_rec if has_asset else {},
        }

        if not should_narrate:
            scenes_skipped.append({"scene_number": sn, "reason": "should_not_narrate"})
            continue
        if has_asset:
            scenes_completed.append(
                {
                    "scene_number": sn,
                    "audio_url": voice_rec.get("audio_url") or voice_rec.get("url") or "",
                    "audio_path": voice_rec.get("audio_path") or voice_rec.get("path") or "",
                }
            )
            continue
        if not voice_text:
            scenes_blocked.append({"scene_number": sn, "reason": "missing_voice_text"})
            continue

        scenes_to_synthesize.append(payload)

    return {
        "context": {
            "task_type": "voice_synthesis",
            "workflow_state_id": workflow_id,
            "total_scenes": len(scenes_source or []),
            "scenes_to_synthesize": scenes_to_synthesize,
            "scenes_completed": scenes_completed,
            "scenes_blocked": scenes_blocked,
            "scenes_skipped": scenes_skipped,
            "voice_plan": voice_plan,
            "roles_context": roles_ctx,
            "scene_overview": overview,
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


__all__ = [
    "load_scene_overview",
    "load_scene_scripts",
    "load_roles_context",
    "load_concept_plan",
    "build_media_agent_context",
    "build_image_generation_context",
    "build_video_generation_context",
    "build_voice_synthesis_context",
    "extract_failed_scenes",
]
