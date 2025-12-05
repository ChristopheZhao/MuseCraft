import inspect
import logging
from typing import Awaitable, Callable, Optional, Sequence

from .models import Event, EventKind
from .sinks import FileEpisodicSink

try:
    from ..services.websocket import WebSocketManager
except Exception:  # pragma: no cover - optional import guard
    WebSocketManager = None  # type: ignore


class EventListener:
    """监听器基类：按事件类型过滤，异常不抛出到总线。"""

    def __init__(self, event_kinds: Optional[Sequence[EventKind]] = None) -> None:
        self._event_kinds = set(event_kinds) if event_kinds else None
        self.logger = logging.getLogger(self.__class__.__name__.lower())

    def supports(self, event: Event) -> bool:
        if self._event_kinds is None:
            return True
        return event.event_kind in self._event_kinds

    async def __call__(self, event: Event) -> None:
        if not self.supports(event):
            return
        try:
            await self.handle_event(event)
        except Exception:
            self.logger.exception(
                "Listener failed (kind=%s, listener=%s)",
                event.event_kind.value,
                self.__class__.__name__,
            )

    async def handle_event(self, event: Event) -> None:  # pragma: no cover - abstract
        raise NotImplementedError


class NotificationListener(EventListener):
    """
    WebSocket 推送监听器。
    仅关注进度/状态/产物/错误事件，消息保持精简，payload 仅预览。
    """

    def __init__(self, websocket_manager: WebSocketManager):
        super().__init__(
            event_kinds=[
                EventKind.PROGRESS,
                EventKind.STATE,
                EventKind.ARTIFACT,
                EventKind.ERROR,
            ]
        )
        self._ws = websocket_manager

    async def handle_event(self, event: Event) -> None:
        if not event.task_id:
            self.logger.debug("Skip WS push: missing task_id (kind=%s)", event.event_kind.value)
            return

        payload_preview = event.payload or {}
        message = {
            "type": f"event.{event.event_kind.value}",
            "task_id": str(event.task_id),
            "workflow_state_id": event.workflow_state_id,
            "agent_type": event.agent_type,
            "agent_name": event.agent_name,
            "iteration": event.iteration,
            "scene_number": event.scene_number,
            "payload": payload_preview,
            "timestamp": event.timestamp,
            "schema_version": event.schema_version,
        }

        try:
            await self._ws.broadcast_to_task(str(event.task_id), message)
        except Exception as exc:
            self.logger.warning(
                "WebSocket push failed (kind=%s, task=%s): %s",
                event.event_kind.value,
                event.task_id,
                exc,
            )


class PersistenceListener(EventListener):
    """
    持久化监听器的可插拔封装。
    sink 可是同步或异步函数，未配置时仅记录 debug，不阻断事件流。
    """

    def __init__(self, sink: Optional[Callable[[Event], Optional[Awaitable[None]]]] = None):
        super().__init__()
        self._sink = sink

    async def handle_event(self, event: Event) -> None:
        if not self._sink:
            self.logger.debug("Persistence sink not configured, skip event %s", event.event_kind.value)
            return
        result = self._sink(event)
        if inspect.isawaitable(result):
            await result


def build_file_episodic_listener(log_path: str) -> EventListener:
    sink = FileEpisodicSink(log_path)
    return EpisodicListener(sink)


class EpisodicListener(EventListener):
    """
    轨迹监听器：将事件写入长期轨迹存储（日志/对象存储等）。
    writer 可是同步或异步函数；未配置时降级为 debug。
    """

    def __init__(self, writer: Optional[Callable[[Event], Optional[Awaitable[None]]]] = None):
        super().__init__()
        self._writer = writer

    async def handle_event(self, event: Event) -> None:
        if not self._writer:
            self.logger.debug("Episodic writer not configured, skip event %s", event.event_kind.value)
            return
        result = self._writer(event)
        if inspect.isawaitable(result):
            await result
