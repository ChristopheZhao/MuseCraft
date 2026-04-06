from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.base import AgentError
from app.agents.concept_planner import ConceptPlannerAgent
from app.agents.tools.ai_services.service_interfaces import LLMServiceInterface, ServiceProvider
from app.agents.utils import llm_policy as llm_policy_module


class _DummyLLMService(LLMServiceInterface):
    def __init__(self, provider_name: str):
        self._provider_name = provider_name

    async def chat_completion(self, messages, model=None, temperature=0.7, max_tokens=2000, **kwargs):
        return {"content": "{}", "model": model or "dummy"}

    async def function_call(self, messages, tools, tool_choice="auto", model=None, temperature=0.3, **kwargs):
        return {"content": "{}", "model": model or "dummy"}

    def get_supported_models(self):
        return []

    def get_provider_name(self) -> str:
        return self._provider_name

    def is_available(self) -> bool:
        return True


def _make_agent() -> ConceptPlannerAgent:
    return ConceptPlannerAgent(
        memory_services=SimpleNamespace(
            global_service=None,
            long_term=None,
            short_term=None,
        )
    )


def test_resolve_planning_route_uses_plan_role_route(monkeypatch):
    agent = _make_agent()
    monkeypatch.setattr(
        agent,
        "get_llm_route",
        lambda role="default": {"provider_name": "deepseek", "model": "deepseek-chat"},
    )

    model_configs = {
        "deepseek-chat": SimpleNamespace(
            provider="deepseek",
            max_tokens=8192,
            temperature=0.7,
            fallback_model="deepseek-reasoner",
        ),
        "deepseek-reasoner": SimpleNamespace(
            provider="deepseek",
            max_tokens=64000,
            temperature=0.7,
            fallback_model="deepseek-chat",
        ),
    }
    fake_ai_config = SimpleNamespace(
        get_model_config=lambda model: model_configs.get(model),
        get_model_provider=lambda model: {
            "deepseek-chat": "deepseek",
            "deepseek-reasoner": "deepseek",
        }.get(model),
    )
    monkeypatch.setattr("app.core.ai_config.get_ai_config", lambda: fake_ai_config)
    monkeypatch.setattr(agent.logger, "info", lambda *args, **kwargs: None)

    route = agent._resolve_planning_route()

    assert route["provider_name"] == "deepseek"
    assert route["model_name"] == "deepseek-chat"
    assert route["fallback_model"] == "deepseek-reasoner"
    assert route["model_config"] is model_configs["deepseek-chat"]


def test_resolve_planning_route_rejects_cross_provider_fallback(monkeypatch):
    agent = _make_agent()
    monkeypatch.setattr(
        agent,
        "get_llm_route",
        lambda role="default": {"provider_name": "deepseek", "model": "deepseek-chat"},
    )

    model_configs = {
        "deepseek-chat": SimpleNamespace(
            provider="deepseek",
            max_tokens=8192,
            temperature=0.7,
            fallback_model="glm-4.5",
        ),
        "glm-4.5": SimpleNamespace(
            provider="zhipu",
            max_tokens=24000,
            temperature=0.7,
            fallback_model="glm-4.5-air",
        ),
    }
    fake_ai_config = SimpleNamespace(
        get_model_config=lambda model: model_configs.get(model),
        get_model_provider=lambda model: {
            "deepseek-chat": "deepseek",
            "glm-4.5": "zhipu",
        }.get(model),
    )
    monkeypatch.setattr("app.core.ai_config.get_ai_config", lambda: fake_ai_config)
    monkeypatch.setattr(agent.logger, "info", lambda *args, **kwargs: None)

    with pytest.raises(AgentError, match="cross-provider fallback is not allowed"):
        agent._resolve_planning_route()


def test_repo_policy_routes_concept_planner_plan_to_deepseek(monkeypatch):
    captured = []

    monkeypatch.setattr(
        llm_policy_module,
        "get_llm_service",
        lambda provider=None: captured.append(provider) or _DummyLLMService(provider.value),
    )
    monkeypatch.setattr(
        llm_policy_module,
        "get_ai_config",
        lambda: SimpleNamespace(
            get_model_provider=lambda model: {
                "glm-4-plus": "zhipu",
                "deepseek-chat": "deepseek",
            }.get(model)
        ),
    )

    policy_path = Path(__file__).resolve().parents[2] / "app" / "config" / "llm_policies.yaml"
    manager = llm_policy_module.LLMPolicyManager(str(policy_path))
    handles = manager.build_llms_for_agent("concept_planner")

    assert ServiceProvider.DEEPSEEK in captured
    assert handles["plan"].provider_name == "deepseek"
    assert handles["plan"].default_model == "deepseek-chat"
