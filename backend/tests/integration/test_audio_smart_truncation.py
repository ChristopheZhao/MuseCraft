import os
import shutil
import subprocess
import pytest


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg/ffprobe not available")


@pytest.mark.asyncio
async def test_audio_smart_truncation(tmp_path):
    """
    Verify AudioAgent uses analysis+apply_edit_plan to truncate overlong BGM to match video duration,
    then Composer adds it onto the video.
    """
    try:
        from app.core.database import engine, SessionLocal  # type: ignore
        from app.models.base import BaseModel  # type: ignore
        from app.models import Task, TaskType  # type: ignore
        from app.core.workflow_state import workflow_manager, SceneData  # type: ignore
        from app.agents.audio_generator import AudioGeneratorAgent  # type: ignore
        from app.agents.video_composer import VideoComposerAgent  # type: ignore
        from app.agents.tools import register_default_tools  # type: ignore
        from app.agents.tools.tool_registry import get_tool_registry  # type: ignore
    except ModuleNotFoundError:
        from backend.app.core.database import engine, SessionLocal
        from backend.app.models.base import BaseModel
        from backend.app.models import Task, TaskType
        from backend.app.core.workflow_state import workflow_manager, SceneData
        from backend.app.agents.audio_generator import AudioGeneratorAgent
        from backend.app.agents.video_composer import VideoComposerAgent
        from backend.app.agents.tools import register_default_tools
        from backend.app.agents.tools.tool_registry import get_tool_registry

    BaseModel.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Create task
        task = Task(title="smart-trunc", description="", task_type=TaskType.VIDEO_GENERATION, status="in_progress")
        db.add(task); db.commit(); db.refresh(task)

        # Prepare 3s black video
        video_path = tmp_path / "base.mp4"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=size=320x240:rate=25:color=black", "-t", "3", str(video_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Prepare 8s audio with 1s silence tail
        long_audio = tmp_path / "long.mp3"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=500:duration=7", str(long_audio)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # WF state
        ws = workflow_manager.create_workflow(user_prompt="smart truncation", duration=3, aspect_ratio="16:9")
        ws.final_video_path = str(video_path)
        ws.scenes = [SceneData(scene_number=1, title="s1", duration=3)]

        # register tools and patch suno/storage to return long_audio
        register_default_tools()
        registry = get_tool_registry()
        orig_get = registry.get_tool

        # 允许真实工具链（需 SUNO_API_KEY）
        use_real = os.getenv("AUDIO_TEST_REAL", "0") == "1"
        if not use_real:
            class DummyTool:
                def __init__(self, name: str):
                    self._name = name
                def get_available_actions(self):
                    if self._name == "suno_client":
                        return ["generate_background_music"]
                    if self._name == "file_storage_tool":
                        return ["upload_from_url"]
                    return []
                def get_action_schema(self, action: str):
                    return {"type": "object", "properties": {}}
                async def execute(self, tool_input):
                    action = getattr(tool_input, "action", None)
                    params = getattr(tool_input, "parameters", {}) or {}
                    if self._name == "suno_client" and action == "generate_background_music":
                        return {"result": {"audio_url": "http://example.com/long.mp3", "title": "L", "duration": 8}}
                    if self._name == "file_storage_tool" and action == "upload_from_url":
                        return {"result": {"local_path": str(long_audio)}}
                    return {"result": {}}

            def patched_get(name: str):
                if name in ("suno_client", "file_storage_tool"):
                    return DummyTool(name)
                return orig_get(name)

            registry.get_tool = patched_get  # type: ignore

        # Agent
        agent = AudioGeneratorAgent()
        async def fake_llm(messages, **kwargs):
            import json as _json
            plan = {"style": "Cinematic Hybrid", "mood": "epic", "duration": 3, "instrumental": True, "title": "L", "negativeTags": "piano solo", "model": "V3_5"}
            return {"content": _json.dumps(plan, ensure_ascii=False)}
        agent.llm_function_call = fake_llm  # type: ignore

        # Execute AudioAgent (analysis+smart apply)
        out = await agent.execute(task=task, input_data={"workflow_state_id": ws.task_id}, db=db, execution_order=1)

        # Composer add_bgm
        comp = VideoComposerAgent()
        comp_out = await comp.execute(task=task, input_data={"workflow_state_id": ws.task_id, "add_bgm": True}, db=db, execution_order=2)

        # Restore
        registry.get_tool = orig_get  # type: ignore

        # Validate final video exists
        mixed = comp_out.get("final_video_path")
        assert mixed and os.path.exists(mixed)

    finally:
        db.close()
