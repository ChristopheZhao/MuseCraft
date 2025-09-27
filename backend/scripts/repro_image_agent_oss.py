"""Reproduce image-agent OSS upload path for debugging.

Usage examples::

    UV_CACHE_DIR=.uvcache uv run python backend/scripts/repro_image_agent_oss.py "<seedream_image_url>"
    UV_CACHE_DIR=.uvcache uv run python backend/scripts/repro_image_agent_oss.py "<seedream_image_url>" images/scene_4_image.jpg
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure backend package is importable when running from repo root
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.tools import register_default_tools
from app.agents.tools.tool_registry import get_tool_registry
from app.agents.tools.base_tool import ToolInput, ToolError
from app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool


async def reproduce(image_url: str, remote_key: str) -> None:
    register_default_tools()
    registry = get_tool_registry()

    file_tool = registry.get_tool("file_storage_tool")
    oss_tool = registry.get_tool("oss_storage")

    print("=== OSS runtime config ===")
    print("OSS_ACCESS_KEY_ID   =", getattr(oss_tool, "access_key_id", None))
    print("OSS_ENDPOINT        =", getattr(oss_tool, "endpoint", None))
    print("OSS_BUCKET_NAME     =", getattr(oss_tool, "bucket_name", None))
    print("UTC now             =", datetime.utcnow().isoformat())
    print("==========================")

    dest_download = f"debug/temp_seedream_download_{Path(remote_key).name}"
    try:
        res = await file_tool.execute(
            ToolInput(
                action="upload_from_url",
                parameters={
                    "url": image_url,
                    "destination_key": dest_download,
                    "metadata": {"source": "repro_script"},
                },
            )
        )
    except ToolError as te:
        print("file_storage_tool failed:", te)
        return

    payload = getattr(res, "result", res)
    local_path = None
    if isinstance(payload, dict):
        local_path = payload.get("local_path") or payload.get("file_path")

    print("Downloaded file_path:", local_path)
    if not local_path or not os.path.exists(local_path):
        print("ERROR: local file does not exist, aborting.")
        return

    tool = ImageGenerationTool()

    hosted_url = await tool._upload_local_image_to_oss(  # pylint: disable=protected-access
        local_path,
        remote_key,
        metadata={"source": "repro_script"},
    )
    print("upload_local_image_to_oss result:", hosted_url)

    if not hosted_url:
        hosted_url = await tool._mirror_image_url_to_oss(  # pylint: disable=protected-access
            image_url,
            remote_key,
            metadata={"source": "repro_script", "original_url": image_url},
        )
        print("mirror_image_url_to_oss result:", hosted_url)


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print(
            "Usage: uv run python backend/scripts/repro_image_agent_oss.py "
            "<seedream_image_url> [remote_key]"
        )
        sys.exit(1)

    image_url = sys.argv[1]
    remote_key = sys.argv[2] if len(sys.argv) == 3 else "debug/repro_scene.jpg"

    asyncio.run(reproduce(image_url, remote_key))


if __name__ == "__main__":
    main()
