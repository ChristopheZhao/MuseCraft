import os
import yaml
from typing import Dict, Any, Optional

from ..tools.ai_services.service_interfaces import get_llm_service, ServiceProvider


class RoleLLM:
    """A thin wrapper binding a default model to an LLM service for a specific role."""

    def __init__(self, service, default_model: Optional[str] = None):
        self._service = service
        self._model = default_model

    async def chat_completion(self, messages, **kwargs):
        if not kwargs.get("model") and self._model:
            kwargs["model"] = self._model
        return await self._service.chat_completion(messages=messages, **kwargs)

    async def function_call(self, messages, tools, **kwargs):
        if not kwargs.get("model") and self._model:
            kwargs["model"] = self._model
        return await self._service.function_call(messages=messages, tools=tools, **kwargs)


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

    def build_llms_for_agent(self, agent_name: str) -> Dict[str, RoleLLM]:
        pol = self.get_policy_for_agent(agent_name)
        handles: Dict[str, RoleLLM] = {}
        # roles: default/observe/plan/act
        for role in ["default", "observe", "plan", "act"]:
            cfg = pol.get(role) if role != "default" else pol.get("default") or pol
            if not cfg:
                continue
            provider = (cfg.get("provider") or "zhipu").lower()
            model = cfg.get("model")
            # Extendable: map provider string to enum
            prov_enum = ServiceProvider.ZHIPU if provider == "zhipu" else ServiceProvider.ZHIPU
            service = get_llm_service(prov_enum)
            handles[role] = RoleLLM(service, model)
        if "default" not in handles and handles:
            # pick any as default
            some = next(iter(handles.values()))
            handles["default"] = some
        return handles

