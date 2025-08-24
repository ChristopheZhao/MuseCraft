#!/usr/bin/env python3
"""
Test script: Generate a 32s Fanta commercial background music using SunoClientTool

Usage:
  cd backend
  python scripts/test_suno_fanta_bgm.py

Requirements:
  - Set SUNO_API_KEY in .env or environment variables
  - Optional: SUNO_BASE_URL if you use a custom endpoint (default in settings)
"""

import asyncio
import os
from pathlib import Path


def build_fanta_prompt() -> str:
    """Assemble the detailed prompt for Suno based on the given spec."""
    return (
        "[Style]: Upbeat Commercial Jingle, Electronic Pop, Orchestral Hybrid\n"
        "[Mood]: Playful, Energetic, Whimsical, Building Excitement\n"
        "[Tempo]: 128 BPM, Accelerating at climax\n"
        "[Duration]: 32 seconds\n\n"
        "[Structure]:\n"
        "0-8s: Mysterious intro with pizzicato strings and xylophone (Scene 1: Cutting house)\n"
        "8-16s: Building tension with electronic beats and synth layers (Scene 2: Cutting fridge)\n"
        "16-24s: Explosive climax with full orchestra and EDM drop (Scene 3: Orange explosion)\n"
        "24-32s: Cheerful resolution with brand signature sound (Scene 4: Logo reveal)\n\n"
        "[Instruments]:\n"
        "- Lead: Bright synth plucks, xylophone, glockenspiel\n"
        "- Rhythm: Electronic drums, trap hi-hats, orchestral percussion\n"
        "- Bass: Deep sub-bass with funky slap bass accents\n"
        "- Atmosphere: Swooshes, risers, sparkle sounds\n"
        "- Climax: Full orchestra hit, brass stabs, EDM synth drop\n\n"
        "[Sound Design]:\n"
        "- Cutting sounds as rhythmic elements (whoosh, slice)\n"
        "- Bubble and fizz effects during transitions\n"
        "- Orange splat sounds as percussion fills\n"
        "- Magical chimes and sparkles throughout\n\n"
        "[Dynamics]:\n"
        "0-8s: Soft and mysterious (mp) - Discovery\n"
        "8-16s: Gradually increasing (mf) - Anticipation\n"
        "16-24s: Full explosive energy (ff) - Climax\n"
        "24-32s: Bright and memorable (f) - Brand celebration\n\n"
        "[Keywords]: Commercial, Fanta, Orange, Fizzy, Playful, Modern, Youth, Summer, Explosive, "
        "Magical, Surprise, Joyful, Bouncy, Advertisement, Product Reveal, 32 seconds\n\n"
        "[Reference]: Think \"Pixar movie score meets EDM festival meets soft drink commercial\"\n"
        "instrumental only, no vocals, no lyrics. Suitable for video soundtrack, professional quality, "
        "balanced frequency range, seamless looping potential."
    )


async def main():
    # Ensure we can import project modules when running from backend/
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Lazy imports after cwd is set
    from app.agents.tools.ai_services.suno_client import SunoClientTool
    from app.services.file_storage import FileStorageService

    print("🎵 Suno Fanta BGM generation test")
    print("-" * 50)

    # Build prompt and parameters
    description = build_fanta_prompt()
    params = {
        # Keep mood/style within allowed enums for validation in tool
        # Use description to carry the full creative brief
        "description": description,
        "mood": "playful",          # allowed moods: playful/energetic/etc.
        "style": "electronic",      # allowed styles: electronic/orchestral/etc.
        "duration": 32,
        "instrumental": True,
        "title": "Fanta Orange BGM 32s"
    }

    # Create Suno client tool
    tool = SunoClientTool()
    if not getattr(tool, "_functional", False):
        print("❌ SunoClientTool not functional. Missing SUNO_API_KEY?")
        return

    print("🚀 Generating background music via Suno... (this may take ~30-120s)")
    try:
        output = await tool.execute({
            "action": "generate_background_music",
            "parameters": params,
            "timeout": 180
        })

        if not getattr(output, "success", False):
            print(f"❌ Generation failed: {getattr(output, 'error', 'unknown error')}")
            return

        result = output.result or {}
        audio_url = result.get("audio_url", "")
        print(f"✅ Generation succeeded.\n   Title: {result.get('title', '')}\n   Audio URL: {audio_url}")

        # Download and save locally
        if audio_url:
            storage = FileStorageService()
            filename = "fanta_orange_bgm_32s.mp3"
            saved_path = await storage.download_and_save_audio(audio_url, filename)
            print(f"📥 Saved to: {saved_path}")
        else:
            print("⚠️ No audio URL returned")

    except Exception as e:
        print(f"❌ Exception during generation: {e}")


if __name__ == "__main__":
    asyncio.run(main())





