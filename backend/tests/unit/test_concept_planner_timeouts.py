from types import SimpleNamespace

from app.agents.base import AgentError
from app.agents.concept_planner import ConceptPlannerAgent


def test_resolve_stage_timeout_uses_stage_budget(monkeypatch):
    agent = ConceptPlannerAgent(
        memory_services=SimpleNamespace(
            global_service=None,
            long_term=None,
            short_term=None,
        )
    )
    monkeypatch.setattr("app.agents.concept_planner.time.monotonic", lambda: 100.0)
    monkeypatch.setattr(agent.logger, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent.logger, "error", lambda *args, **kwargs: None)

    monkeypatch.setattr("app.agents.concept_planner.settings.LLM_REQUEST_SAFETY_MARGIN", 5, raising=False)
    monkeypatch.setattr("app.agents.concept_planner.settings.CONCEPT_STAGE_TIMEOUT_SCENE_BATCH", 90, raising=False)
    monkeypatch.setattr(
        "app.agents.concept_planner.settings.CONCEPT_STAGE_TIMEOUT_SCENE_BATCH_FLOOR",
        45,
        raising=False,
    )

    timeout = agent._resolve_stage_timeout("scene_batch", deadline_ts=240.0)

    assert timeout == 90


def test_resolve_stage_timeout_fails_fast_when_remaining_budget_below_floor(monkeypatch):
    agent = ConceptPlannerAgent(
        memory_services=SimpleNamespace(
            global_service=None,
            long_term=None,
            short_term=None,
        )
    )
    monkeypatch.setattr("app.agents.concept_planner.time.monotonic", lambda: 100.0)
    monkeypatch.setattr(agent.logger, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent.logger, "error", lambda *args, **kwargs: None)

    monkeypatch.setattr("app.agents.concept_planner.settings.LLM_REQUEST_SAFETY_MARGIN", 5, raising=False)
    monkeypatch.setattr(
        "app.agents.concept_planner.settings.CONCEPT_STAGE_TIMEOUT_SCENE_BATCH_FLOOR",
        45,
        raising=False,
    )

    try:
        agent._resolve_stage_timeout("scene_batch", deadline_ts=140.0)
    except AgentError as exc:
        assert "timeout_budget_exhausted" in str(exc)
    else:
        raise AssertionError("expected timeout_budget_exhausted")
