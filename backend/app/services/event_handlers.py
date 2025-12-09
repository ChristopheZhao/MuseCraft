import asyncio
import logging
from typing import Dict, Any

from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..events.models import Event, EventKind
from .data_persistence import DataPersistenceService

logger = logging.getLogger(__name__)


async def handle_persistence_event(event: Event) -> None:
    """
    Persistence sink：消费事件载荷/终态摘要，最小投影落库（任务/资源）。
    - 独立 Session，每次事件自建/提交/回滚。
    - 不读取 WM，不透传上游事务。
    """
    if event.event_kind not in (EventKind.STATE, EventKind.ARTIFACT, EventKind.ERROR):
        return
    if not event.task_id:
        return

    def _build_payload() -> Dict[str, Any]:
        payload = dict(event.payload or {})
        payload.setdefault("task_id", str(event.task_id))
        payload.setdefault("external_task_id", str(event.task_id))
        # 将单个产物事件包装为 resources 列表
        if event.event_kind == EventKind.ARTIFACT:
            res = {
                "scene_number": payload.get("scene_number") or event.scene_number,
                "url": payload.get("url") or payload.get("file_url"),
                "path": payload.get("file_path") or payload.get("path"),
                "resource_type": payload.get("resource_type") or payload.get("kind"),
                "kind": payload.get("kind"),
            }
            payload.setdefault("resources", []).append(res)
        # workflow 完成事件附带 final_video
        if payload.get("final_video_url") or payload.get("final_video_path"):
            payload.setdefault("resources", []).append(
                {
                    "scope": "task",
                    "kind": "final_video",
                    "url": payload.get("final_video_url"),
                    "path": payload.get("final_video_path"),
                    "resource_type": "video",
                }
            )
        # 状态映射
        if event.event_kind == EventKind.STATE and "status" not in payload:
            payload["status"] = payload.get("state") or "PERSISTING"
        return payload

    def _sync_handle() -> None:
        payload = _build_payload()
        svc = DataPersistenceService()
        with SessionLocal() as db:  # type: Session
            svc.persist_from_event_payload(payload, db)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    try:
        if loop:
            await loop.run_in_executor(None, _sync_handle)
        else:
            _sync_handle()
    except Exception as exc:
        logger.error("Persistence sink failed for event %s: %s", event.event_kind.value, exc, exc_info=True)
