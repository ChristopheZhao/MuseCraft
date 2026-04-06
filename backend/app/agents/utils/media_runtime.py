from __future__ import annotations

from pathlib import Path
from typing import Tuple

from ...core.config import settings


def _static_roots() -> Tuple[Tuple[str, str], ...]:
    return (
        ("/files/outputs", settings.FINAL_OUTPUT_ROOT),
        ("/files/generated", settings.GENERATED_PATH),
        ("/files/uploads", settings.UPLOAD_PATH),
        ("/files/temp", settings.TEMP_PATH),
    )


def build_local_public_url(local_path: str) -> str:
    if not local_path:
        return ""

    try:
        resolved = Path(local_path).resolve()
    except Exception:
        return ""

    for public_prefix, root in _static_roots():
        try:
            root_path = Path(root).resolve()
            if resolved == root_path or root_path in resolved.parents:
                relative = resolved.relative_to(root_path)
                return f"{public_prefix}/{relative.as_posix()}"
        except Exception:
            continue

    return ""


def resolve_local_public_path(public_url: str) -> str:
    if not public_url:
        return ""

    candidate = str(public_url).strip()
    if not candidate:
        return ""
    if candidate.startswith("file://"):
        return candidate.replace("file://", "", 1)

    for public_prefix, root in _static_roots():
        if not candidate.startswith(public_prefix):
            continue
        relative = candidate[len(public_prefix) :].lstrip("/")
        resolved = (Path(root) / relative).resolve()
        return str(resolved)

    return ""
