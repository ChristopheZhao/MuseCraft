import logging
from typing import Callable, Optional

from .bus import EventBus
from .listeners import (
    TraceLogListener,
    NotificationListener,
    PersistenceListener,
    build_file_trace_listener,
)
from .provider import get_event_bus


def setup_event_listeners(
    *,
    websocket_manager=None,
    persistence_sink: Optional[Callable] = None,
    episodic_sink: Optional[Callable] = None,
    episodic_log_path: Optional[str] = None,
    bus: Optional[EventBus] = None,
) -> EventBus:
    """
    注册默认事件监听器。
    - WebSocket 推送：仅进度/状态/产物/错误事件，payload 预览。
    - 持久化 sink 可选注入；轨迹日志 sink 仅用于调试（非记忆/审计）。
    """
    logger = logging.getLogger(__name__)
    event_bus = bus or get_event_bus()

    if websocket_manager is not None:
        listener = NotificationListener(websocket_manager)
        event_bus.subscribe(listener)
        logger.info("EventBus: NotificationListener registered")
    else:
        logger.info("EventBus: websocket manager not provided, skip NotificationListener")

    if persistence_sink is not None:
        event_bus.subscribe(PersistenceListener(persistence_sink))
        logger.info("EventBus: PersistenceListener registered (sink=%s)", getattr(persistence_sink, "__name__", type(persistence_sink)))
    else:
        logger.info("EventBus: persistence sink not provided, PersistenceListener skipped")

    if episodic_sink is not None:
        event_bus.subscribe(TraceLogListener(episodic_sink))
        logger.info("EventBus: TraceLogListener registered (sink=%s)", getattr(episodic_sink, "__name__", type(episodic_sink)))
    elif episodic_log_path:
        event_bus.subscribe(build_file_trace_listener(episodic_log_path))
        logger.info("EventBus: TraceLogListener registered (file sink=%s)", episodic_log_path)
    else:
        logger.info("EventBus: trace/episodic sink not provided, TraceLogListener skipped")

    return event_bus
