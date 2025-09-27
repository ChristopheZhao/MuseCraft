"""Reusable prompt sanitation utilities to avoid AIGC provider rejections."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ...core.config import settings


logger = logging.getLogger("prompt_safety")


def _get_project_root() -> Path:
    candidate = getattr(settings, "PROJECT_ROOT", None) or getattr(settings, "BASE_DIR", None)
    if candidate:
        try:
            return Path(candidate).resolve()
        except Exception:
            pass
    # backend/app/services/prompt_safety -> parents[4] ≈ repo root
    return Path(__file__).resolve().parents[4]


@dataclass
class SanitizedPrompt:
    """Result of prompt sanitation."""

    text: str
    changed: bool
    matches: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@lru_cache(maxsize=1)
def _load_rules() -> List[Dict[str, Any]]:
    """Load replacement rules from configuration."""

    config_path = getattr(settings, "PROMPT_SAFETY_RULE_PATH", "backend/config/prompt_safety_rules.yaml")
    path = Path(config_path)
    if not path.is_absolute():
        path = _get_project_root().joinpath(path)

    if not path.exists():
        logger.warning("Prompt safety rule file not found: %s", path)
        return []

    try:
        import yaml

        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        rules = data.get("rules", [])
        sanitized_rules: List[Dict[str, Any]] = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            pattern = rule.get("pattern")
            replacement = rule.get("replacement")
            if not pattern or replacement is None:
                continue
            flags = rule.get("flags", 0)
            if isinstance(flags, list):
                # Support e.g. ["IGNORECASE"]
                flag_value = 0
                for flag_name in flags:
                    if hasattr(re, flag_name):
                        flag_value |= getattr(re, flag_name)
                flags = flag_value
            elif isinstance(flags, str):
                flag_value = 0
                for part in flags.split("|"):
                    part = part.strip().upper()
                    if hasattr(re, part):
                        flag_value |= getattr(re, part)
                flags = flag_value
            elif not isinstance(flags, int):
                flags = 0

            sanitized_rules.append(
                {
                    "pattern": pattern,
                    "replacement": replacement,
                    "regex": re.compile(pattern, flags),
                    "category": rule.get("category", "general"),
                    "note": rule.get("note", ""),
                }
            )
        return sanitized_rules
    except Exception as exc:
        logger.error("Failed to load prompt safety rules: %s", exc)
        return []


def sanitize_prompt(prompt: str, context: Optional[Dict[str, Any]] = None) -> SanitizedPrompt:
    """Apply configured safety rules to a prompt string."""

    context = context or {}
    if not prompt:
        return SanitizedPrompt(text=prompt, changed=False, matches=[], metadata={"context": context})

    rules = _load_rules()
    sanitized_text = prompt
    matches: List[Dict[str, Any]] = []

    for rule in rules:
        regex = rule["regex"]
        match_iter = list(regex.finditer(sanitized_text))
        if not match_iter:
            continue
        sanitized_text = regex.sub(rule["replacement"], sanitized_text)
        matches.extend(
            {
                "matched": m.group(0),
                "start": m.start(),
                "end": m.end(),
                "category": rule.get("category"),
                "replacement": rule.get("replacement"),
                "note": rule.get("note"),
            }
            for m in match_iter
        )

    # Avoid returning an empty string after aggressive replacements
    sanitized_text = sanitized_text.strip()
    if not sanitized_text:
        sanitized_text = prompt
        matches.append(
            {
                "matched": "__sanitizer_empty__",
                "category": "fallback",
                "note": "Sanitizer produced empty prompt; reverted to original",
            }
        )

    changed = sanitized_text != prompt
    metadata = {
        "context": context,
        "match_count": len(matches),
    }

    if changed:
        logger.debug(
            "Prompt sanitized (%s matches): %s",
            len(matches),
            json.dumps(matches, ensure_ascii=False)[:400],
        )

    return SanitizedPrompt(text=sanitized_text, changed=changed, matches=matches, metadata=metadata)


# ---------------------------------------------------------------------------
# Advisory component
# ---------------------------------------------------------------------------


@dataclass
class SafetyContext:
    """Structured prompt metadata for safety guidance."""

    modality: str
    provider: Optional[str] = None
    language: str = "zh"
    audience: str = "general"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SafetyAdvice:
    """Safety instructions to be applied around a prompt or LLM request."""

    system_instructions: List[str] = field(default_factory=list)
    prompt_prefix: Optional[str] = None
    prompt_suffix: Optional[str] = None
    hints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        return bool(
            self.system_instructions
            or (self.prompt_prefix and self.prompt_prefix.strip())
            or (self.prompt_suffix and self.prompt_suffix.strip())
        )

    def compose_system_prompt(self, base: Optional[str] = None) -> Optional[str]:
        """Merge advisory system instructions with an existing base message."""

        parts: List[str] = []
        instructions = [instr.strip() for instr in self.system_instructions if instr and instr.strip()]
        if instructions:
            parts.append("\n".join(instructions))
        if base and base.strip():
            parts.append(base.strip())
        if not parts:
            return None
        return "\n\n".join(parts).strip()

    def apply_to_prompt(self, prompt: str) -> str:
        """Apply optional prefix/suffix to a prompt without losing original content."""

        segments: List[str] = []
        if self.prompt_prefix and self.prompt_prefix.strip():
            segments.append(self.prompt_prefix.strip())
        if prompt and str(prompt).strip():
            segments.append(str(prompt).strip())
        if self.prompt_suffix and self.prompt_suffix.strip():
            segments.append(self.prompt_suffix.strip())
        return " ".join(segments).strip()


def _ensure_list(value: Optional[Sequence[Any] | Any]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value if item is not None and str(item).strip()]
    return [str(value)]


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


@lru_cache(maxsize=1)
def _load_advisor_config() -> Dict[str, Any]:
    """Load advisor configuration from YAML."""

    config_path = getattr(settings, "PROMPT_SAFETY_CONFIG_PATH", "backend/config/prompt_safety.yaml")
    path = Path(config_path)
    if not path.is_absolute():
        path = _get_project_root().joinpath(path)

    if not path.exists():
        logger.warning("Prompt safety advisor config not found: %s", path)
        return {}

    try:
        import yaml

        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            logger.warning("Prompt safety advisor config is not a dict: %s", type(data))
            return {}
        return data
    except Exception as exc:
        logger.error("Failed to load prompt safety advisor config: %s", exc)
        return {}


class PromptSafetyAdvisor:
    """Provide reusable prompt safety guidance for AIGC toolchains."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config if config is not None else _load_advisor_config()

    def reload(self) -> None:
        """Reload configuration from disk."""

        _load_advisor_config.cache_clear()
        self._config = _load_advisor_config()

    def get_advice(self, context: SafetyContext | Dict[str, Any], prompt: Optional[str] = None) -> SafetyAdvice:
        if isinstance(context, dict):
            context = SafetyContext(**context)

        config = self._config or {}
        layers: List[tuple[Dict[str, Any], str]] = []

        def add_layer(layer: Optional[Dict[str, Any]], source: str) -> None:
            if not layer or not isinstance(layer, dict):
                return
            enabled = layer.get("enabled", True)
            if isinstance(enabled, bool) and not enabled:
                return
            layers.append((layer, source))

        add_layer(config.get("defaults"), "defaults")

        modality_cfg = (config.get("modalities") or {}).get(context.modality)
        add_layer(modality_cfg, f"modalities.{context.modality}")

        provider_cfg = (config.get("providers") or {}).get(context.provider)
        add_layer(provider_cfg, f"providers.{context.provider}")
        if provider_cfg:
            provider_modality = (provider_cfg.get("modalities") or {}).get(context.modality)
            add_layer(provider_modality, f"providers.{context.provider}.{context.modality}")

        language_cfg = (config.get("languages") or {}).get(context.language)
        add_layer(language_cfg, f"languages.{context.language}")
        if language_cfg:
            lang_modality = (language_cfg.get("modalities") or {}).get(context.modality)
            add_layer(lang_modality, f"languages.{context.language}.{context.modality}")

        tags_cfg = config.get("tags") or {}
        for tag in context.tags or []:
            add_layer(tags_cfg.get(tag), f"tags.{tag}")

        system_msgs: List[str] = []
        prefix_parts: List[str] = []
        suffix_parts: List[str] = []
        hints: List[str] = []
        applied: List[str] = []

        for layer, source in layers:
            msgs = _ensure_list(layer.get("system_instructions"))
            if msgs:
                system_msgs.extend(msgs)
            prefix = layer.get("prompt_prefix")
            if isinstance(prefix, str) and prefix.strip():
                prefix_parts.append(prefix.strip())
            suffix = layer.get("prompt_suffix")
            if isinstance(suffix, str) and suffix.strip():
                suffix_parts.append(suffix.strip())
            hint_values = _ensure_list(layer.get("hints"))
            if hint_values:
                hints.extend(hint_values)
            applied.append(source)

        system_msgs = _dedupe_preserve_order(system_msgs)
        prefix_str = " ".join(_dedupe_preserve_order(prefix_parts)) or None
        suffix_str = " ".join(_dedupe_preserve_order(suffix_parts)) or None
        hints = _dedupe_preserve_order(hints)

        metadata = {
            "context": {
                "modality": context.modality,
                "provider": context.provider,
                "language": context.language,
                "audience": context.audience,
                "tags": context.tags,
                "metadata": context.metadata,
            },
            "applied_layers": applied,
        }

        advice = SafetyAdvice(
            system_instructions=system_msgs,
            prompt_prefix=prefix_str,
            prompt_suffix=suffix_str,
            hints=hints,
            metadata=metadata,
        )

        if advice.is_active():
            logger.debug(
                "Prompt safety advice applied: layers=%s"
                " prefix=%s suffix=%s",
                applied,
                prefix_str,
                suffix_str,
            )

        return advice


_advisor_instance: Optional[PromptSafetyAdvisor] = None


def get_prompt_safety_advisor() -> PromptSafetyAdvisor:
    """Obtain a shared PromptSafetyAdvisor instance."""

    global _advisor_instance
    if _advisor_instance is None:
        _advisor_instance = PromptSafetyAdvisor()
    return _advisor_instance


def apply_prompt_safety(prompt: str, context: SafetyContext | Dict[str, Any]) -> tuple[str, SafetyAdvice]:
    """Convenience helper returning the adjusted prompt and the advice metadata."""

    advisor = get_prompt_safety_advisor()
    advice = advisor.get_advice(context, prompt)
    if advice.is_active():
        safe_prompt = advice.apply_to_prompt(prompt)
    else:
        safe_prompt = prompt
    return safe_prompt, advice


__all__ = [
    "sanitize_prompt",
    "SanitizedPrompt",
    "PromptSafetyAdvisor",
    "SafetyAdvice",
    "SafetyContext",
    "get_prompt_safety_advisor",
    "apply_prompt_safety",
]
