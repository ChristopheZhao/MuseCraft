import asyncio
import logging
import time
from typing import Awaitable, Callable, Dict, Iterable, List, Optional, Sequence

from .models import Event, EventKind

EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """事件总线接口：发布事件、订阅回调。"""

    async def publish(self, event: Event) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def subscribe(
        self,
        handler: EventHandler,
        *,
        kinds: Optional[Sequence[EventKind]] = None,
    ) -> Callable[[], None]:  # pragma: no cover - interface
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    """
    进程内异步 pub/sub。
    - 支持按事件类型订阅，kinds=None 表示订阅全部。
    - 监听器异常不会阻断其他订阅者，统一记录日志。
    """

    def __init__(self, *, max_retries: int = 1, retry_backoff_seconds: float = 0.1) -> None:
        self._logger = logging.getLogger(__name__)
        self._subscribers: Dict[Optional[EventKind], List[EventHandler]] = {}
        self._lock = asyncio.Lock()
        self._dead_letters: List[Dict[str, object]] = []
        self._metrics: Dict[str, int] = {"published": 0, "delivered": 0, "failed": 0}
        self._max_retries = max(0, int(max_retries))
        self._retry_backoff = max(0.0, retry_backoff_seconds)

    def subscribe(
        self,
        handler: EventHandler,
        *,
        kinds: Optional[Sequence[EventKind]] = None,
    ) -> Callable[[], None]:
        # 订阅是轻量同步操作，避免在无事件循环环境下创建任务的风险
        key_list: Iterable[Optional[EventKind]] = kinds or [None]
        for kind in key_list:
            self._subscribers.setdefault(kind, []).append(handler)

        def _unsubscribe() -> None:
            try:
                for kind in kinds or [None]:
                    handlers = self._subscribers.get(kind, [])
                    if handler in handlers:
                        handlers.remove(handler)
            except Exception:
                self._logger.exception("Failed to unsubscribe handler")

        return _unsubscribe

    async def publish(self, event: Event) -> None:
        # 发布前确保 payload 尺寸与可序列化
        event.clamp_payload()
        self._metrics["published"] += 1

        async with self._lock:
            handlers = list(self._subscribers.get(event.event_kind, []))
            handlers += list(self._subscribers.get(None, []))

        if not handlers:
            self._logger.debug("No subscribers for event %s", event.event_kind.value)
            return

        await asyncio.gather(*(self._invoke_with_retry(h, event) for h in handlers), return_exceptions=True)

    async def _invoke_with_retry(self, handler: EventHandler, event: Event) -> None:
        attempt = 0
        start_ts = time.time()
        while True:
            try:
                await handler(event)
                self._metrics["delivered"] += 1
                return
            except Exception as exc:  # pragma: no cover - error path
                attempt += 1
                if attempt > self._max_retries:
                    self._metrics["failed"] += 1
                    self._dead_letters.append(
                        {
                            "event": event.as_dict(),
                            "handler": getattr(handler, "__name__", str(handler)),
                            "error": str(exc),
                            "attempts": attempt,
                            "elapsed_sec": round(time.time() - start_ts, 4),
                        }
                    )
                    self._logger.exception(
                        "Event handler failed after retries (kind=%s, handler=%s)",
                        event.event_kind.value,
                        getattr(handler, "__name__", str(handler)),
                    )
                    return
                # 重试前简单退避
                if self._retry_backoff > 0:
                    await asyncio.sleep(self._retry_backoff)

    def get_dead_letters(self) -> List[Dict[str, object]]:
        return list(self._dead_letters)

    def get_metrics(self) -> Dict[str, int]:
        return dict(self._metrics)
