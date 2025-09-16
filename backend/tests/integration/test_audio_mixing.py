import os
import asyncio
import tempfile
import shutil
import subprocess
from typing import Any, Dict

import pytest


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg/ffprobe not available")


@pytest.mark.asyncio
async def test_audio_mixing_with_final_video(tmp_path):
    """
    Integration: given an existing final video, AudioGeneratorAgent generates BGM
    and mixes it into the video using real ffmpeg_tool (audio_processor optional).

    This test patches only suno_client (to avoid network) and file_storage_tool
    (to return a prepared local mp3), keeping ffmpeg_tool real.
    """

    # Imports (backend context)
    try:
        from app.core.database import engine, SessionLocal  # type: ignore
        from app.models.base import BaseModel  # type: ignore
        from app.models import Task, TaskType  # type: ignore
        from app.core.workflow_state import workflow_manager, SceneData  # type: ignore
        from app.agents.audio_generator import AudioGeneratorAgent  # type: ignore
        from app.agents.tools.tool_registry import get_tool_registry  # type: ignore
        from app.agents.tools import register_default_tools  # type: ignore
    except ModuleNotFoundError:
        from backend.app.core.database import engine, SessionLocal
        from backend.app.models.base import BaseModel
        from backend.app.models import Task, TaskType
        from backend.app.core.workflow_state import workflow_manager, SceneData
        from backend.app.agents.audio_generator import AudioGeneratorAgent
        from backend.app.agents.tools.tool_registry import get_tool_registry
        from backend.app.agents.tools import register_default_tools

    # Ensure tables
    BaseModel.metadata.create_all(bind=engine)

    # Prepare minimal DB task
    db = SessionLocal()
    try:
        task = Task(
            title="mixing-test",
            description="mixing integration",
            task_type=TaskType.VIDEO_GENERATION,
            status="in_progress",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # Prepare a short dummy video using ffmpeg (black, 3s)
        video_path = tmp_path / "dummy_video.mp4"
        cmd_video = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=size=320x240:rate=25:color=black",
            "-t", "3",
            str(video_path)
        ]
        subprocess.run(cmd_video, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Prepare a short sine audio (mp3, 3s)
        sine_audio = tmp_path / "sine.mp3"
        cmd_audio = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
            "-c:a", "libmp3lame",
            str(sine_audio)
        ]
        subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Build workflow state with final video
        ws = workflow_manager.create_workflow(
            user_prompt="三秒黑屏视频混音测试",
            duration=3,
            aspect_ratio="16:9",
        )
        ws.final_video_path = str(video_path)
        ws.scenes = [SceneData(scene_number=1, title="s1", duration=3)]

        # Register default tools
        register_default_tools()
        registry = get_tool_registry()
        original_get_tool = registry.get_tool

        # 允许通过环境变量使用真实工具链（需要 SUNO_API_KEY 和网络）
        use_real = os.getenv("AUDIO_TEST_REAL", "0") == "1"
        if not use_real:
            # Patch only suno_client + file_storage_tool（离线可重复）
            class DummyTool:
                def __init__(self, name: str):
                    self._name = name

                def get_available_actions(self):
                    if self._name == "suno_client":
                        return ["generate_background_music"]
                    if self._name == "file_storage_tool":
                        return ["upload_from_url", "upload_file"]
                    return []

                def get_action_schema(self, action: str) -> Dict[str, Any]:
                    return {"type": "object", "properties": {}}

                async def execute(self, tool_input):
                    action = getattr(tool_input, "action", None)
                    params = getattr(tool_input, "parameters", {}) or {}
                    if self._name == "suno_client" and action == "generate_background_music":
                        return {"result": {"audio_url": "http://example.com/fake_bgm.mp3", "title": "test", "duration": 3}}
                    if self._name == "file_storage_tool" and action == "upload_from_url":
                        return {"result": {"local_path": str(sine_audio)}}
                    if self._name == "file_storage_tool" and action == "upload_file":
                        return {"result": {"file_key": os.path.basename(params.get("file_path", ""))}}
                    return {"result": {}}

            def patched_get_tool(name: str):
                if name in ("suno_client", "file_storage_tool"):
                    return DummyTool(name)
                return original_get_tool(name)

            registry.get_tool = patched_get_tool  # type: ignore

        # Agent instance（走系统配置）
        agent = AudioGeneratorAgent()

        # Patch plan to deterministic JSON
        async def fake_llm_function_call(messages, model=None, context_description="", temperature=0.2, **kwargs):
            import json as _json
            plan = {
                "style": "Cinematic Hybrid",
                "mood": "epic",
                "duration": 3,
                "instrumental": True,
                "title": "BG",
                "negativeTags": "piano solo",
                "model": "V3_5"
            }
            return {"content": _json.dumps(plan, ensure_ascii=False)}

        agent.llm_function_call = fake_llm_function_call  # type: ignore

        # Execute AudioAgent to produce BGM (no mixing in composer mode)
        result = await agent.execute(task=task, input_data={"workflow_state_id": ws.task_id}, db=db, execution_order=1)

        # Then call Composer to add BGM
        from app.agents.video_composer import VideoComposerAgent as _VCA  # type: ignore
        comp = _VCA() if 'app.' in str(type(agent)) else __import__('backend.app.agents.video_composer', fromlist=['VideoComposerAgent']).VideoComposerAgent()
        comp_out = await comp.execute(task=task, input_data={"workflow_state_id": ws.task_id, "add_bgm": True}, db=db, execution_order=2)

        # Restore
        registry.get_tool = original_get_tool  # type: ignore

        # Assert mixed video exists
        mixed = comp_out.get("final_video_path") or result.get("mixed_video_path")
        assert mixed, "Expected mixed_video_path/final_video_path in composer output"
        assert os.path.exists(mixed), f"Mixed video not found: {mixed}"

    finally:
        db.close()
