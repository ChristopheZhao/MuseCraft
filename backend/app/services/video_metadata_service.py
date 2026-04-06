from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_frame_rate(raw_value: Any) -> float:
    raw = str(raw_value or "").strip()
    if not raw:
        return 0.0
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        try:
            numerator_value = float(numerator)
            denominator_value = float(denominator)
            if denominator_value == 0:
                return 0.0
            return numerator_value / denominator_value
        except Exception:
            return 0.0
    return _safe_float(raw, 0.0)


def _canonical_video_format(format_names: str, local_path: str) -> str:
    tokens = [token.strip().lower() for token in str(format_names or "").split(",") if token.strip()]
    if "mp4" in tokens:
        return "mp4"
    if tokens:
        return tokens[0]
    return Path(local_path).suffix.lstrip(".").lower()


def normalize_video_metadata(metadata: Any) -> Dict[str, Any]:
    if not isinstance(metadata, dict) or not metadata:
        return {}

    normalized = dict(metadata)
    try:
        normalized["duration"] = float(normalized.get("duration") or 0.0)
    except Exception:
        normalized["duration"] = 0.0

    file_size = normalized.get("file_size")
    if file_size is not None:
        try:
            normalized["file_size"] = int(file_size)
        except Exception:
            normalized.pop("file_size", None)

    file_size_mb = normalized.get("file_size_mb")
    if file_size_mb is not None:
        try:
            normalized["file_size_mb"] = float(file_size_mb)
        except Exception:
            normalized.pop("file_size_mb", None)
    elif isinstance(normalized.get("file_size"), int):
        normalized["file_size_mb"] = round(normalized["file_size"] / (1024 * 1024), 4)

    format_value = str(normalized.get("format") or "").strip().lower()
    format_names = str(normalized.get("format_names") or "").strip().lower()
    if not format_value and format_names:
        normalized["format"] = (
            "mp4" if "mp4" in format_names.split(",") else format_names.split(",")[0].strip()
        )
    elif format_value:
        normalized["format"] = format_value

    return normalized


def merge_video_metadata(
    base_metadata: Any,
    overlay_metadata: Any,
    *,
    overwrite_non_empty: bool = False,
) -> Dict[str, Any]:
    merged = normalize_video_metadata(base_metadata)
    overlay = normalize_video_metadata(overlay_metadata)

    for key, value in overlay.items():
        current = merged.get(key)
        if overwrite_non_empty or current in (None, "", 0, 0.0, []):
            merged[key] = value
    return merged


def probe_local_video_metadata_sync(local_path: str) -> Dict[str, Any]:
    candidate = str(local_path or "").strip()
    if not candidate or not os.path.exists(candidate):
        return {}

    fallback_size = 0
    try:
        fallback_size = int(os.path.getsize(candidate))
    except Exception:
        fallback_size = 0

    command = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        candidate,
    ]

    try:
        probe = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if probe.returncode != 0:
            raise RuntimeError(f"ffprobe exited with code {probe.returncode}")
        payload = json.loads(probe.stdout or "{}")
    except Exception:
        if not fallback_size:
            return {}
        return {
            "file_size": fallback_size,
            "file_size_mb": round(fallback_size / (1024 * 1024), 4),
            "format": _canonical_video_format("", candidate),
        }

    format_info = payload.get("format") if isinstance(payload, dict) else {}
    streams = payload.get("streams") if isinstance(payload, dict) else []
    format_info = format_info if isinstance(format_info, dict) else {}
    streams = streams if isinstance(streams, list) else []

    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and str(stream.get("codec_type") or "").strip().lower() == "video"
        ),
        {},
    )
    audio_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and str(stream.get("codec_type") or "").strip().lower() == "audio"
        ),
        {},
    )

    width = int(video_stream.get("width") or 0) if isinstance(video_stream, dict) else 0
    height = int(video_stream.get("height") or 0) if isinstance(video_stream, dict) else 0
    format_names = str(format_info.get("format_name") or "").strip().lower()
    file_size = int(format_info.get("size") or fallback_size or 0)

    metadata: Dict[str, Any] = {
        "duration": _safe_float(format_info.get("duration"), 0.0),
        "file_size": file_size,
        "file_size_mb": round(file_size / (1024 * 1024), 4) if file_size else 0.0,
        "format": _canonical_video_format(format_names, candidate),
        "format_names": format_names,
        "codec": str(video_stream.get("codec_name") or "").strip() if isinstance(video_stream, dict) else "",
        "frame_rate": round(_parse_frame_rate(video_stream.get("r_frame_rate")), 3)
        if isinstance(video_stream, dict)
        else 0.0,
        "resolution": f"{width}x{height}" if width and height else "",
    }
    if isinstance(audio_stream, dict):
        metadata["audio_codec"] = str(audio_stream.get("codec_name") or "").strip()
    return normalize_video_metadata(metadata)


__all__ = [
    "merge_video_metadata",
    "normalize_video_metadata",
    "probe_local_video_metadata_sync",
]
