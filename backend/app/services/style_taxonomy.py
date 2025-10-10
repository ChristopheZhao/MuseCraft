"""Style taxonomy loader and matcher for visual style propagation."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from ..core.config import settings


def _resolve_taxonomy_path() -> Path:
    configured = getattr(settings, "STYLE_TAXONOMY_PATH", "backend/config/style/style_taxonomy.yaml")
    path = Path(configured)
    if path.is_absolute():
        return path
    base_dir = getattr(settings, "BASE_DIR", None)
    if base_dir:
        return Path(base_dir).joinpath(path).resolve()
    # fallback: project root inferred from this file
    return Path(__file__).resolve().parents[3].joinpath(path).resolve()


@lru_cache(maxsize=1)
def get_style_taxonomy() -> Dict[str, Any]:
    taxonomy_path = _resolve_taxonomy_path()
    if not taxonomy_path.exists():
        return {"families": []}
    try:
        with taxonomy_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:
        data = {}
    families = data.get("families") if isinstance(data, dict) else None
    if not isinstance(families, list):
        return {"families": []}
    return data


def _split_to_tokens(raw: str) -> List[str]:
    if not raw:
        return []
    cleaned = str(raw).replace('"', '').replace("'", "")
    pieces = re.split(r"[\s/|、，\-]+", cleaned)
    return [p.strip().lower() for p in pieces if p and p.strip()]


def _token_variants(token: str) -> Iterable[str]:
    if not token:
        return []
    lowered = token.strip().lower()
    if not lowered:
        return []
    yield lowered
    collapsed = re.sub(r"['\"“”]", "", lowered)
    if collapsed and collapsed != lowered:
        yield collapsed
    for splitter in ["-", "_", ":"]:
        if splitter in collapsed:
            for part in collapsed.split(splitter):
                part = part.strip()
                if len(part) >= 2:
                    yield part
    for part in collapsed.split():
        part = part.strip()
        if len(part) >= 2:
            yield part


def _collect_tokens(entry: Dict[str, Any]) -> List[str]:
    tokens: List[str] = []
    for key in ("label", "key"):
        tokens.extend(_split_to_tokens(entry.get(key, "")))
    for token in entry.get("positive_tokens", []) or []:
        tokens.extend(list(_token_variants(token)))
    for token in entry.get("negative_tokens", []) or []:
        tokens.extend(list(_token_variants(token)))
    tokens = [t for t in tokens if t]
    # remove duplicates preserving order
    seen = set()
    result = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _score_substyle(text: str, substyle: Dict[str, Any]) -> int:
    score = 0
    for token in _collect_tokens(substyle):
        if token in text:
            score += 2
    label_tokens = _split_to_tokens(substyle.get("label", ""))
    for token in label_tokens:
        if token in text:
            score += 2
    key = str(substyle.get("key", "")).strip().lower()
    if key and key in text:
        score += 1
    return score


def match_style_taxonomy(design: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best-effort match of intelligent_style_design to taxonomy entry."""

    if not isinstance(design, dict) or not design:
        return None

    style_taxonomy = get_style_taxonomy()
    families = style_taxonomy.get("families") or []
    if not families:
        return None

    style_fragments = []
    for key in [
        "style_name",
        "style_description",
        "visual_approach",
        "narrative_style",
        "production_taste",
        "emotional_tone",
    ]:
        val = design.get(key)
        if isinstance(val, str) and val.strip():
            style_fragments.append(val.strip())
    composite_text = " ".join(style_fragments).lower()
    if not composite_text:
        return None

    best: Tuple[int, Dict[str, Any], Dict[str, Any]] | None = None
    for family in families:
        substyles = family.get("substyles") or []
        for sub in substyles:
            score = _score_substyle(composite_text, sub)
            if score <= 0:
                continue
            if not best or score > best[0]:
                best = (score, family, sub)

    # fallback: check family key presence if no token match
    if best is None:
        for family in families:
            key = str(family.get("key", "")).strip().lower()
            label = str(family.get("label", "")).strip().lower()
            if not key and not label:
                continue
            family_tokens = _collect_tokens({"label": family.get("label"), "key": family.get("key")})
            matched = False
            for token in family_tokens:
                if token in composite_text:
                    matched = True
                    break
            if key and key in composite_text:
                matched = True
            if label and label in composite_text:
                matched = True
            if matched:
                substyles = family.get("substyles") or []
                if substyles:
                    best = (1, family, substyles[0])
                    break

    if best is None:
        return None

    _, family, substyle = best
    result = {
        "family_key": family.get("key"),
        "family_label": family.get("label"),
        "substyle_key": substyle.get("key"),
        "substyle_label": substyle.get("label"),
        "positive_tokens": list(substyle.get("positive_tokens") or []),
        "negative_tokens": list(substyle.get("negative_tokens") or []),
        "description": substyle.get("description") or family.get("description"),
        "score": best[0],
    }
    return result


def summarize_style_taxonomy(
    *,
    max_families: int = 8,
    max_substyles_per_family: int = 6,
    max_tokens_per_substyle: int = 5,
) -> str:
    """Produce a compact, human-readable summary of the taxonomy for prompting."""

    taxonomy = get_style_taxonomy()
    families = taxonomy.get("families") or []
    if not families:
        return ""

    lines: List[str] = ["可选风格家族与子风格参考："]
    for family in families[:max_families]:
        family_label = family.get("label") or family.get("key") or "未命名家族"
        family_key = family.get("key") or ""
        lines.append(f"- {family_label} ({family_key})")
        for substyle in (family.get("substyles") or [])[:max_substyles_per_family]:
            sub_label = substyle.get("label") or substyle.get("key") or "子风格"
            tokens = substyle.get("positive_tokens") or []
            token_preview = ", ".join(str(t) for t in tokens[:max_tokens_per_substyle])
            if token_preview:
                lines.append(f"  - {sub_label}: {token_preview}")
            else:
                lines.append(f"  - {sub_label}")
    return "\n".join(lines)
