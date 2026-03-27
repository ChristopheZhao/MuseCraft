import os
import yaml
from typing import Dict, Any, Optional

from ..tools.ai_services.service_interfaces import (
    get_llm_service,
    resolve_llm_provider,
    get_supported_llm_provider_names,
)
from ...core.ai_config import get_ai_config
from ...core.config import settings


class RoleLLM:
    """A thin wrapper binding a default model to an LLM service for a specific role."""

    def __init__(self, service, default_model: Optional[str] = None, provider_name: Optional[str] = None):
        self._service = service
        self._model = default_model
        self._provider_name = provider_name or getattr(service, "get_provider_name", lambda: None)()

    async def chat_completion(self, messages, **kwargs):
        if not kwargs.get("model") and self._model:
            kwargs["model"] = self._model
        return await self._service.chat_completion(messages=messages, **kwargs)

    async def function_call(self, messages, tools, **kwargs):
        if not kwargs.get("model") and self._model:
            kwargs["model"] = self._model
        return await self._service.function_call(messages=messages, tools=tools, **kwargs)

    @property
    def provider_name(self) -> Optional[str]:
        return self._provider_name

    @property
    def default_model(self) -> Optional[str]:
        return self._model


class LLMPolicyManager:
    """
    Loads llm_policies.yaml and constructs per-agent LLM handles for roles
    {default, observe, plan, act}.
    """

    def __init__(self, policy_path: str):
        self.policy_path = policy_path
        self._mtime = 0.0
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.policy_path):
            self._data = {}
            return
        st = os.stat(self.policy_path)
        if st.st_mtime <= self._mtime:
            return
        with open(self.policy_path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}
        self._mtime = st.st_mtime

    def get_policy_for_agent(self, agent_name: str) -> Dict[str, Any]:
        self._load()
        agent_key = f"agents.{agent_name}"
        default = self._data.get("default", {})
        agent_pol = self._data.get(agent_key, {})
        return {**default, **agent_pol}

    def _resolve_model_alias(self, model: Optional[str]) -> Optional[str]:
        if not model:
            return model
        if model == "glm-default":
            return settings.GLM_DEFAULT_MODEL
        if model == "glm-light":
            return settings.GLM_LIGHT_MODEL
        return model

    def _resolve_role_route(
        self,
        *,
        agent_name: str,
        role: str,
        cfg: Dict[str, Any],
    ):
        ai_cfg = get_ai_config()
        model = self._resolve_model_alias(cfg.get("model"))
        explicit_provider = (cfg.get("provider") or "").strip().lower() or None
        model_provider = None
        if model:
            model_provider = ai_cfg.get_model_provider(model)
            if isinstance(model_provider, str):
                model_provider = model_provider.strip().lower() or None
            else:
                model_provider = None

        if explicit_provider and model_provider and explicit_provider != model_provider:
            raise ValueError(
                f"LLM policy provider/model mismatch for agent={agent_name} role={role}: "
                f"provider={explicit_provider} model={model} model_provider={model_provider}"
            )

        resolved_provider_name = explicit_provider or model_provider
        if not resolved_provider_name:
            raise ValueError(
                f"LLM policy missing provider resolution for agent={agent_name} role={role}: "
                f"model={model!r}"
            )

        prov_enum = resolve_llm_provider(resolved_provider_name)
        if prov_enum is None:
            raise ValueError(
                f"Unsupported LLM provider '{resolved_provider_name}' for agent={agent_name} role={role}; "
                f"supported={get_supported_llm_provider_names()}"
            )
        return prov_enum, model, resolved_provider_name

    def build_llms_for_agent(self, agent_name: str) -> Dict[str, RoleLLM]:
        pol = self.get_policy_for_agent(agent_name)
        handles: Dict[str, RoleLLM] = {}
        # roles: default/observe/plan/act
        for role in ["default", "observe", "plan", "act"]:
            cfg = pol.get(role) if role != "default" else pol.get("default") or pol
            if not cfg:
                continue
            try:
                route = self.resolve_route_for_agent(agent_name, role)
            except ValueError:
                if role == "default":
                    raise
                continue
            service = get_llm_service(route["provider_enum"])
            handles[role] = RoleLLM(
                service,
                route["model"],
                provider_name=route["provider_name"],
            )
        if "default" not in handles and handles:
            # pick any as default
            some = next(iter(handles.values()))
            handles["default"] = some
        return handles

    def resolve_route_for_agent(self, agent_name: str, role: str = "default") -> Dict[str, Any]:
        pol = self.get_policy_for_agent(agent_name)
        cfg = pol.get(role) if role != "default" else pol.get("default") or pol
        if not cfg and role != "default":
            cfg = pol.get("default") or pol
        if not cfg:
            raise ValueError(f"No LLM route configured for agent={agent_name} role={role}")
        prov_enum, model, provider_name = self._resolve_role_route(
            agent_name=agent_name,
            role=role,
            cfg=cfg,
        )
        return {
            "provider_enum": prov_enum,
            "provider_name": provider_name,
            "model": model,
        }
