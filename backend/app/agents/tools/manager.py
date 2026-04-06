"""
Tool Manager
------------
Central coordination layer over ToolRegistry and Agent tool allocation.

Responsibilities (design-only, minimal implementation):
- Register tools (delegates to ToolRegistry) with optional metadata checks.
- Allocate tools for an Agent (merge default allocation + central policy + tool self-visibility).
- Build FC (function call) schema and fc_map for LLM planning.
- Validate planned tool_calls (warn/critical classification, non-intrusive by default).
- Apply parameter policy (only fill when missing + template present; no forced overrides).
- Normalize artifacts (supplier-agnostic fields for WM write-back).

Notes:
- Does NOT execute tools. Execution remains in BaseAgent.execute_tool_calls.
- YAML policy loading is optional; absence or missing parser yields empty policy with a log note.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import os

from ..tools.tool_registry import get_tool_registry
from ..tools.agent_tool_allocation import get_agent_tools
from ..tools.base_tool import BaseTool
from ...models import AgentType


# ---------- Data contracts ----------

@dataclass
class Exposure:
    expose: bool = True
    allowed_actions: List[str] = field(default_factory=list)


@dataclass
class AllocationPlan:
    tools: Dict[str, BaseTool]
    exposure: Dict[str, Exposure]
    fc_map: Dict[str, Tuple[str, str]]  # function_name -> (tool_name, action)
    diag: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationIssue:
    level: str  # 'warn' | 'error' | 'critical'
    call_index: int
    reason: str
    hint: Optional[str] = None


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


class ToolManager:
    """Unified manager for tool registration, allocation, schema, validation and artifact normalization."""

    def __init__(self, policy_path: Optional[str] = None) -> None:
        # Default policy path inside repo: backend/app/agents/config/tool_policies.yaml
        if policy_path is None:
            base_dir = os.path.dirname(os.path.dirname(__file__))  # .../agents/tools -> .../agents
            policy_path = os.path.join(base_dir, "config", "tool_policies.yaml")
        self._policy_path = policy_path
        self._policy_cache: Dict[str, Any] = {}
        self._load_policy_safely()

    # ---------- Registration ----------
    def register(self, tool_class, name: Optional[str] = None, config: Optional[Dict[str, Any]] = None,
                 is_singleton: bool = True, auto_load: bool = True, aliases: Optional[List[str]] = None) -> str:
        """Delegate to ToolRegistry for registration. Keep a single entry point for tools."""
        registry = get_tool_registry()
        return registry.register_tool(
            tool_class=tool_class,
            name=name,
            config=(config or {}),
            is_singleton=is_singleton,
            auto_load=auto_load,
            aliases=aliases,
        )

    # ---------- Allocation & Exposure ----------
    def allocate(self, agent_type: AgentType, requested: Optional[List[str]] = None,
                 agent_name: Optional[str] = None) -> AllocationPlan:
        """
        Allocate tools for an agent by merging:
        - default allocation (AgentToolAllocator)
        - requested overrides (optional)
        - central policy (per-agent whitelist)
        - tool self-visibility (get_fc_visibility)
        """
        registry = get_tool_registry()
        desired = list(requested or get_agent_tools(agent_type) or [])

        tools: Dict[str, BaseTool] = {}
        exposure: Dict[str, Exposure] = {}
        diag: Dict[str, Any] = {"not_registered": [], "schema_missing": []}

        # Load agent policy
        pol = self._get_agent_policy(agent_name or agent_type.value)

        for tool_name in desired:
            try:
                inst = registry.get_tool(tool_name)
                tools[tool_name] = inst
            except Exception as e:
                diag["not_registered"].append(f"{tool_name}: {e}")
                continue
            # Tool self-visibility
            try:
                vis = inst.get_fc_visibility() if hasattr(inst, "get_fc_visibility") else {"expose": True}
            except Exception:
                vis = {"expose": True}
            expose = bool(vis.get("expose", True))
            allowed = list(vis.get("allowed_actions", []) or [])

            # Merge central policy (per agent)
            pol_t = self._get_tool_policy(pol, tool_name)
            if pol_t:
                if "expose" in pol_t:
                    expose = bool(pol_t["expose"])
                if isinstance(pol_t.get("allowed_actions"), list) and pol_t["allowed_actions"]:
                    allowed = list(pol_t["allowed_actions"])  # narrow down to whitelist

            exposure[tool_name] = Exposure(expose=expose, allowed_actions=allowed)

        # Build fc_map
        fc_map: Dict[str, Tuple[str, str]] = {}
        for tname, tool in tools.items():
            exp = exposure.get(tname, Exposure(True, []))
            if not exp.expose:
                continue
            try:
                actions = tool.get_available_actions() or []
            except Exception:
                actions = []
            if exp.allowed_actions:
                actions = [a for a in actions if a in exp.allowed_actions]
            for act in actions:
                fc_map[f"{tname}.{act}"] = (tname, act)

        return AllocationPlan(tools=tools, exposure=exposure, fc_map=fc_map, diag=diag)

    # ---------- FC Schema ----------
    def build_fc_schema(self, allocated_tools: Dict[str, BaseTool], exposure: Dict[str, Exposure]) -> List[Dict[str, Any]]:
        """Build OpenAI/Anthropic-compatible function schemas from allocated tools and exposure policy."""
        schemas: List[Dict[str, Any]] = []
        for tname, tool in allocated_tools.items():
            exp = exposure.get(tname, Exposure(True, []))
            if not exp.expose:
                continue
            try:
                actions = tool.get_available_actions() or []
            except Exception:
                actions = []
            if exp.allowed_actions:
                actions = [a for a in actions if a in exp.allowed_actions]
            for act in actions:
                try:
                    action_schema = tool.get_action_schema(act)
                except Exception:
                    action_schema = None
                if not isinstance(action_schema, dict) or not action_schema:
                    continue
                # Prefer action-level description from schema if provided; fallback to tool description + action
                try:
                    tool_desc = tool.get_metadata().description
                except Exception:
                    tool_desc = ""
                action_desc = action_schema.get("description") if isinstance(action_schema, dict) else None
                parameters_schema = self._build_parameters_schema(action_schema)
                final_desc = action_desc or (f"{tool_desc} - {act}" if tool_desc else act)
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": f"{tname}.{act}",
                        "description": final_desc,
                        "parameters": parameters_schema,
                    },
                })
        return schemas

    def _build_parameters_schema(self, action_schema: Any) -> Dict[str, Any]:
        """Extract JSON Schema keys for parameters, removing action-level metadata."""
        if not isinstance(action_schema, dict):
            return {}

        allowed_top_keys = {
            "type",
            "properties",
            "required",
            "items",
            "enum",
            "anyOf",
            "oneOf",
            "allOf",
            "not",
            "definitions",
            "$defs",
            "dependencies",
            "dependentRequired",
            "dependentSchemas",
            "patternProperties",
            "additionalProperties",
            "contains",
            "const",
            "default",
            "examples",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minItems",
            "maxItems",
            "minLength",
            "maxLength",
            "pattern",
            "format",
            "title",
        }

        params: Dict[str, Any] = {}
        for key in allowed_top_keys:
            if key in action_schema:
                params[key] = self._strip_extension_fields(action_schema[key])

        return params

    def _strip_extension_fields(self, schema: Any) -> Any:
        """Recursively remove extension fields (x-*) while preserving JSON Schema content."""
        if isinstance(schema, dict):
            cleaned: Dict[str, Any] = {}
            for key, value in schema.items():
                if key.startswith("x-"):
                    continue
                cleaned[key] = self._strip_extension_fields(value)
            return cleaned
        if isinstance(schema, list):
            return [self._strip_extension_fields(item) for item in schema]
        return schema

    # ---------- Validation (warn-first) ----------
    def validate_tool_calls(self, tool_calls: List[Dict[str, Any]], fc_schema: List[Dict[str, Any]]) -> ValidationReport:
        """Lightweight validation: unknown function names, basic args type presence. Non-intrusive by default."""
        valid_functions = {
            (t or {}).get("function", {}).get("name")
            for t in (fc_schema or [])
            if isinstance(t, dict)
        }
        issues: List[ValidationIssue] = []
        for idx, call in enumerate(tool_calls or []):
            fn = ((call or {}).get("function") or {}).get("name")
            if not fn or fn not in valid_functions:
                issues.append(ValidationIssue(level="critical", call_index=idx, reason=f"unknown function: {fn}", hint="Check exposure/whitelist"))
        summary = {"total": len(tool_calls or []), "issues": len(issues)}
        return ValidationReport(issues=issues, summary=summary)

    # ---------- Parameter policy (inject only when templated and missing) ----------
    def apply_param_policy(self, function_name: str, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Only inject when parameter is missing and a policy template exists.
        - If destination_key present: verify prefix if configured; do not rewrite silently.
        - If required fields missing (e.g., wf_id/scene_number for per-scene), raise error.
        - No forced overrides of LLM decisions.
        """
        tool_name, action = (function_name.split(".", 1) + [None])[:2] if "." in function_name else (function_name, None)
        agent_name = context.get("agent_name") or context.get("agent_type")
        pol = self._get_agent_policy(str(agent_name or ""))
        pol_t = self._get_tool_policy(pol, tool_name)
        if not pol_t:
            return args

        requires = list(pol_t.get("requires", []) or [])
        path_cfg = pol_t.get("path", {}) if isinstance(pol_t.get("path"), dict) else {}
        prefix = path_cfg.get("prefix")
        template = path_cfg.get("template")

        # Required fields enforcement
        # wf_id must come from context
        if "wf_id" in requires and not context.get("wf_id"):
            raise ValueError("Parameter policy requires wf_id in context")
        # per-scene requires scene_number in args
        if "scene_number" in requires and (args.get("scene_number") is None):
            raise ValueError("Per-scene call missing scene_number (plan incomplete)")
        if "execution.id" in requires and not context.get("execution.id"):
            raise ValueError("Parameter policy requires execution.id in context")

        new_args = dict(args or {})

        # If provided, enforce prefix on destination_key
        dest_key = new_args.get("destination_key")
        if isinstance(dest_key, str) and dest_key and isinstance(prefix, str) and prefix:
            if not dest_key.startswith(prefix):
                raise ValueError("destination_key outside allowed prefix")

        # Only inject when missing and template exists
        if (not dest_key) and template:
            # prepare formatting bag
            bag = {
                "wf_id": context.get("wf_id"),
                "scene_number": new_args.get("scene_number"),
                "execution.id": context.get("execution.id"),
            }
            # Fail if required placeholders are unavailable (no forced overrides)
            if ("{scene_number}" in template) and (bag.get("scene_number") is None):
                raise ValueError("destination_key template requires scene_number")
            if ("{execution.id}" in template) and (bag.get("execution.id") is None):
                raise ValueError("destination_key template requires execution.id")
            if ("{wf_id}" in template) and (bag.get("wf_id") is None):
                raise ValueError("destination_key template requires wf_id")
            # Render
            rendered = template.replace("{wf_id}", str(bag.get("wf_id") or ""))
            if bag.get("scene_number") is not None:
                rendered = rendered.replace("{scene_number}", str(int(bag["scene_number"])) )
            if bag.get("execution.id") is not None:
                rendered = rendered.replace("{execution.id}", str(bag["execution.id"]))
            new_args["destination_key"] = rendered

        return new_args

    # ---------- Artifact normalization ----------
    def normalize_artifact(self, tool_result: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return a supplier-agnostic artifact snapshot for WM write-back."""
        payload = tool_result.result if hasattr(tool_result, "result") else tool_result
        data = payload if isinstance(payload, dict) else {}

        # file_path preference (common keys)
        file_path = (
            data.get("file_path")
            or data.get("output_path")
            or data.get("output_file")
            or data.get("local_path")
        )

        # URLs
        image_url = data.get("image_url")
        video_url = data.get("video_url")
        audio_url = data.get("audio_url")

        # Duration
        duration = (
            data.get("duration_sec")
            or data.get("duration")
            or data.get("audio_duration")
            or data.get("video_duration")
        )
        try:
            duration = float(duration) if duration is not None else None
        except Exception:
            duration = None

        # Prompt / text
        prompt_text = (
            data.get("prompt_text")
            or data.get("prompt")
            or data.get("description")
            or data.get("text")
        )

        # Scene number from args (do not coerce from payload to avoid supplier coupling)
        scene_number = args.get("scene_number") if isinstance(args, dict) else None
        try:
            if scene_number is not None:
                scene_number = int(scene_number)
        except Exception:
            pass

        return {
            "scene_number": scene_number,
            "file_path": file_path,
            "image_url": image_url,
            "video_url": video_url,
            "audio_url": audio_url,
            "duration_sec": duration,
            "prompt_text": prompt_text,
        }

    # ---------- Policy loading ----------
    def _load_policy_safely(self) -> None:
        """Best-effort load YAML policy. If unavailable, fall back to empty policy."""
        path = self._policy_path
        if not path or not os.path.exists(path):
            self._policy_cache = {}
            return
        try:
            import yaml  # type: ignore
        except Exception:
            # YAML parser not available; ignore policy silently (non-intrusive for now)
            self._policy_cache = {}
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    self._policy_cache = data
                else:
                    self._policy_cache = {}
        except Exception:
            self._policy_cache = {}

    def _get_agent_policy(self, agent_key: str) -> Dict[str, Any]:
        agents = self._policy_cache.get("agents") if isinstance(self._policy_cache, dict) else None
        if isinstance(agents, dict):
            return agents.get(agent_key, {}) or {}
        return {}

    def _get_tool_policy(self, agent_policy: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        if not isinstance(agent_policy, dict):
            return {}
        pol = agent_policy.get(tool_name)
        return pol if isinstance(pol, dict) else {}


# Convenience accessor (optional singleton)
_tool_manager_singleton: Optional[ToolManager] = None


def get_tool_manager() -> ToolManager:
    global _tool_manager_singleton
    if _tool_manager_singleton is None:
        _tool_manager_singleton = ToolManager()
    return _tool_manager_singleton
