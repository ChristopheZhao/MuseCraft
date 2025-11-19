"""
Smoke test for AudioGeneratorAgent (ReAct) without external dependencies.

What it does
- Sets up a local SQLite DB and creates Task/AgentExecution tables
- Creates a minimal WorkflowState with concept_plan and scenes
- Monkeypatches ToolRegistry.get_tool to return dummy in-memory tools for:
  - suno_client.generate_background_music
  - file_storage_tool.upload_from_url
  - audio_processor.adjust_duration
  - ffmpeg_tool.add_audio (no-op)
- Monkeypatches agent.llm_function_call to return a design plan JSON
- Runs AudioGeneratorAgent.execute and prints results/assertions

Run
- Ensure you have Python 3.9+ available
- Optional: create a virtualenv and install minimal deps if needed
  (SQLAlchemy and pydantic are already vendored in the project’s backend)
- Execute: `python backend/scripts/test_audio_agent_react.py`
"""

import os
import asyncio
import tempfile
from typing import Any, Dict


def _set_env_defaults():
    # Use local sqlite file DB for the test
    os.environ.setdefault("DATABASE_URL", "sqlite:///./test_audioagent.db")
    # Keep WebSocket quiet
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    # Avoid any external callbacks
    os.environ.setdefault("PUBLIC_API_URL", "http://127.0.0.1:8000")
    # Storage paths
    os.environ.setdefault("TEMP_PATH", "./storage/temp")
    os.makedirs(os.environ["TEMP_PATH"], exist_ok=True)


_set_env_defaults()


async def main() -> None:
    # Lazy imports after env
    # 兼容两种运行位置：
    # - 在项目根执行（PYTHONPATH=.）：使用 backend.app.*
    # - 在 backend 目录下执行（uv run python scripts/...）：使用 app.*
    try:
        from app.core.database import engine, SessionLocal  # type: ignore
        from app.models.base import BaseModel  # type: ignore
        from app.models import Task, TaskType, AgentType  # type: ignore  # noqa: F401
        from app.models import agent as _agent_mod  # type: ignore  # noqa: F401
        from app.models import scene as _scene_mod  # type: ignore  # noqa: F401
        from app.models import resource as _res_mod  # type: ignore  # noqa: F401
        from app.core.workflow_state import workflow_manager, SceneData  # type: ignore
        from app.agents.audio_generator import AudioGeneratorAgent  # type: ignore
        from app.agents.tools.tool_registry import get_tool_registry  # type: ignore
        from app.agents.tools import register_default_tools as _register_default_tools  # type: ignore
    except ModuleNotFoundError:
        from backend.app.core.database import engine, SessionLocal
        from backend.app.models.base import BaseModel
        from backend.app.models import Task, TaskType, AgentType  # noqa: F401
        from backend.app.models import agent as _agent_mod  # noqa: F401
        from backend.app.models import scene as _scene_mod  # noqa: F401
        from backend.app.models import resource as _res_mod  # noqa: F401
        from backend.app.core.workflow_state import workflow_manager, SceneData
        from backend.app.agents.audio_generator import AudioGeneratorAgent
        from backend.app.agents.tools.tool_registry import get_tool_registry
        from backend.app.agents.tools import register_default_tools as _register_default_tools

    # Create tables
    BaseModel.metadata.create_all(bind=engine)

    # Create a DB session
    db = SessionLocal()
    try:
        # Create a Task
        task = Task(
            title="audio-react-test",
            description="Test AudioGeneratorAgent ReAct flow",
            task_type=TaskType.VIDEO_GENERATION,
            status="in_progress",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # Create a WorkflowState
        ws = workflow_manager.create_workflow(
            user_prompt="测试一个30秒的冒险短视频，节奏紧凑，结尾有反转。",
            duration=30,
            aspect_ratio="16:9",
        )
        # Concept plan minimal
        ws.concept_plan = {
            "theme": "adventure",
            "narrative": "快速推进的冒险，逐步紧张，结尾反转",
            "music_guidance": "节奏感强、史诗感、无歌词"
        }
        # Scenes summary
        ws.scenes = [
            SceneData(scene_number=1, title="出发", duration=5, mood_and_atmosphere="curious"),
            SceneData(scene_number=2, title="遭遇", duration=10, mood_and_atmosphere="tense"),
            SceneData(scene_number=3, title="反转", duration=15, mood_and_atmosphere="epic"),
        ]
        # No final video in this smoke test (audio-only or no-mix path)
        workflow_state_id = ws.task_id

        # 允许两种模式：
        # - 真实模式（需要 SUNO_API_KEY 且系统安装了 ffmpeg）
        # - 模拟模式（默认）：无外部依赖
        registry = get_tool_registry()
        try:
            print("[test] 初始工具统计:", registry.get_registry_stats())
        except Exception:
            pass
        original_get_tool = registry.get_tool
        use_real = os.getenv("AUDIO_TEST_REAL", "0") == "1"

        # 检查前置条件（真实模式需要）
        def _ffmpeg_available() -> bool:
            import shutil as _sh
            return _sh.which("ffmpeg") is not None and _sh.which("ffprobe") is not None

        have_suno = bool(os.getenv("SUNO_API_KEY") or os.getenv("SUNO_BASE_URL"))
        if use_real and not have_suno:
            print("[test] 未检测到 SUNO_API_KEY，降级为模拟模式。设置 AUDIO_TEST_REAL=0 或配置 SUNO_API_KEY 以启用真实模式。")
            use_real = False
        if use_real and not _ffmpeg_available():
            print("[test] 未检测到 ffmpeg/ffprobe，降级为模拟模式。请安装后再试真实模式。")
            use_real = False

        class DummyTool:
            def __init__(self, name: str):
                self._name = name
                # Minimal metadata object for logging compatibility
                class _MD:
                    def __init__(self, n: str):
                        self.name = n
                self.metadata = _MD(name)

            # Tools API expected by BaseAgent
            def get_available_actions(self):
                if self._name == "suno_client":
                    return ["generate_background_music"]
                if self._name == "file_storage_tool":
                    return ["upload_from_url", "upload_file"]
                if self._name == "audio_processor":
                    return ["adjust_duration"]
                if self._name == "ffmpeg_tool":
                    return ["add_audio"]
                return []

            def get_action_schema(self, action: str) -> Dict[str, Any]:
                return {"type": "object", "properties": {}}

            async def execute(self, tool_input):
                action = getattr(tool_input, "action", None)
                params = getattr(tool_input, "parameters", {}) or {}
                # Simulate suno background music
                if self._name == "suno_client" and action == "generate_background_music":
                    return {
                        "result": {
                            "audio_url": "http://example.com/fake_bgm.mp3",
                            "title": params.get("title") or "BG Test",
                            "duration": int(params.get("duration") or 30),
                            "style": params.get("style") or "cinematic",
                            "mood": params.get("mood") or "epic",
                        }
                    }
                # Simulate storing file from URL
                if self._name == "file_storage_tool" and action == "upload_from_url":
                    # Create a small dummy file to represent persisted audio
                    base_dir = os.environ.get("TEMP_PATH", tempfile.gettempdir())
                    out_dir = os.path.join(base_dir, "audio")
                    os.makedirs(out_dir, exist_ok=True)
                    local_path = os.path.join(out_dir, "bgm_test.mp3")
                    with open(local_path, "wb") as f:
                        f.write(b"\x00\x00dummy-mp3")
                    return {"result": {"local_path": local_path}}
                # Simulate audio duration adjust
                if self._name == "audio_processor" and action == "adjust_duration":
                    # Return the same file path as output, pretending success
                    input_path = params.get("input_path")
                    return {"result": {"output_path": input_path, "final_duration": float(params.get("target_duration", 30))}}
                # Simulate ffmpeg add_audio
                if self._name == "ffmpeg_tool" and action == "add_audio":
                    # Return an output path without actually processing
                    base_dir = os.environ.get("TEMP_PATH", tempfile.gettempdir())
                    out_path = os.path.join(base_dir, "final_with_audio.mp4")
                    with open(out_path, "wb") as f:
                        f.write(b"\x00\x00dummy-mp4")
                    return {"result": {"output_path": out_path}}
                return {"result": {}}

        if use_real:
            # 在真实模式下，注册默认工具集（与 app/main.py 启动路径一致）
            try:
                _register_default_tools()
                print("[test] 默认工具已注册（真实模式）")
                try:
                    print("[test] 工具统计(注册后):", registry.get_registry_stats())
                except Exception:
                    pass
                # 确保关键工具已注册（缺失则手动注册）
                required = [
                    ("suno_client", "ai_services.suno_client", "SunoClientTool"),
                    ("file_storage_tool", "storage.file_storage_tool", "FileStorageTool"),
                    ("ffmpeg_tool", "video_processing.ffmpeg_tool", "FFmpegTool"),
                    ("audio_processor", "media_processing.audio_processor", "AudioProcessorTool"),
                ]
                for tool_name, mod_rel, cls_name in required:
                    try:
                        # probe
                        registry.get_tool(tool_name)
                        continue
                    except Exception:
                        pass
                    # manual register
                    try:
                        try:
                            mod = __import__(f"app.agents.tools.{mod_rel}", fromlist=[cls_name])
                        except ModuleNotFoundError:
                            mod = __import__(f"backend.app.agents.tools.{mod_rel}", fromlist=[cls_name])
                        tool_cls = getattr(mod, cls_name)
                        registry.register_tool(tool_cls)
                        print(f"[test] 手动注册工具: {tool_name}")
                    except Exception as ee:
                        print(f"[test] 手动注册工具失败 {tool_name}: {ee}")
            except Exception as e:
                print(f"[test] 默认工具注册失败: {e}")
        else:
            def patched_get_tool(name: str):
                return DummyTool(name)
            registry.get_tool = patched_get_tool  # type: ignore

        # Instantiate agent
        # 初始化 Agent：真实模式下不覆盖 llms，让其走配置；模拟模式可随意
        agent = AudioGeneratorAgent()

        # 规划阶段：
        # - 真实模式：若提供 AUDIO_TEST_PLAN_JSON，则仅替换规划为该 JSON（避免依赖真实 LLM）；
        #             若不提供，则走系统配置的 LLM 真实调用。
        # - 模拟模式：始终使用内置的固定规划，保证可重复。
        plan_override = os.getenv("AUDIO_TEST_PLAN_JSON")
        if not use_real or plan_override:
            async def fake_llm_function_call(messages, model=None, context_description="", temperature=0.2, **kwargs):
                import json as _json
                if plan_override:
                    return {"content": plan_override}
                plan = {
                    "style": "Cinematic Hybrid",
                    "mood": "epic",
                    "duration": 30,
                    "instrumental": True,
                    "title": "Background Music",
                    "negativeTags": "piano solo",
                    "model": "V3_5"
                }
                return {"content": _json.dumps(plan, ensure_ascii=False)}
            agent.llm_function_call = fake_llm_function_call  # type: ignore

        # Execute
        input_data = {"workflow_state_id": workflow_state_id}
        result = await agent.execute(task=task, input_data=input_data, db=db, execution_order=1)

        # Restore registry method
        registry.get_tool = original_get_tool  # type: ignore

        # Assertions/Output
        print("AudioGeneratorAgent result:")
        print(result)
        ok = bool(result.get("audio_url") or result.get("audio_path"))
        assert ok, "Expected audio_url or audio_path in result"
        print("OK: Audio generation simulated successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
