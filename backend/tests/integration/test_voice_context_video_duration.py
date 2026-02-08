#!/usr/bin/env python3
"""
Verify voice synthesis context uses scene_outputs.video.duration_sec.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_import_order() -> None:
    # Import utils first to avoid circular import when memory_views loads memory_helpers.
    import app.agents.utils  # noqa: F401


def _probe_duration(path: str) -> float:
    if not shutil.which("ffprobe"):
        return 0.0
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float((result.stdout or "").strip())
    except ValueError:
        return 0.0


def _has_ffprobe() -> bool:
    return bool(shutil.which("ffprobe"))


def _collect_local_videos(video_dir: Path) -> List[Tuple[int, str, float]]:
    files = sorted(glob.glob(str(video_dir / "scene_*.mp4")))
    results: List[Tuple[int, str, float]] = []
    for path in files:
        name = os.path.basename(path)
        match = re.search(r"scene_(\d+)\.mp4$", name)
        if not match:
            continue
        scene_number = int(match.group(1))
        duration = _probe_duration(path)
        results.append((scene_number, path, duration))
    return results


def _build_context_from_local_videos(video_dir: Path) -> Dict[str, object]:
    _ensure_import_order()
    from app.agents.adapters.memory_views import build_voice_synthesis_context
    from app.agents.memory.short_term.service import WorkingMemoryService
    from app.agents.utils.memory_helpers import ensure_mas_working_memory, write_shared_fact

    local_videos = _collect_local_videos(video_dir)
    if not local_videos:
        return {}

    scene_outputs = {}
    scene_overview_scenes = []
    scene_scripts = {}

    for scene_number, path, duration in local_videos:
        scene_outputs[str(scene_number)] = {
            "scene_number": scene_number,
            "video_path": path,
            "duration_sec": duration,
        }
        scene_overview_scenes.append(
            {
                "scene_number": scene_number,
                "duration": duration,
                "visual_description": f"Scene {scene_number} visual",
                "narrative_description": f"Scene {scene_number} narrative",
            }
        )
        scene_scripts[scene_number] = {
            "scene_number": scene_number,
            "script_text": f"Scene {scene_number} narration",
        }

    workflow_id = f"wm_duration_probe_{int(time.time())}"
    service = WorkingMemoryService()
    ensure_mas_working_memory(workflow_id, service=service)
    write_shared_fact(workflow_id, "scene_overview", {"scenes": scene_overview_scenes}, service=service)
    write_shared_fact(workflow_id, "project.scene_scripts", scene_scripts, service=service)
    write_shared_fact(workflow_id, "scene_outputs.video", scene_outputs, service=service)

    return build_voice_synthesis_context(workflow_id, service=service)


def _assert_duration_mapping(context: Dict[str, object]) -> None:
    scenes = (context.get("context", {}) or {}).get("scenes_to_synthesize", [])  # type: ignore[assignment]
    if not scenes:
        raise AssertionError("No scenes_to_synthesize in context")

    mismatches = []
    for scene in scenes:
        scene_number = scene.get("scene_number")
        duration = float(scene.get("duration") or 0.0)
        video_duration = float(scene.get("video_duration_sec") or 0.0)
        if video_duration <= 0:
            mismatches.append((scene_number, duration, video_duration, "missing video_duration_sec"))
            continue
        if abs(duration - video_duration) > 0.01:
            mismatches.append((scene_number, duration, video_duration, "duration mismatch"))

    if mismatches:
        details = "; ".join(
            f"scene={sn} duration={dur} video={vid} reason={reason}"
            for sn, dur, vid, reason in mismatches
        )
        raise AssertionError(f"duration mapping failed: {details}")


def test_voice_context_video_duration_mapping() -> None:
    if not _has_ffprobe():
        try:
            import pytest

            pytest.skip("ffprobe is not available")
        except Exception:
            return
    backend_root = _backend_root()
    video_dir = backend_root / "storage" / "temp" / "videos"
    if not video_dir.exists():
        try:
            import pytest

            pytest.skip("No local video directory found")
        except Exception:
            return

    context = _build_context_from_local_videos(video_dir)
    if not context:
        try:
            import pytest

            pytest.skip("No local scene videos available")
        except Exception:
            return
    _assert_duration_mapping(context)


if __name__ == "__main__":
    test_voice_context_video_duration_mapping()
    print("OK: voice context duration matches scene_outputs.video.duration_sec")
