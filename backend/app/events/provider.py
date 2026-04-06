import logging
from typing import Optional

from .bus import EventBus, InMemoryEventBus

_event_bus: Optional[EventBus] = None
logger = logging.getLogger(__name__)


def get_event_bus() -> EventBus:
    """
    获取事件总线实例，默认使用进程内实现。
    可通过 set_event_bus 注入自定义实现（如消息队列）。
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = InMemoryEventBus()
        logger.info("Initialized default InMemoryEventBus")
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    global _event_bus
    _event_bus = bus
    logger.info("Event bus overridden with custom implementation: %s", type(bus).__name__)


def reset_event_bus() -> EventBus:
    """Replace the process-local bus with a fresh in-memory instance."""
    bus = InMemoryEventBus()
    set_event_bus(bus)
    logger.info("Event bus reset to a fresh InMemoryEventBus instance")
    return bus
