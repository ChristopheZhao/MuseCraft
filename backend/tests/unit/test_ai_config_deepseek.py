import logging

from app.agents.tools.ai_services import service_interfaces
from app.agents.tools.ai_services.service_interfaces import ServiceManager, ServiceProvider
from app.core import ai_config as ai_config_module
from app.core.ai_config import AIConfigManager


def _blank_ai_config_manager() -> AIConfigManager:
    manager = AIConfigManager.__new__(AIConfigManager)
    manager.logger = logging.getLogger("test.ai_config.deepseek")
    manager.providers = {}
    manager.models = {}
    manager.agent_model_mapping = {}
    manager.tool_model_mapping = {}
    manager.tool_provider_mapping = {}
    manager.agent_fallback_model_mapping = {}
    manager.agent_thinking_mode = {}
    return manager


def test_merge_user_config_creates_deepseek_provider_and_models():
    manager = _blank_ai_config_manager()

    manager._merge_user_config(
        {
            "providers": {
                "deepseek": {
                    "default_model": "deepseek-chat",
                    "api_key": "deepseek-config-key",
                    "base_url": "https://api.deepseek.com",
                    "enabled": True,
                    "timeout": 120,
                    "rate_limit": 80,
                }
            },
            "models": {
                "deepseek-chat": {
                    "provider": "deepseek",
                    "temperature": 0.7,
                    "max_tokens": 8192,
                    "enabled": True,
                    "timeout": 120,
                    "fallback_model": "deepseek-reasoner",
                    "capabilities": ["text_generation", "chat", "reasoning", "json_output"],
                },
                "deepseek-reasoner": {
                    "provider": "deepseek",
                    "temperature": 0.7,
                    "max_tokens": 64000,
                    "enabled": True,
                    "timeout": 120,
                    "fallback_model": "deepseek-chat",
                    "capabilities": ["text_generation", "chat", "reasoning", "json_output", "thinking"],
                },
            },
        }
    )

    provider = manager.get_provider_config("deepseek")
    assert provider is not None
    assert provider.default_model == "deepseek-chat"
    assert provider.api_key == "deepseek-config-key"
    assert provider.base_url == "https://api.deepseek.com"
    assert provider.timeout == 120
    assert provider.rate_limit == 80

    chat_model = manager.get_model_config("deepseek-chat")
    assert chat_model is not None
    assert chat_model.provider == "deepseek"
    assert chat_model.max_tokens == 8192
    assert chat_model.fallback_model == "deepseek-reasoner"
    assert provider.models["deepseek-chat"] is chat_model

    reasoner_model = manager.get_model_config("deepseek-reasoner")
    assert reasoner_model is not None
    assert reasoner_model.provider == "deepseek"
    assert reasoner_model.max_tokens == 64000
    assert provider.models["deepseek-reasoner"] is reasoner_model


def test_deepseek_diagnostics_accept_provider_config_api_key(monkeypatch):
    manager = _blank_ai_config_manager()
    manager._merge_user_config(
        {
            "providers": {
                "deepseek": {
                    "default_model": "deepseek-chat",
                    "api_key": "deepseek-config-key",
                    "enabled": True,
                }
            }
        }
    )

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(ai_config_module, "get_ai_config", lambda: manager)

    diag = service_interfaces._diagnose_provider_requirements(ServiceProvider.DEEPSEEK, "llm")

    assert diag["provider"] == "deepseek"
    assert diag["missing_required_env"] == []


def test_initialize_default_services_registers_deepseek_from_provider_config(monkeypatch):
    ai_manager = _blank_ai_config_manager()
    ai_manager._merge_user_config(
        {
            "providers": {
                "deepseek": {
                    "default_model": "deepseek-chat",
                    "api_key": "deepseek-config-key",
                    "base_url": "https://api.deepseek.com",
                    "enabled": True,
                    "timeout": 120,
                }
            }
        }
    )

    service_manager = ServiceManager()
    monkeypatch.setattr(ai_config_module, "get_ai_config", lambda: ai_manager)
    monkeypatch.setattr(service_interfaces, "_service_manager", service_manager)
    monkeypatch.setattr(service_interfaces, "_emit_service_registration_diagnostics", lambda manager: None)
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DOUBAO_API_KEY", raising=False)

    service_interfaces._initialize_default_services()

    assert ServiceProvider.DEEPSEEK in service_manager._llm_services
    assert service_manager.get_llm_service(ServiceProvider.DEEPSEEK).get_provider_name() == "deepseek"
