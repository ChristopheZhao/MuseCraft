from __future__ import annotations

"""
Shared WM Snapshot Exporter（长期记忆视图）

从 Shared Working Memory 导出适合持久化/审计的轻量快照：
- 只保留必要字段与引用，避免大对象进入快照
- 为数据持久化与日志分析提供统一入口
"""

from typing import Any, Dict, List, Optional

from ...services.mas_shared_memory import get_shared_wm
from ..short_term.workflow_facts import WorkflowFactStoreError
from ....services.memory_provider import get_memory_services, MemoryServices


def _coerce_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _coerce_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def export_shared_wm_snapshot(task_id: str, memory_services: Optional[MemoryServices] = None) -> Dict[str, Any]:
    """导出指定任务在 Shared WM 中的整体快照。"""
    services = memory_services or get_memory_services()
    view = get_shared_wm().get_task(str(task_id))
    store = services.fact_store
    coordinator = services.coordinator
    try:
        concept_plan = store.get(str(task_id), "concept_plan", default={}) or {}
    except WorkflowFactStoreError:
        concept_plan = {}
    try:
        voice_plan = store.get(str(task_id), "voice_plan", default={}) or {}
    except WorkflowFactStoreError:
        voice_plan = {}
    style_design = concept_plan.get("intelligent_style_design") if isinstance(concept_plan, dict) else {}
    if not isinstance(style_design, dict):
        style_design = {}
    content_elements = concept_plan.get("content_elements") if isinstance(concept_plan, dict) else {}
    if not isinstance(content_elements, dict):
        content_elements = {}
    try:
        voice_assets = store.get(str(task_id), "voice_assets", default={}) or {}
    except WorkflowFactStoreError:
        voice_assets = {}

    scenes: List[Dict[str, Any]] = []

    plan_scenes = concept_plan.get("scenes") if isinstance(concept_plan, dict) else None
    if isinstance(plan_scenes, list) and plan_scenes:
        for s in plan_scenes:
            if not isinstance(s, dict):
                continue
            sn = _coerce_int(s.get("scene_number"), 0)
            if sn <= 0:
                continue
            dur = _coerce_float(s.get("final_duration", s.get("duration")), 0.0)
            entry = {
                "scene_number": sn,
                "title": s.get("title", ""),
                "duration": dur,
                "start_time": _coerce_float(s.get("start_time", 0.0), 0.0),
                "end_time": _coerce_float(s.get("end_time", 0.0), 0.0),
                "narrative_description": s.get("narrative_description", ""),
                "visual_description": s.get("visual_description", ""),
                "mood_and_atmosphere": s.get("mood_and_atmosphere", ""),
                "video_prompt": s.get("video_prompt", ""),
                "video_generation_params": s.get("video_generation_params", {}),
                "script_text": s.get("script_text", ""),
                # artifacts will be merged below
                "video_url": "",
                "video_path": "",
                "image_url": s.get("image_url", ""),
                "image_path": s.get("image_path", ""),
            }
            scenes.append(entry)
    else:
        # fallback to shared WM scene snapshots (minimal)
        for sn, snap in (view.scenes or {}).items():
            if not snap:
                continue
            scenes.append(
                {
                    "scene_number": _coerce_int(sn, 0),
                    "title": "",
                    "duration": _coerce_float(getattr(snap, "duration", 0.0), 0.0),
                    "start_time": 0.0,
                    "end_time": 0.0,
                    "narrative_description": getattr(snap, "narrative_description", ""),
                    "visual_description": getattr(snap, "visual_description", ""),
                    "mood_and_atmosphere": "",
                    "video_prompt": "",
                    "video_generation_params": {},
                    "script_text": "",
                    "video_url": "",
                    "video_path": "",
                    "image_url": getattr(snap, "image_url", ""),
                    "image_path": "",
                }
            )

    # Merge video artifacts (if any)
    # 优先使用 artifacts 中的 video_only（按 scene 取最新），否则 fallback 到 view.completed
    try:
        arts_vo = get_shared_wm().list_artifacts(str(task_id), kind="video", stage="video_only")
        latest_by_scene: Dict[int, Dict[str, Any]] = {}
        for r in arts_vo or []:
            if not isinstance(r, dict):
                continue
            sn = r.get("scene_number")
            if sn is None:
                continue
            try:
                sn_int = int(sn)
            except Exception:
                continue
            latest_by_scene[sn_int] = r
        for entry in scenes:
            sn = _coerce_int(entry.get("scene_number"), 0)
            if sn <= 0:
                continue
            art = latest_by_scene.get(sn)
            if not isinstance(art, dict):
                continue
            entry["video_url"] = art.get("url") or ""
            entry["video_path"] = art.get("file_path") or ""
    except Exception:
        # fallback: nothing to merge
        pass

    # voice assets merge: attach simple flags/urls per scene if needed
    if isinstance(voice_assets, dict) and voice_assets:
        by_scene: Dict[int, Dict[str, Any]] = {}
        for sid, val in voice_assets.items():
            try:
                sn = int(sid)
            except Exception:
                continue
            if not isinstance(val, dict):
                continue
            by_scene[sn] = val
        for entry in scenes:
            sn = _coerce_int(entry.get("scene_number"), 0)
            if sn <= 0:
                continue
            v = by_scene.get(sn)
            if not isinstance(v, dict):
                continue
            # 仅附加最小必要字段，避免大对象
            entry.setdefault("voice_assets", {})
            entry["voice_assets"].update(
                {
                    "has_voice": bool(v.get("url") or v.get("path")),
                    "url": v.get("url") or "",
                    "path": v.get("path") or "",
                }
            )

    # 按 scene_number 排序
    try:
        scenes.sort(key=lambda x: x.get("scene_number", 0))
    except Exception:
        pass

    try:
        final_video = store.get(str(task_id), "final_video", default={}) or {}
        if isinstance(final_video, dict):
            final_video = {
                "path": final_video.get("path") or "",
                "url": final_video.get("url") or "",
                "remote_path": final_video.get("remote_path") or "",
                "storage": final_video.get("storage") or {},
                "mix": final_video.get("mix") or "",
            }
        else:
            final_video = {}
    except WorkflowFactStoreError:
        final_video = {}

    # Export artifacts timeline (lightweight fields only)
    try:
        artifacts = get_shared_wm().list_artifacts(str(task_id))
        # keep only essential keys to avoid large blobs
        sanitized: List[Dict[str, Any]] = []
        for r in artifacts or []:
            if not isinstance(r, dict):
                continue
            sanitized.append(
                {
                    "id": r.get("id"),
                    "created_at": r.get("created_at"),
                    "kind": r.get("kind"),
                    "stage": r.get("stage"),
                    "scene_number": r.get("scene_number"),
                    "file_path": r.get("file_path") or "",
                    "url": r.get("url") or "",
                    "duration_sec": r.get("duration_sec"),
                    "prompt_text": r.get("prompt_text") or "",
                    "agent": r.get("agent") or "",
                    "tool": r.get("tool") or "",
                    "metadata": r.get("metadata") or {},
                }
            )
    except Exception:
        sanitized = []

    return {
        "task_id": str(task_id),
        "facts": {
            "concept_plan": concept_plan,
            "voice_plan": voice_plan,
            "intelligent_style_design": style_design,
            "content_elements": content_elements,
        },
        "scenes": scenes,
        "failures": {int(k): v for k, v in (view.failed or {}).items() if k is not None},
        "final_video": final_video,
        "artifacts": sanitized,
    }


__all__ = ["export_shared_wm_snapshot"]
