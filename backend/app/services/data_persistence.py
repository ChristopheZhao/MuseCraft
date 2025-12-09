"""事件驱动的数据持久化（最小投影）。"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import Resource, ResourceType, Scene, SceneType, Task, TaskStatus, TaskType


class DataPersistenceService:
    """仅基于事件/终态摘要落库，不再读取 MAS WM 或全局单例。"""

    def __init__(self) -> None:
        import logging

        self.logger = logging.getLogger(self.__class__.__name__.lower())

    def persist_from_event_payload(self, payload: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """使用事件载荷（或终态摘要）写入任务/场景/资源最小投影。"""
        task_id = str(payload.get("task_id") or payload.get("external_task_id") or "")
        scenes = payload.get("scenes") or []
        resources = payload.get("resources") or []
        facts = payload.get("facts") or {}
        status = payload.get("status") or "PERSISTING"
        progress = payload.get("progress") or 90
        current_step = payload.get("current_step") or "Persisting data"

        try:
            task = self._persist_task_from_payload(task_id, facts, status, progress, current_step, db)
            scene_results = self._persist_scenes_from_payload(task, scenes, db)
            resource_results = self._persist_resources_from_payload(task, resources, scenes, db)
            db.commit()
            return {
                "task_id": task.id,
                "external_task_id": task_id,
                "status": "success",
                "scenes_persisted": len(scene_results),
                "resources_persisted": len(resource_results),
                "persistence_time": datetime.now().isoformat(),
            }
        except Exception as exc:  # pragma: no cover - defensive
            db.rollback()
            self.logger.error("Persist from event payload failed: %s", exc)
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(exc),
                "persistence_time": datetime.now().isoformat(),
            }

    def _persist_task_from_payload(
        self,
        ext_id: str,
        facts: Dict[str, Any],
        status: str,
        progress: Any,
        current_step: str,
        db: Session,
    ) -> Task:
        ext_id = str(ext_id or "")
        concept_plan = facts.get("concept_plan", {}) if isinstance(facts, dict) else {}
        voice_plan = facts.get("voice_plan", {}) if isinstance(facts, dict) else {}
        intelligent_style_design = {}
        content_elements = {}
        if isinstance(concept_plan, dict):
            intelligent_style_design = concept_plan.get("intelligent_style_design", {}) or {}
            content_elements = concept_plan.get("content_elements", {}) or {}

        task = db.query(Task).filter(Task.task_id == ext_id).first()
        if not task:
            try:
                task_status = TaskStatus(status) if isinstance(status, TaskStatus) else TaskStatus[status]  # type: ignore[index]
            except Exception:
                task_status = TaskStatus.PERSISTING
            task = Task(
                task_id=ext_id,
                title="Short Video Task",
                description="",
                task_type=TaskType.VIDEO_GENERATION if hasattr(TaskType, "VIDEO_GENERATION") else None,
                status=task_status if isinstance(task_status, TaskStatus) else TaskStatus.PERSISTING,
                progress_percentage=int(progress) if progress is not None else 90,
                current_step=current_step,
                input_parameters={
                    "intelligent_style_design": intelligent_style_design,
                    "voice_plan": voice_plan,
                    "content_elements": content_elements,
                },
            )
            db.add(task)
            db.flush()

        # 更新状态/进度
        try:
            task.status = TaskStatus(status) if isinstance(status, TaskStatus) else TaskStatus[status]  # type: ignore[index]
        except Exception:
            pass
        try:
            task.progress_percentage = int(progress)
        except Exception:
            pass
        task.current_step = current_step

        # 元数据
        if hasattr(task, "output_metadata"):
            task.output_metadata = {
                "concept_plan": concept_plan,
                "intelligent_style_design": intelligent_style_design,
                "voice_plan": voice_plan,
                "content_elements": content_elements,
            }
        db.flush()
        return task

    def _persist_scenes_from_payload(self, task: Task, scenes: List[Dict[str, Any]], db: Session) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for sd in scenes:
            if not isinstance(sd, dict):
                continue
            sn = sd.get("scene_number")
            if sn is None:
                continue
            existing = db.query(Scene).filter(Scene.task_id == task.id, Scene.scene_number == sn).first()
            if existing:
                scene = existing
                status = "updated"
            else:
                scene = Scene(task_id=task.id, scene_number=sn)
                db.add(scene)
                status = "created"
            self._update_scene_from_payload(scene, sd)
            db.flush()
            results.append({"scene_id": scene.id, "scene_number": scene.scene_number, "status": status})
        return results

    def _persist_resources_from_payload(self, task: Task, resources: List[Dict[str, Any]], scenes: List[Dict[str, Any]], db: Session) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        scene_index = {(sd.get("scene_number")): sd for sd in scenes if isinstance(sd, dict)}
        for res in resources:
            if not isinstance(res, dict):
                continue
            scene_number = res.get("scene_number")
            scene = None
            if scene_number is not None:
                scene = db.query(Scene).filter(Scene.task_id == task.id, Scene.scene_number == scene_number).first()
            file_url = (res.get("url") or res.get("file_url") or "") if isinstance(res.get("url") or res.get("file_url"), str) else ""
            file_path = (res.get("path") or res.get("file_path") or "") if isinstance(res.get("path") or res.get("file_path"), str) else ""
            rtype = res.get("resource_type") or res.get("type") or ""
            # 兼容旧字段：缺失资源列表时，从 scenes 衍生
            if not (file_url or file_path) and scene_number in scene_index:
                sd = scene_index.get(scene_number) or {}
                kind = res.get("kind") or sd.get("kind")
                if kind == "video":
                    file_url = (sd.get("video_url") or "") if isinstance(sd.get("video_url"), str) else ""
                    file_path = (sd.get("video_path") or "") if isinstance(sd.get("video_path"), str) else ""
                    rtype = rtype or ResourceType.VIDEO
                if kind == "audio":
                    file_url = (sd.get("audio_url") or "") if isinstance(sd.get("audio_url"), str) else ""
                    file_path = (sd.get("audio_path") or "") if isinstance(sd.get("audio_path"), str) else ""
                    rtype = rtype or self._resolve_voice_resource_type()
            if not (file_url or file_path):
                continue
            try:
                if isinstance(rtype, ResourceType):
                    resource_type = rtype
                elif isinstance(rtype, str):
                    try:
                        resource_type = ResourceType(rtype)
                    except Exception:
                        resource_type = ResourceType[rtype.upper()]  # type: ignore[index]
                else:
                    resource_type = ResourceType.VIDEO
            except Exception:
                resource_type = ResourceType.VIDEO
            model = Resource(
                task_id=task.id,
                scene_id=scene.id if scene else None,
                filename=res.get("filename") or f"scene_{scene_number}_{resource_type.value}",
                file_path=file_path,
                file_url=file_url,
                resource_type=resource_type,
            )
            db.add(model)
            results.append({"scene_number": scene_number, "resource_id": model.id, "status": "created"})

        # 兼容 task 级 final 视频
        for res in resources:
            if not isinstance(res, dict):
                continue
            if res.get("scope") == "task" and res.get("kind") == "final_video":
                model = Resource(
                    task_id=task.id,
                    filename=res.get("filename") or f"task_{task.id}_final_video",
                    file_path=res.get("path") or res.get("file_path") or "",
                    file_url=res.get("url") or res.get("file_url") or "",
                    resource_type=ResourceType.VIDEO,
                )
                db.add(model)
                results.append({"task_id": task.id, "resource_id": model.id, "status": "created"})
        db.flush()
        return results

    def _update_scene_from_payload(self, scene: Scene, payload: Dict[str, Any]) -> None:
        def _s(key: str) -> str:
            v = payload.get(key)
            return v if isinstance(v, str) else (str(v) if v is not None else "")

        def _f(key: str, default: float = 0.0) -> float:
            try:
                return float(payload.get(key, default) or default)
            except Exception:
                return default

        scene.scene_type = SceneType.MAIN_CONTENT
        scene.title = _s("title")
        scene.description = _s("description")
        scene.duration = _f("duration", 0.0)
        scene.start_time = _f("start_time", 0.0)
        scene.end_time = _f("end_time", scene.start_time + scene.duration)

        scene.visual_description = _s("visual_description")
        scene.narrative_description = _s("narrative_description")
        scene.mood_and_atmosphere = _s("mood_and_atmosphere")
        scene.camera_angle = _s("camera_angle")
        scene.lighting_style = _s("lighting_style")
        scene.art_style = _s("art_style")
        scene.script_text = _s("script_text")
        scene.voice_over_text = _s("voice_over_text")

    def _resolve_voice_resource_type(self) -> ResourceType:
        try:
            enum_values = getattr(Resource.__table__.c.resource_type.type, "enums", [])
        except Exception:
            enum_values = []
        if ResourceType.VOICE_OVER.value in enum_values:
            return ResourceType.VOICE_OVER
        return ResourceType.AUDIO
