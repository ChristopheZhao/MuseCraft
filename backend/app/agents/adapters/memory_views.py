from __future__ import annotations

"""Shared memory view helpers for orchestrator → agent context construction.

Active mainline paths should inject published stage payloads/views via
`ContextContractAssembler`. Builders may still read canonical facts from working memory,
but they must not self-resolve missing stage boundaries through legacy shared-WM bridges.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ...core.config import settings
from ...services.scene_contract import annotate_scene_info_payload
from ...services.video_composer_execution_contract import get_video_composer_compose_mode
from ..tools import image_prompt_normalization as image_prompt_norm
if TYPE_CHECKING:
    from ..memory.short_term.service import WorkingMemoryService


_MAS_SCOPE_PREFIX = "mas"


def _get_mas_working_memory(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
):
    return service.get(str(workflow_id), f"{_MAS_SCOPE_PREFIX}:{workflow_id}")


def _require_boundary_dict(
    payload: Optional[Dict[str, Any]],
    *,
    workflow_id: str,
    field_name: str,
    purpose: str,
) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    raise ValueError(
        f"{field_name} is required for {purpose}: workflow_id={workflow_id}"
    )


def _merge_image_bucket_into_overview(
    overview: Dict[str, Any],
    *,
    workflow_id: str,
    service: "WorkingMemoryService",
) -> Dict[str, Any]:
    if not isinstance(overview, dict) or not overview:
        return {}
    try:
        wm = _get_mas_working_memory(str(workflow_id), service=service)
    except Exception:
        wm = None
    if wm is None:
        return overview
    try:
        scenes = overview.get("scenes") if isinstance(overview, dict) else None
        image_bucket = wm.get("scene_outputs.image", {}) or {}
        if not (isinstance(scenes, list) and scenes and isinstance(image_bucket, dict) and image_bucket):
            return overview
        updated_scenes: List[Dict[str, Any]] = []
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            sn = _coerce_int(scene.get("scene_number"))
            if sn is not None and not (scene.get("image_url") or "").strip():
                rec = image_bucket.get(sn) or image_bucket.get(str(sn))
                if isinstance(rec, dict) and isinstance(rec.get("image_url"), str) and rec.get("image_url"):
                    scene_copy = dict(scene)
                    scene_copy["image_url"] = rec.get("image_url")
                    updated_scenes.append(scene_copy)
                    continue
            updated_scenes.append(scene)
        merged = dict(overview)
        merged["scenes"] = updated_scenes
        return merged
    except Exception:
        return overview


def load_scene_overview(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[str, Any]:
    """Return MAS working-memory projection for scenes/state."""
    wm = _get_mas_working_memory(str(workflow_id), service=service)
    if wm is None:
        return {}
    overview = wm.get("scene_overview", {})
    if isinstance(overview, dict) and overview:
        return _merge_image_bucket_into_overview(
            overview,
            workflow_id=workflow_id,
            service=service,
        )
    return {}


def load_scene_scripts(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[int, Dict[str, Any]]:
    """Fetch per-scene script facts from the workflow fact store."""
    try:
        wm = _get_mas_working_memory(workflow_id, service=service)
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
        wm = _get_mas_working_memory(workflow_id, service=service)
        plan = wm.get("project.concept_plan", {}) or {}
        if isinstance(plan, dict):
            return plan
    except Exception:
        pass
    return {}


def load_audio_requirements(workflow_id: str, *, service: "WorkingMemoryService") -> Dict[str, Any]:
    """Return audio requirement facts, if available."""
    try:
        wm = _get_mas_working_memory(workflow_id, service=service)
        payload = wm.get("project.audio_requirements", {}) if wm is not None else {}
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def build_script_stage_views(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
    published_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = _require_boundary_dict(
        published_payload,
        workflow_id=workflow_id,
        field_name="published_payload",
        purpose="building script stage views",
    )

    concept_plan = payload.get("concept_plan") or {}
    scene_overview = _merge_image_bucket_into_overview(
        payload.get("scene_overview") or {},
        workflow_id=workflow_id,
        service=service,
    )
    scene_scripts = _normalize_scene_dict(payload.get("scene_scripts") or {})
    return {
        "concept_plan": concept_plan if isinstance(concept_plan, dict) else {},
        "scene_overview": scene_overview if isinstance(scene_overview, dict) else {},
        "scene_scripts": scene_scripts if isinstance(scene_scripts, dict) else {},
    }


def build_media_agent_context(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
    include_scripts: bool = True,
    include_roles: bool = False,
    include_audio_requirements: bool = False,
    sfx_required_default: Optional[bool] = None,
    sfx_required_override: Optional[bool] = None,
    script_stage_views: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience helper for orchestrator when preparing agent inputs."""
    context: Dict[str, Any] = {}
    boundary_views = dict(
        _require_boundary_dict(
            script_stage_views,
            workflow_id=workflow_id,
            field_name="script_stage_views",
            purpose="downstream media context assembly",
        )
    )
    overview = boundary_views.get("scene_overview") or {}
    if overview:
        context["scene_overview"] = overview
    if include_scripts:
        scripts = boundary_views.get("scene_scripts") or {}
        if scripts:
            context["scene_scripts"] = scripts
    if include_roles:
        concept_plan = boundary_views.get("concept_plan") or {}
        roles = concept_plan.get("roles") if isinstance(concept_plan, dict) else []
        roles_ctx = {
            "concept_overview": (
                concept_plan.get("overview") or concept_plan.get("story_overview") or ""
            ) if isinstance(concept_plan, dict) else "",
            "style": (
                concept_plan.get("intelligent_style_design") or {}
            ) if isinstance(concept_plan, dict) else {},
            "roles": roles if isinstance(roles, list) else [],
        }
        if roles_ctx:
            context["roles_context"] = roles_ctx
    if include_audio_requirements:
        audio_requirements = load_audio_requirements(workflow_id, service=service)
        if not isinstance(audio_requirements, dict):
            audio_requirements = {}
        if sfx_required_override is not None:
            audio_requirements = dict(audio_requirements)
            audio_requirements["sfx_required"] = bool(sfx_required_override)
        elif "sfx_required" not in audio_requirements and sfx_required_default is not None:
            audio_requirements = dict(audio_requirements)
            audio_requirements["sfx_required"] = bool(sfx_required_default)
        if audio_requirements:
            context["audio_requirements"] = audio_requirements
    return context


def build_video_composer_context(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
    execution_contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregate composer facts for ReAct planning."""
    ctx: Dict[str, Any] = {}
    wm = None
    try:
        wm = _get_mas_working_memory(str(workflow_id), service=service)
    except Exception:
        wm = None

    final_video = wm.get("project.final_video", {}) if wm else {}
    bgm = wm.get("project.background_music", {}) if wm else {}
    voice_settings = wm.get("project.voice_settings", {}) if wm else {}
    if not voice_settings:
        voice_settings = wm.get("voice_settings", {}) if wm else {}
    voice_assets = wm.get("project.voice_assets", {}) if wm else {}
    if not voice_assets:
        voice_assets = wm.get("voice_assets", {}) if wm else {}
    vm_state = wm.get("project.voice_mixing_state", {}) if wm else {}

    scene_videos: List[Dict[str, Any]] = []
    scene_voiceovers: List[Dict[str, Any]] = []
    try:
        overview = wm.get("scene_overview", {}) if wm else {}
        duration_by_scene: Dict[int, float] = {}
        for s in (overview.get("scenes") if isinstance(overview, dict) else []) or []:
            if not isinstance(s, dict):
                continue
            try:
                sn = int(s.get("scene_number"))
            except Exception:
                continue
            try:
                duration_by_scene[sn] = float(s.get("duration") or 0.0)
            except Exception:
                duration_by_scene[sn] = 0.0

        video_bucket = wm.get("scene_outputs.video", {}) if wm else {}
        if isinstance(video_bucket, dict) and video_bucket:
            for k, rec in video_bucket.items():
                if not isinstance(rec, dict):
                    continue
                try:
                    sn = int(rec.get("scene_number") or k)
                except Exception:
                    continue
                local_path = rec.get("video_path") or rec.get("path") or rec.get("file_path") or ""
                video_url = rec.get("video_url") or rec.get("url") or ""
                if local_path:
                    # Prefer local artifacts when available to avoid redundant downloads.
                    video_url = ""
                scene_videos.append(
                    {
                        "scene_number": sn,
                        "local_path": local_path,
                        "video_url": video_url,
                        "duration": float(rec.get("duration_sec") or duration_by_scene.get(sn) or 0.0),
                    }
                )
        scene_videos.sort(key=lambda x: int(x.get("scene_number") or 0))

        voice_bucket = wm.get("scene_outputs.voice", {}) if wm else {}
        if isinstance(voice_bucket, dict) and voice_bucket:
            for k, rec in voice_bucket.items():
                if not isinstance(rec, dict):
                    continue
                try:
                    sn = int(rec.get("scene_number") or k)
                except Exception:
                    continue
                scene_voiceovers.append(
                    {
                        "scene_number": sn,
                        "local_path": rec.get("audio_path") or "",
                        "audio_url": rec.get("audio_url") or "",
                        "duration": float(rec.get("duration_sec") or 0.0),
                    }
                )
        scene_voiceovers.sort(key=lambda x: int(x.get("scene_number") or 0))
    except Exception:
        scene_videos = []
        scene_voiceovers = []

    compose_mode = get_video_composer_compose_mode(execution_contract)
    final_video_ctx = {
        "path": final_video.get("path", "") if isinstance(final_video, dict) else "",
        "url": final_video.get("url", "") if isinstance(final_video, dict) else "",
    }
    background_music_ctx = {
        "path": bgm.get("audio_path", "") if isinstance(bgm, dict) else "",
        "url": bgm.get("audio_url", "") if isinstance(bgm, dict) else "",
        "duration": (bgm.get("duration") or 0.0) if isinstance(bgm, dict) else 0.0,
        "style": bgm.get("style", "") if isinstance(bgm, dict) else "",
    }
    voice_assets_ctx = [
        {
            "scene_number": int(k) if str(k).isdigit() else k,
            "local_path": (v or {}).get("local_path") or (v or {}).get("audio_path") or "",
            "audio_url": (v or {}).get("audio_url", ""),
            "duration": (v or {}).get("duration", 0.0),
        }
        for k, v in (voice_assets.items() if isinstance(voice_assets, dict) else [])
    ]
    scene_media_ref, scene_media_has_voice = _build_video_composer_scene_media_ref(
        workflow_id=workflow_id,
        scene_videos=scene_videos,
        scene_voiceovers=scene_voiceovers,
        include_voice_tracks=compose_mode == "voiceover",
    )
    if compose_mode == "bgm":
        if not _has_video_artifact(final_video_ctx):
            raise ValueError(
                f"video_composer static context missing final_video for compose_mode=bgm: workflow_id={workflow_id}"
            )
        if not _has_audio_artifact(background_music_ctx):
            raise ValueError(
                f"video_composer static context missing background_music for compose_mode=bgm: workflow_id={workflow_id}"
            )
        ctx["final_video"] = final_video_ctx
        ctx["background_music"] = background_music_ctx
        ctx["ducking_config"] = vm_state.get("ducking_config", {}) if isinstance(vm_state, dict) else {}
        return ctx

    if not scene_videos:
        raise ValueError(
            "video_composer static context missing scene_videos for "
            f"compose_mode={compose_mode}: workflow_id={workflow_id}"
        )

    ctx["scene_videos"] = scene_videos
    if scene_media_ref:
        ctx["scene_media_ref"] = scene_media_ref
        key_illustration = dict(ctx.get("key_illustration") or {})
        key_illustration.setdefault(
            "scene_media_ref",
            "场景合成清单的引用地址（包含场景视频路径/时长，可能包含配音路径）",
        )
        ctx["key_illustration"] = key_illustration

    if compose_mode == "voiceover":
        if not scene_media_has_voice:
            raise ValueError(
                "video_composer static context missing complete scene voice tracks for "
                f"compose_mode=voiceover: workflow_id={workflow_id}"
            )
        ctx["scene_voiceovers"] = scene_voiceovers
        ctx["scene_media_has_voice"] = True
        ctx["voice_assets"] = voice_assets_ctx
        if (
            scene_media_ref
            and bool(getattr(settings, "COMPOSER_HIDE_SCENE_AUDIO_ON_REF", False))
        ):
            ctx["scene_voiceovers"] = []
            ctx["voice_assets"] = []
        ctx["voice_settings"] = voice_settings if isinstance(voice_settings, dict) else {}
        ctx["ducking_config"] = vm_state.get("ducking_config", {}) if isinstance(vm_state, dict) else {}
    return ctx


def _has_video_artifact(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(str(payload.get("path") or "").strip() or str(payload.get("url") or "").strip())


def _has_audio_artifact(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(str(payload.get("path") or "").strip() or str(payload.get("url") or "").strip())


def _build_video_composer_scene_media_ref(
    *,
    workflow_id: str,
    scene_videos: List[Dict[str, Any]],
    scene_voiceovers: List[Dict[str, Any]],
    include_voice_tracks: bool,
) -> tuple[Optional[str], bool]:
    if not scene_videos:
        return None, False

    scene_numbers = [int(item.get("scene_number") or 0) for item in scene_videos]
    voice_map = {
        int(item.get("scene_number") or 0): item
        for item in scene_voiceovers
        if isinstance(item, dict) and item.get("local_path")
    }
    scene_media_has_voice = bool(scene_numbers) and all(sn in voice_map for sn in scene_numbers)
    include_audio = include_voice_tracks and scene_media_has_voice
    scene_media: List[Dict[str, Any]] = []
    for item in scene_videos:
        if not isinstance(item, dict):
            continue
        try:
            sn = int(item.get("scene_number") or 0)
        except Exception:
            continue
        video_path = (item.get("local_path") or "").strip()
        if not video_path:
            continue
        entry: Dict[str, Any] = {
            "scene_number": sn,
            "video_file": video_path,
            "duration": float(item.get("duration") or 0.0),
        }
        if include_audio:
            entry["audio_file"] = voice_map[sn].get("local_path") or ""
        scene_media.append(entry)
    if not scene_media:
        return None, include_audio
    try:
        base_dir = Path(settings.TEMP_PATH) / "context"
        base_dir.mkdir(parents=True, exist_ok=True)
        filename = f"video_composer_scene_media_{workflow_id}.json"
        ref_path = (base_dir / filename).resolve()
        with open(ref_path, "w", encoding="utf-8") as fh:
            json.dump({"scenes": scene_media}, fh, ensure_ascii=False)
        try:
            backend_root = Path(__file__).resolve().parents[3]
            scene_media_ref = str(ref_path.relative_to(backend_root))
        except Exception:
            scene_media_ref = str(ref_path)
        return scene_media_ref, include_audio
    except Exception:
        return None, include_audio


def build_image_generation_context(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
    published_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregates concept/scene/script facts for ImageGenerator."""
    published_payload = _require_boundary_dict(
        published_payload,
        workflow_id=workflow_id,
        field_name="published_payload",
        purpose="image generation context assembly",
    )
    concept_plan = published_payload.get("concept_plan") or {}
    overview = published_payload.get("scene_overview") or {}
    scripts = _normalize_scene_dict(published_payload.get("scene_scripts") or {})

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
        mode = target_map.get(sn) or "generate"
        payload = {
            "scene_number": sn,
            "title": concept_entry.get("title", ""),
            "scene_thesis": (script_entry or {}).get("scene_thesis", "") or scene.get("scene_thesis", "") or concept_entry.get("scene_thesis", "") or "",
            "visual_description": scene.get("visual_description", ""),
            "narrative_description": scene.get("narrative_description", ""),
            "duration": scene.get("duration", 0.0),
            "mood_and_atmosphere": scene.get("mood_and_atmosphere") or concept_entry.get("mood_and_atmosphere") or "",
            "camera_angle": scene.get("camera_angle") or concept_entry.get("camera_angle") or "",
            "creative_intent": scene.get("creative_intent") or concept_entry.get("creative_intent") or "",
            "motion_beats": list(
                (script_entry or {}).get("motion_beats")
                or concept_entry.get("motion_beats")
                or scene.get("motion_beats", [])
            ),
            "opening_state": (script_entry or {}).get("opening_state", "") or scene.get("opening_state", "") or "",
            "event_trigger": (script_entry or {}).get("event_trigger", "") or scene.get("event_trigger", "") or "",
            "action_phases": list(
                (script_entry or {}).get("action_phases")
                or scene.get("action_phases", [])
            ),
            "end_state": (script_entry or {}).get("end_state", "") or scene.get("end_state", "") or "",
            "camera_language": (script_entry or {}).get("camera_language", "") or scene.get("camera_language", "") or "",
            "characters_present": list((script_entry or {}).get("characters_present") or concept_entry.get("characters_present") or []),
            "character_descriptions": list((script_entry or {}).get("character_descriptions") or concept_entry.get("character_descriptions") or []),
            "script_text": (script_entry or {}).get("script_text", ""),
            "voice_over_text": (script_entry or {}).get("voice_over_text", ""),
            "background_music_style": (script_entry or {}).get("background_music_style", ""),
        }
        payload["image_purpose"] = image_prompt_norm.infer_image_purpose(payload)
        payload["frame_thesis"] = image_prompt_norm.select_frame_thesis(
            payload,
            image_purpose=payload["image_purpose"],
            fallback_title=(payload.get("title") or "单帧静态画面").strip(),
        )
        if mode in {"skip", "reuse"}:
            scenes_to_skip.append({"scene_number": sn, "reason": mode, "reuse_from": None})
        else:
            scenes_to_generate.append(payload)

    context = {
        "task_type": "batch_image_generation",
        "workflow_state_id": workflow_id,
        "total_scenes": len(overview.get("scenes", [])) if isinstance(overview, dict) else 0,
        "scenes_to_generate": scenes_to_generate,
        "scenes_to_skip": scenes_to_skip,
        "concept_plan": concept_plan,
        "intelligent_style": concept_plan.get("intelligent_style_design") or {},
    }

    scene_info_payload = annotate_scene_info_payload({
        "task_type": "batch_image_generation",
        "workflow_state_id": workflow_id,
        "total_scenes": len(overview.get("scenes", [])) if isinstance(overview, dict) else 0,
        "scenes_to_generate": scenes_to_generate,
        "scenes_to_skip": scenes_to_skip,
        "concept_plan": concept_plan,
        "intelligent_style": concept_plan.get("intelligent_style_design") or {},
        "scene_overview": overview,
    }, mode="image_generation")

    return {
        "context": context,
        "scene_info_payload": scene_info_payload,
    }


def build_video_generation_context(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
    published_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregates concept/scene/script facts for VideoGenerator."""
    published_payload = _require_boundary_dict(
        published_payload,
        workflow_id=workflow_id,
        field_name="published_payload",
        purpose="video generation context assembly",
    )
    concept_plan = published_payload.get("concept_plan") or {}
    overview = _merge_image_bucket_into_overview(
        published_payload.get("scene_overview") or {},
        workflow_id=workflow_id,
        service=service,
    )
    scripts = _normalize_scene_dict(published_payload.get("scene_scripts") or {})

    try:
        wm = _get_mas_working_memory(workflow_id, service=service)
    except Exception:
        wm = None
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
            "scene_thesis": (script_entry or {}).get("scene_thesis", "") or scene.get("scene_thesis", "") or concept_entry.get("scene_thesis", "") or "",
            "visual_description": scene.get("visual_description", ""),
            "narrative_description": scene.get("narrative_description", ""),
            "duration": scene.get("duration", 0.0),
            "mood_and_atmosphere": scene.get("mood_and_atmosphere") or concept_entry.get("mood_and_atmosphere") or "",
            "camera_angle": scene.get("camera_angle") or concept_entry.get("camera_angle") or "",
            "creative_intent": scene.get("creative_intent") or concept_entry.get("creative_intent") or "",
            "image_url": image_url,
            "motion_beats": list(
                (script_entry or {}).get("motion_beats")
                or concept_entry.get("motion_beats")
                or scene.get("motion_beats", [])
            ),
            "opening_state": (script_entry or {}).get("opening_state", "") or scene.get("opening_state", "") or "",
            "event_trigger": (script_entry or {}).get("event_trigger", "") or scene.get("event_trigger", "") or "",
            "action_phases": list(
                (script_entry or {}).get("action_phases")
                or scene.get("action_phases", [])
            ),
            "end_state": (script_entry or {}).get("end_state", "") or scene.get("end_state", "") or "",
            "camera_language": (script_entry or {}).get("camera_language", "") or scene.get("camera_language", "") or "",
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
        payload["image_purpose"] = image_prompt_norm.infer_image_purpose(payload)
        payload["frame_thesis"] = image_prompt_norm.select_frame_thesis(
            payload,
            image_purpose=payload["image_purpose"],
            fallback_title=(payload.get("title") or "单帧静态画面").strip(),
        )
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

    scene_image_refs: List[Dict[str, Any]] = []
    for scene in scenes_source or []:
        if not isinstance(scene, dict):
            continue
        sn = _coerce_int(scene.get("scene_number"))
        if sn is None:
            continue
        concept_entry = concept_scene_index.get(sn, {})
        image_url = scene.get("image_url") or concept_entry.get("image_url") or ""
        if isinstance(image_url, str) and image_url:
            scene_image_refs.append({"scene_number": sn, "image_url": image_url})
    scene_image_refs.sort(key=lambda item: item.get("scene_number") or 0)

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
        "scene_image_refs": scene_image_refs,
    }

    scene_info_payload = annotate_scene_info_payload({
        "task_type": "batch_video_generation",
        "workflow_state_id": workflow_id,
        "total_scenes": len(scenes_source or []),
        "scenes_to_generate": scenes_to_generate,
        "concept_plan": concept_plan,
        "intelligent_style": concept_plan.get("intelligent_style_design") or {},
        "scene_overview": overview,
    }, mode="video_generation")

    context = {
        "task_overview": task_overview,
        "scene_dependency_graph": scene_dependency_graph,
        "key_illustration": {
            "task_overview": "全局故事与风格/角色概览，仅用于规划",
            "scene_dependency_graph": "场景依赖关系，表示生成顺序",
            "scene_image_refs": "场景起始视觉参考索引（含 image_url）",
        },
    }

    return {
        "context": context,
        "scene_info_payload": scene_info_payload,
    }


def build_voice_synthesis_context(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
    script_stage_views: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregates concept/scene/script facts for VoiceSynthesizer."""
    boundary_views = dict(
        _require_boundary_dict(
            script_stage_views,
            workflow_id=workflow_id,
            field_name="script_stage_views",
            purpose="voice synthesis context assembly",
        )
    )
    concept_plan = boundary_views.get("concept_plan") or {}
    overview = boundary_views.get("scene_overview") or {}
    scripts = boundary_views.get("scene_scripts") or {}
    roles = concept_plan.get("roles") if isinstance(concept_plan, dict) else []
    roles_ctx = {
        "concept_overview": (
            concept_plan.get("overview") or concept_plan.get("story_overview") or ""
        ) if isinstance(concept_plan, dict) else "",
        "style": (
            concept_plan.get("intelligent_style_design") or {}
        ) if isinstance(concept_plan, dict) else {},
        "roles": roles if isinstance(roles, list) else [],
    }

    wm = _get_mas_working_memory(workflow_id, service=service)
    voice_bucket = wm.get("scene_outputs.voice", {}) if wm is not None else {}
    video_bucket = wm.get("scene_outputs.video", {}) if wm is not None else {}
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

    video_duration_map: Dict[int, float] = {}
    if isinstance(video_bucket, dict):
        for key, rec in video_bucket.items():
            if not isinstance(rec, dict):
                continue
            try:
                sn = int(rec.get("scene_number") or key)
            except Exception:
                continue
            try:
                duration_val = float(rec.get("duration_sec") or rec.get("duration") or 0.0)
            except Exception:
                duration_val = 0.0
            if duration_val > 0:
                video_duration_map[sn] = duration_val

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

        scene_duration = video_duration_map.get(sn) or scene.get("duration", 0.0)
        payload = {
            "scene_number": sn,
            "title": concept_entry.get("title", ""),
            "visual_description": scene.get("visual_description", ""),
            "narrative_description": scene.get("narrative_description", ""),
            "duration": scene_duration,
            "voice_over_text": voice_text,
            "script_text": (script_entry or {}).get("script_text", "") or scene.get("script_text", ""),
            "voice_guidance": guidance,
            "should_narrate": bool(should_narrate),
            "has_voice_asset": has_asset,
            "existing_asset": voice_rec if has_asset else {},
        }
        if sn in video_duration_map:
            payload["video_duration_sec"] = video_duration_map.get(sn)

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
    "build_script_stage_views",
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
