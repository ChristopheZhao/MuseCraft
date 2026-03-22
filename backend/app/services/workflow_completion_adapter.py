"""
Completion projection and event payload assembly outside orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..agents.adapters.state.mas_state import build_mas_state_view
from ..agents.utils.memory_helpers import get_mas_working_memory
from ..events.models import EventKind
from ..events.publisher import publish_event
from ..models import Task
from .memory_provider import MemoryServices, build_memory_services


class WorkflowCompletionAdapter:
    """Owns completion projection and runtime completion/failure event payloads."""

    def __init__(
        self,
        memory_services: Optional[MemoryServices] = None,
        *,
        owner_agent_name: str = "workflow_completion",
    ):
        self._memory_services = memory_services or build_memory_services()
        self._owner_agent_name = str(owner_agent_name or "workflow_completion")

    def build_persistence_payload(self, workflow_id: str) -> Dict[str, Any]:
        scenes: List[Dict[str, Any]] = []
        resources: List[Dict[str, Any]] = []

        wf_id = str(workflow_id or "")
        shared = None
        try:
            shared = get_mas_working_memory(wf_id, service=self._memory_services.short_term)
        except Exception:
            shared = None

        overview = shared.get("scene_overview", {}) if shared is not None else {}
        raw_scenes = overview.get("scenes") if isinstance(overview, dict) else []
        if isinstance(raw_scenes, list):
            for scene in raw_scenes:
                if not isinstance(scene, dict):
                    continue
                scenes.append(
                    {
                        "scene_number": scene.get("scene_number"),
                        "title": scene.get("title") or scene.get("scene_title"),
                        "description": scene.get("description")
                        or scene.get("narrative_description")
                        or scene.get("visual_description"),
                        "duration": scene.get("duration"),
                    }
                )

        def _iter_bucket(key: str) -> List[Dict[str, Any]]:
            if shared is None:
                return []
            try:
                bucket = shared.get(key, {})
            except Exception:
                bucket = {}
            if not isinstance(bucket, dict):
                return []
            out: List[Dict[str, Any]] = []
            for bucket_key, value in bucket.items():
                if not isinstance(value, dict):
                    continue
                record = dict(value)
                scene_number = record.get("scene_number")
                if scene_number is None:
                    try:
                        scene_number = int(bucket_key)
                    except Exception:
                        scene_number = bucket_key
                    record["scene_number"] = scene_number
                out.append(record)
            return out

        for record in _iter_bucket("scene_outputs.video"):
            url = record.get("video_url") or record.get("url")
            path = record.get("video_path") or record.get("path") or record.get("file_path")
            if url or path:
                scene_number = record.get("scene_number")
                resources.append(
                    {
                        "scene_number": scene_number,
                        "type": "video",
                        "resource_type": "video",
                        "url": url,
                        "path": path,
                        "filename": f"scene_{scene_number}_video.mp4",
                    }
                )

        for record in _iter_bucket("scene_outputs.image"):
            url = record.get("image_url") or record.get("url")
            path = record.get("image_path") or record.get("path") or record.get("file_path")
            if url or path:
                scene_number = record.get("scene_number")
                resources.append(
                    {
                        "scene_number": scene_number,
                        "type": "image",
                        "resource_type": "image",
                        "url": url,
                        "path": path,
                        "filename": f"scene_{scene_number}_image.jpg",
                    }
                )

        for record in _iter_bucket("scene_outputs.voice"):
            url = record.get("audio_url") or record.get("url")
            path = record.get("audio_path") or record.get("path") or record.get("file_path")
            if url or path:
                scene_number = record.get("scene_number")
                resources.append(
                    {
                        "scene_number": scene_number,
                        "type": "audio",
                        "resource_type": "audio",
                        "url": url,
                        "path": path,
                        "filename": f"scene_{scene_number}_audio.mp3",
                    }
                )

        final_video = shared.get("project.final_video", {}) if shared is not None else {}
        if isinstance(final_video, dict):
            final_url = final_video.get("url") or ""
            final_path = final_video.get("path") or ""
            if final_url or final_path:
                resources.append(
                    {
                        "scope": "task",
                        "kind": "final_video",
                        "resource_type": "video",
                        "url": final_url,
                        "path": final_path,
                        "filename": "final_video.mp4",
                    }
                )

        bgm = shared.get("project.background_music", {}) if shared is not None else {}
        if isinstance(bgm, dict):
            bgm_url = bgm.get("audio_url") or ""
            bgm_path = bgm.get("audio_path") or ""
            if bgm_url or bgm_path:
                resources.append(
                    {
                        "scope": "task",
                        "kind": "background_music",
                        "resource_type": "audio",
                        "url": bgm_url,
                        "path": bgm_path,
                        "filename": "background_music",
                    }
                )

        return {"scenes": scenes, "resources": resources}

    def resolve_final_video_url(self, workflow_id: str) -> str:
        try:
            shared = get_mas_working_memory(str(workflow_id), service=self._memory_services.short_term)
        except Exception:
            shared = None
        final_video = shared.get("project.final_video", {}) if shared is not None else {}
        if not isinstance(final_video, dict):
            return ""
        return str(final_video.get("url") or final_video.get("path") or "").strip()

    async def publish_completed(
        self,
        *,
        task: Task,
        workflow_id: str,
        results: Optional[Dict[str, Any]] = None,
        quality_score: Optional[Any] = None,
    ) -> Dict[str, Any]:
        persistence_payload = self.build_persistence_payload(workflow_id)
        try:
            mas_state = build_mas_state_view(str(workflow_id), service=self._memory_services.short_term)
        except Exception:
            mas_state = {}

        final_video_url = self.resolve_final_video_url(workflow_id)
        payload: Dict[str, Any] = {
            "state": "workflow_completed",
            "status": "COMPLETED",
            "final_video_url": final_video_url,
            "mas_state": mas_state,
            "scenes": persistence_payload.get("scenes") or [],
            "resources": persistence_payload.get("resources") or [],
        }
        if isinstance(results, dict) and results:
            payload["results"] = results
        if quality_score is not None:
            payload["quality_score"] = quality_score

        await publish_event(
            kind=EventKind.STATE,
            payload=payload,
            task_id=str(task.task_id),
            task_db_id=task.id,
            workflow_state_id=str(workflow_id),
            agent_name=self._owner_agent_name,
        )
        return {
            "final_video_url": final_video_url,
            "scenes": payload["scenes"],
            "resources": payload["resources"],
        }

    async def publish_failed(
        self,
        *,
        task: Task,
        workflow_id: str,
        error_message: str,
    ) -> None:
        await publish_event(
            kind=EventKind.STATE,
            payload={
                "state": "workflow_failed",
                "status": "FAILED",
                "error": str(error_message or ""),
            },
            task_id=str(task.task_id),
            task_db_id=task.id,
            workflow_state_id=str(workflow_id),
            agent_name=self._owner_agent_name,
        )
