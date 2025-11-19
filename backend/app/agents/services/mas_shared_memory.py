"""MAS-level working memory helpers moved to application service layer."""
from __future__ import annotations

from typing import Dict, List, Optional

from ..memory.short_term import (
    get_working_memory_service,
    WorkflowFactStore,
    WorkflowFactStoreError,
)
from ..memory.short_term.service import MemoryNotInitializedError, WorkingMemoryService
from ..memory.short_term.working_memory import WorkingMemory
from ..adapters.video import SceneSnapshot, SceneArtifact, VideoMemoryAdapter
from ..utils.memory_helpers import mas_scope


def _ensure_workflow_memory(service: WorkingMemoryService, workflow_id: str) -> WorkingMemory:
    scope = mas_scope(workflow_id)
    try:
        return service.get(workflow_id, scope)
    except MemoryNotInitializedError:
        return service.create_or_get(workflow_id, scope, owner_agent=None)


class MasSharedMemoryFacade:
    def __init__(self, wm_service: WorkingMemoryService, fact_store: WorkflowFactStore):
        self._wm_service = wm_service
        self._fact_store = fact_store

    def get_task(self, workflow_id: str) -> WorkingMemory:
        return _ensure_workflow_memory(self._wm_service, workflow_id)

    def upsert_scene(self, workflow_id: str, snapshot: SceneSnapshot) -> None:
        VideoMemoryAdapter(self.get_task(workflow_id)).upsert_scene(snapshot)

    def register_artifact_ref(self, workflow_id: str, scene_number: int, artifact: Dict[str, Any]) -> None:
        wm = self.get_task(workflow_id)
        payload: Dict[str, Any]
        if isinstance(artifact, SceneArtifact):
            payload = artifact.as_output(scene_number)
        elif isinstance(artifact, dict):
            payload = dict(artifact)
        else:
            payload = {"scene_number": scene_number, "value": artifact}
        wm.add_iteration_artifact(
            kind=payload.get("kind", "scene"),
            scene_number=scene_number,
            url=payload.get("video_url") or payload.get("audio_url") or payload.get("url", ""),
            file_path=payload.get("video_path") or payload.get("audio_path") or payload.get("file_path", ""),
            duration=payload.get("duration") or payload.get("duration_sec"),
            prompt_text=payload.get("prompt_text", ""),
            stage=payload.get("stage"),
            metadata=payload,
        )

    def add_artifact(self, workflow_id: str, record: Dict[str, Any]) -> None:
        wm = self.get_task(workflow_id)
        payload = dict(record or {})
        wm.add_iteration_artifact(
            kind=payload.get("kind", "artifact"),
            scene_number=payload.get("scene_number"),
            url=payload.get("url", ""),
            file_path=payload.get("file_path", ""),
            duration=payload.get("duration") or payload.get("duration_sec"),
            prompt_text=payload.get("prompt_text", ""),
            stage=payload.get("stage"),
            metadata=payload.get("metadata"),
            ts=payload.get("ts"),
        )

    def list_artifacts(
        self,
        workflow_id: str,
        *,
        kind: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        wm = self.get_task(workflow_id)
        items = list(wm.iteration_artifacts or [])
        if not items:
            return []

        def _ok(it: Dict[str, Any]) -> bool:
            if kind and it.get("kind") != kind:
                return False
            if stage and it.get("stage") != stage:
                return False
            return True

        return [it for it in items if _ok(it)]

    def get_latest_artifact(
        self,
        workflow_id: str,
        *,
        kind: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        items = self.list_artifacts(workflow_id, kind=kind, stage=stage)
        return items[-1] if items else None

    def delete_task(self, workflow_id: str) -> None:
        scope = mas_scope(workflow_id)
        self._wm_service.delete(workflow_id, scope, sync_to_slots=False)


_shared_facade: Optional[MasSharedMemoryFacade] = None


def configure_shared_wm(
    fact_store: WorkflowFactStore,
    working_memory_service: WorkingMemoryService,
) -> None:
    global _shared_facade
    _shared_facade = MasSharedMemoryFacade(working_memory_service, fact_store)


def get_shared_wm() -> MasSharedMemoryFacade:
    if _shared_facade is None:
        raise RuntimeError("MAS shared memory facade not configured")
    return _shared_facade


__all__ = ["MasSharedMemoryFacade", "get_shared_wm", "configure_shared_wm"]
