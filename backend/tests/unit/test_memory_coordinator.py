"""Memory service composition tests."""

from app.services.memory_provider import build_memory_services


def test_memory_services_expose_decoupled_public_facades() -> None:
    services = build_memory_services()

    assert services.global_service.long_term is services.long_term
    assert services.short_term is not None
    assert not hasattr(services.global_service, "_memory_coordinator")
