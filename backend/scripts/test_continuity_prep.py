#!/usr/bin/env python3
"""
Quick continuity-prep test: extracts final frame from a given video (local path),
uploads it to OSS via oss_storage, and prints the returned URL.

Usage:
  uv run scripts/test_continuity_prep.py --video ./path/to/video.mp4 --scene 2
If --video is omitted, it generates a 1s black test clip via ffmpeg into TEMP_PATH.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))  # repo root

from app.core.config import settings
from app.agents.tools.tool_registry import ToolRegistry
from app.agents.tools.video_processing.ffmpeg_tool import FFmpegTool
from app.agents.tools.storage.oss_storage_tool import OSSStorageTool
from app.agents.tools.video_processing.final_frame_tool import FinalFrameTool
from app.agents.tools.video_processing.scene_continuity_preparation_tool import (
    SceneContinuityPreparationTool,
)
from app.agents.tools.base_tool import ToolInput


logger = logging.getLogger("cont_prep_test")


def _ensure_ffmpeg_video(video_path: Path) -> None:
    video_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
        str(video_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found in PATH. Please install ffmpeg.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr.decode('utf-8', 'ignore')}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=str, help="Local video file path for testing")
    parser.add_argument("--scene", type=int, default=2, help="Current scene number (>=2)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger.info("Starting continuity-prep test")

    # Prepare a test video if not provided
    if args.video:
        video_path = Path(args.video)
        if not video_path.exists():
            raise RuntimeError(f"Video not found: {video_path}")
    else:
        tmp_dir = Path(settings.TEMP_PATH) / "test"
        video_path = tmp_dir / "test_black_1s.mp4"
        if not video_path.exists():
            _ensure_ffmpeg_video(video_path)
        logger.info(f"Using generated test video: {video_path}")

    # Basic config checks for OSS
    missing = []
    if not settings.OSS_ACCESS_KEY_ID:
        missing.append("OSS_ACCESS_KEY_ID")
    if not settings.OSS_ACCESS_KEY_SECRET:
        missing.append("OSS_ACCESS_KEY_SECRET")
    if not settings.OSS_ENDPOINT:
        missing.append("OSS_ENDPOINT")
    if not settings.OSS_BUCKET_NAME:
        missing.append("OSS_BUCKET_NAME")
    if missing:
        raise RuntimeError(f"OSS configuration incomplete, missing: {', '.join(missing)}")

    # Register tools
    registry = ToolRegistry()
    # Ensure fresh registrations override any existing ones
    for tn in ("ffmpeg_tool", "oss_storage", "final_frame_tool", "scene_continuity_preparation"):
        try:
            registry.unregister_tool(tn)
        except Exception:
            pass
    registry.register_tool(FFmpegTool)
    registry.register_tool(OSSStorageTool)
    registry.register_tool(FinalFrameTool)
    registry.register_tool(SceneContinuityPreparationTool)

    tool = registry.get_tool("scene_continuity_preparation")
    params = {
        "is_continuous": True,
        "scene_number": int(args.scene),
        # Intentionally pass local path via the param; the tool supports it.
        "previous_scene_video_url": str(video_path),
        "fallback_image_url": "",
    }
    out = await tool.execute(ToolInput(action="prepare_scene_input", parameters=params))
    res = getattr(out, "result", out)
    ok = getattr(out, "success", isinstance(res, dict) and res.get("success"))
    if not ok:
        raise RuntimeError(f"Continuity prep failed: {getattr(out, 'error', res)}")

    print("=== Continuity Prep Result ===")
    print(f"success: {ok}")
    print(f"image_url: {res.get('image_url')}")
    print(f"continuity_used: {res.get('continuity_used')}")
    print(f"processing_type: {res.get('processing_type')}")
    print(f"upload_info: {res.get('upload_info')}")


if __name__ == "__main__":
    asyncio.run(main())

