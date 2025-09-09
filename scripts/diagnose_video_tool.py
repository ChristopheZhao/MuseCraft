#!/usr/bin/env python3
import asyncio
import argparse

# Minimal diagnostic runner for video tool via the tool registry (no direct SDK)

async def main():
    parser = argparse.ArgumentParser(description="Diagnose video generation tool")
    parser.add_argument("--prompt", required=False, help="Video prompt text")
    parser.add_argument("--duration", type=int, default=5, help="Video duration seconds")
    parser.add_argument("--image_url", required=False, help="Reference image cloud URL (http/https)")
    parser.add_argument("--is_continuous", action="store_true", help="Enable continuity path (requires prev video URL)")
    parser.add_argument("--previous_video_url", required=False, help="Previous scene video URL for continuity")
    parser.add_argument("--fallback_image_url", required=False, help="Fallback image URL when continuity not available")
    args = parser.parse_args()

    from backend.app.agents.tools.tool_registry import get_tool_registry
    from backend.app.agents.tools.base_tool import ToolInput

    registry = get_tool_registry()

    # 1) List available video services and capabilities
    try:
        video_tool = registry.get_tool("video_generation")
        caps = await video_tool.execute(ToolInput(action="get_capabilities", parameters={}))
        print("[capabilities]", getattr(caps, 'result', caps))
    except Exception as e:
        print("[capabilities:error]", e)

    # Optionally prepare continuity image
    image_url = args.image_url
    if args.is_continuous:
        try:
            cont_tool = registry.get_tool("scene_continuity_preparation")
            params = {
                "is_continuous": True,
                "previous_scene_video_url": args.previous_video_url,
                "scene_number": 1,
                "fallback_image_url": args.fallback_image_url or image_url or ""
            }
            cont = await cont_tool.execute(ToolInput(action="prepare_scene_input", parameters=params))
            cont_payload = getattr(cont, 'result', cont)
            if isinstance(cont_payload, dict):
                image_url = cont_payload.get("image_url") or image_url
            print("[continuity]", cont_payload)
        except Exception as e:
            print("[continuity:error]", e)

    # 2) Generate video
    try:
        gen_params = {
            "prompt": args.prompt or "测试：一位年轻修士在山顶，云海翻涌，光影变换",
            "duration": args.duration,
        }
        if image_url:
            gen_params["image_url"] = image_url
        res = await video_tool.execute(ToolInput(action="generate_with_continuity", parameters=gen_params))
        print("[generate]", getattr(res, 'result', res))
    except Exception as e:
        print("[generate:error]", e)

if __name__ == "__main__":
    asyncio.run(main())

