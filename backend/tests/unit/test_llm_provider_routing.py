from pathlib import Path

import pytest

from app.agents.tools.ai_services.service_interfaces import (
    LLMServiceInterface,
    ServiceManager,
    ServiceProvider,
)
from app.agents.utils import llm_policy as llm_policy_module


class _DummyLLMService(LLMServiceInterface):
    def __init__(self, provider_name: str, *, available: bool = True):
        self._provider_name = provider_name
        self._available = available

    async def chat_completion(self, messages, model=None, temperature=0.7, max_tokens=2000, **kwargs):
        return {"content": "{}", "model": model or "dummy"}

    async def function_call(self, messages, tools, tool_choice="auto", model=None, temperature=0.3, **kwargs):
        return {"content": "{}", "model": model or "dummy"}

    def get_supported_models(self):
        return []

    def get_provider_name(self) -> str:
        return self._provider_name

    def is_available(self) -> bool:
        return self._available


def _write_policy(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_llm_policy_uses_configured_non_zhipu_provider(tmp_path, monkeypatch):
    policy_path = tmp_path / "llm_policies.yaml"
    _write_policy(
        policy_path,
        """
default:
  provider: openai
  model: gpt-4
""".strip(),
    )

    captured = []
    openai_service = _DummyLLMService("openai")

    monkeypatch.setattr(
        llm_policy_module,
        "get_llm_service",
        lambda provider=None: captured.append(provider) or openai_service,
    )
    monkeypatch.setattr(
        llm_policy_module,
        "get_ai_config",
        lambda: type(
            "_FakeAIConfig",
            (),
            {"get_model_provider": staticmethod(lambda model: "openai" if model == "gpt-4" else None)},
        )(),
    )

    manager = llm_policy_module.LLMPolicyManager(str(policy_path))
    handles = manager.build_llms_for_agent("concept_planner")

    assert captured == [ServiceProvider.OPENAI]
    assert handles["default"].provider_name == "openai"


def test_llm_policy_rejects_provider_model_mismatch(tmp_path, monkeypatch):
    policy_path = tmp_path / "llm_policies.yaml"
    _write_policy(
        policy_path,
        """
default:
  provider: openai
  model: glm-4.5
""".strip(),
    )

    monkeypatch.setattr(
        llm_policy_module,
        "get_ai_config",
        lambda: type(
            "_FakeAIConfig",
            (),
            {"get_model_provider": staticmethod(lambda model: "zhipu" if model == "glm-4.5" else None)},
        )(),
    )

    manager = llm_policy_module.LLMPolicyManager(str(policy_path))
    with pytest.raises(ValueError, match="provider/model mismatch"):
        manager.build_llms_for_agent("concept_planner")


def test_service_manager_does_not_cross_fallback_llm_provider():
    manager = ServiceManager()
    manager.register_llm_service(ServiceProvider.ZHIPU, _DummyLLMService("zhipu", available=False))
    manager.register_llm_service(ServiceProvider.OPENAI, _DummyLLMService("openai", available=True))

    with pytest.raises(RuntimeError, match="provider 'zhipu' is unavailable"):
        manager.get_llm_service(ServiceProvider.ZHIPU)


def test_service_manager_reports_unregistered_llm_provider():
    manager = ServiceManager()
    manager.register_llm_service(ServiceProvider.ZHIPU, _DummyLLMService("zhipu", available=True))

    with pytest.raises(ValueError, match="provider 'openai' is not registered"):
        manager.get_llm_service(ServiceProvider.OPENAI)
