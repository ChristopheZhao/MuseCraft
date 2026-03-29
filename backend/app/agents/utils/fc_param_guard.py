"""
FC Parameter Guard

Non-intrusive validation for tool_calls returned by LLM function call.
Goals:
- Do not modify tool_calls (no coercion/clip here).
- Do not couple providers or hardcode constants in code.
- Read policies from config (fc_param_policies.yaml) and provider capabilities dynamically.
- Emit diagnostics and reject contract-invalid calls when policy requires it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..tools.ai_services.service_interfaces import get_vlm_capabilities


class FCParamPolicyViolation(ValueError):
    """Raised when a tool-call parameter violates an enforced FC policy."""


class FCParamGuard:
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger("fc_param_guard")
        self._policies = None

    def _load_policies(self) -> Dict[str, Any]:
        if self._policies is not None:
            return self._policies
        # Search config path (app/config/prompts sibling: app/config/mas)
        here = Path(__file__).resolve()
        cfg_root = here.parent.parent.parent / "config" / "mas"
        cfg_file = cfg_root / "fc_param_policies.yaml"
        data: Dict[str, Any] = {}
        try:
            if cfg_file.exists():
                import yaml
                with cfg_file.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
        except Exception as e:
            self.logger.debug(f"FCParamGuard: failed to load policies: {e}")
            data = {}
        # Minimal default (warn-only), keeps behavior unchanged
        if not data:
            data = {
                "per_agent": {
                    "video_generator": {
                        "functions": [
                            {
                                "name": "video_generation.generate_with_continuity",
                                "params": {
                                    "duration": {
                                        "allowed_values": "${provider.duration_capabilities}",
                                        "on_violation": "warn",
                                    },
                                    "image_url": {
                                        "allow_schemes": ["http", "https"],
                                        "on_violation": "warn",
                                    },
                                    "previous_video_url": {
                                        "allow_schemes": ["http", "https"],
                                        "on_violation": "warn",
                                    },
                                    "continuity_frame": {
                                        "allow_schemes": ["http", "https"],
                                        "on_violation": "warn",
                                    },
                                },
                            }
                        ]
                    },
                    "image_generator": {
                        "functions": [
                            {
                                "name": "image_prompt_composer.generate",
                                "params": {
                                    "size": {
                                        "allowed_values": "${provider.image_size_inputs}",
                                        "on_violation": "reject",
                                    }
                                },
                            }
                        ]
                    },
                }
            }
        self._policies = data
        return data

    def _get_provider_caps(self, agent: Any) -> Dict[str, Any]:
        # Supplier-agnostic: use video_config_manager for video generator if available
        try:
            if hasattr(agent, "video_config") and agent.video_config is not None:
                cfg = agent.video_config.get_current_provider_config()
                return {
                    "provider": {
                        "duration_capabilities": list(getattr(cfg, "duration_capabilities", []) or []),
                        "model_name": getattr(cfg, "model_name", None),
                    }
                }
        except Exception:
            pass
        try:
            if getattr(agent, "agent_name", "") == "image_generator":
                caps = get_vlm_capabilities()
                size_cap = caps.size if caps else None
                return {
                    "provider": {
                        "image_size_options": list(size_cap.options or []) if size_cap else [],
                        "image_size_aliases": dict(size_cap.aliases or {}) if size_cap else {},
                        "image_size_inputs": size_cap.expand_enum() if size_cap else [],
                    }
                }
        except Exception:
            pass
        return {"provider": {"duration_capabilities": []}}

    def _resolve_tokens(self, value: Any, caps: Dict[str, Any]) -> Any:
        # Support string placeholder "${provider.duration_capabilities}"
        try:
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                key = value[2:-1]  # provider.duration_capabilities
                parts = key.split(".")
                cur: Any = caps
                for p in parts:
                    cur = cur.get(p) if isinstance(cur, dict) else None
                    if cur is None:
                        break
                return cur
        except Exception:
            return value
        return value

    def _apply_param_rules(self, agent: Any, fname: str, args_obj: Dict[str, Any], rules: Dict[str, Any], caps: Dict[str, Any]) -> None:
        params = rules.get("params", {}) if isinstance(rules, dict) else {}
        for p_name, p_rule in params.items():
            rule = p_rule or {}
            if not isinstance(rule, dict):
                continue
            val = args_obj.get(p_name)
            on_violation = str(rule.get("on_violation") or "warn").strip().lower()
            # allowed_values
            try:
                allowed = self._resolve_tokens(rule.get("allowed_values"), caps)
                if isinstance(allowed, list) and val is not None:
                    # Normalize numeric types where possible
                    vv = val
                    if isinstance(vv, float) and float(int(vv)) == vv:
                        vv = int(vv)
                    if vv not in allowed:
                        message = (
                            f"POLICY_VALIDATION function={fname} param={p_name} value={val} "
                            f"rule=allowed_values expected={allowed} severity={on_violation}"
                        )
                        if on_violation == "reject":
                            raise FCParamPolicyViolation(message)
                        self.logger.warning(message)
            except FCParamPolicyViolation:
                raise
            except Exception:
                pass
            # allow_schemes for URL-like params
            try:
                schemes = rule.get("allow_schemes")
                if isinstance(schemes, list) and val:
                    if isinstance(val, str):
                        ok = any(val.startswith(s + "://") for s in schemes)
                        # also allow raw http(s) forms without ://? No, strict
                        if not ok:
                            message = (
                                f"POLICY_VALIDATION function={fname} param={p_name} "
                                f"value_preview={str(val)[:80]} rule=allow_schemes expected={schemes} "
                                f"severity={on_violation}"
                            )
                            if on_violation == "reject":
                                raise FCParamPolicyViolation(message)
                            self.logger.warning(message)
            except FCParamPolicyViolation:
                raise
            except Exception:
                pass

        # 通用媒体类型一致性提示（启发式，warn-only，非侵入）：
        # - 若参数名暗示“video_url”而值看起来像图片URL，则警告
        # - 若参数名暗示“image_url”而值看起来像视频URL，则警告
        try:
            from urllib.parse import urlparse

            def _url_path(u: str) -> str:
                try:
                    return urlparse(u).path or u
                except Exception:
                    return u

            def _is_image_path(p: str) -> bool:
                lp = p.lower()
                return lp.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))

            def _is_video_path(p: str) -> bool:
                lp = p.lower()
                return lp.endswith((".mp4", ".mov", ".mkv", ".avi", ".webm"))

            for k, v in (args_obj or {}).items():
                if not isinstance(v, str):
                    continue
                # 仅处理明显是URL的字符串
                if not (v.startswith("http://") or v.startswith("https://")):
                    continue
                path = _url_path(v)
                name_l = str(k).lower()
                if ("video" in name_l and "url" in name_l) and _is_image_path(path) and not _is_video_path(path):
                    self.logger.warning(
                        f"POLICY_VALIDATION function={fname} param={k} looks_like=image_url rule=media_type_mismatch expected=video_url severity=warn"
                    )
                if ("image" in name_l and "url" in name_l) and _is_video_path(path) and not _is_image_path(path):
                    self.logger.warning(
                        f"POLICY_VALIDATION function={fname} param={k} looks_like=video_url rule=media_type_mismatch expected=image_url severity=warn"
                    )
        except Exception:
            pass

    def validate(self, agent: Any, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            pol = self._load_policies()
            per_agent = (pol.get("per_agent") or {}).get(getattr(agent, "agent_name", ""), {})
            functions = per_agent.get("functions", []) if isinstance(per_agent, dict) else []
            if not functions:
                return tool_calls

            # Build rules map
            rule_map: Dict[str, Dict[str, Any]] = {}
            for f in functions:
                if isinstance(f, dict) and f.get("name"):
                    rule_map[f["name"]] = f

            caps = self._get_provider_caps(agent)
            for call in tool_calls or []:
                try:
                    fname = (call.get("function", {}) or {}).get("name")
                    if not fname or fname not in rule_map:
                        continue
                    raw = (call.get("function", {}) or {}).get("arguments")
                    args_obj = json.loads(raw) if isinstance(raw, str) else (raw or {})
                    if not isinstance(args_obj, dict):
                        continue
                    self._apply_param_rules(agent, fname, args_obj, rule_map[fname], caps)
                except FCParamPolicyViolation:
                    raise
                except Exception:
                    continue
        except FCParamPolicyViolation:
            raise
        except Exception as e:
            self.logger.debug(f"FCParamGuard.validate skipped due to error: {e}")
        return tool_calls


_guard_singleton: Optional[FCParamGuard] = None


def get_fc_param_guard(logger: Optional[logging.Logger] = None) -> FCParamGuard:
    global _guard_singleton
    if _guard_singleton is None:
        _guard_singleton = FCParamGuard(logger)
    return _guard_singleton
