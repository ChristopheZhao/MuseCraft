#!/usr/bin/env python3
"""
Retry Suno background music generation with manual parameters.

Usage (from backend/):
  python scripts/retry_suno_bgm.py \
    --description "<full text>" \
    --mood calm \
    --style corporate \
    --duration 50 \
    --title "Background Music - Video"

Notes:
  - Requires SUNO_API_KEY in environment/.env
  - Saves the audio file into generated/ and prints the local path
  - Does not mutate DB; use for ad‑hoc regeneration when previous download failed
"""

import asyncio
import argparse
import os
from pathlib import Path


async def main():
    parser = argparse.ArgumentParser(description="Retry Suno BGM generation")
    parser.add_argument("--description", required=True, help="Full creative brief for music generation")
    parser.add_argument("--mood", default="calm", help="Music mood")
    parser.add_argument("--style", default="corporate", help="Music style")
    parser.add_argument("--duration", type=int, default=45, help="Target duration in seconds")
    parser.add_argument("--title", default="Background Music - Video", help="Music title")
    parser.add_argument("--filename", default=None, help="Output filename (defaults to title + .mp3)")
    args = parser.parse_args()

    # Ensure we run from backend/
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)

    # Lazy imports after cwd is set
    from app.agents.tools.ai_services.suno_client import SunoClientTool
    from app.services.file_storage import FileStorageService

    # Validate tool availability
    tool = SunoClientTool()
    if not getattr(tool, "_functional", False):
        print("❌ SunoClientTool not functional. Missing SUNO_API_KEY?")
        return 2

    params = {
        "description": args.description,
        "mood": args.mood,
        "style": args.style,
        "duration": int(args.duration),
        "instrumental": True,
        "title": args.title,
    }

    print("🚀 Generating background music via Suno…")
    out = await tool.execute({
        "action": "generate_background_music",
        "parameters": params,
        "timeout": 180,
    })

    if not getattr(out, "success", False):
        print(f"❌ Generation failed: {getattr(out, 'error', 'unknown error')}")
        return 3

    result = out.result or {}
    audio_url = result.get("audio_url")
    print(f"✅ Generation succeeded.\n   Title: {result.get('title','')}\n   Audio URL: {audio_url}")

    if not audio_url:
        print("⚠️ No audio URL returned; nothing to save")
        return 0

    storage = FileStorageService()
    filename = args.filename or f"{args.title.replace(' ', '_')}_{args.duration}s.mp3"
    saved_path = await storage.download_and_save_audio(audio_url, filename)
    print(f"📥 Saved to: {saved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

