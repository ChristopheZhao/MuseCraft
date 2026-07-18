"""Service constructors must not schedule external Redis I/O."""

from app.services import enhanced_ai_client as enhanced_module
from app.services import monitoring_service as monitoring_module


class _LazyRedisClient:
    async def ping(self):  # pragma: no cover - must never be called by constructors
        raise AssertionError("constructor performed Redis I/O")


def test_enhanced_ai_client_constructor_only_builds_lazy_redis_client(monkeypatch) -> None:
    redis_client = _LazyRedisClient()
    monkeypatch.setattr(enhanced_module.redis, "from_url", lambda _url: redis_client)

    service = enhanced_module.EnhancedAIClient()

    assert service.redis_client is redis_client


def test_monitoring_service_constructor_only_builds_lazy_redis_client(monkeypatch) -> None:
    redis_client = _LazyRedisClient()
    monkeypatch.setattr(monitoring_module.redis, "from_url", lambda _url: redis_client)

    service = monitoring_module.MonitoringService()

    assert service.redis_client is redis_client
