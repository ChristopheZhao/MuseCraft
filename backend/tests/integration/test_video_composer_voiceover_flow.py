"""
Integration test for VideoComposerAgent voiceover flow.

Default: offline stub (no network).
Real LLM: set USE_REAL_LLM=1 (requires GLM_API_KEY/ZHIPU_API_KEY).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import types
import uuid

import pytest

from app.agents.adapters.memory_views import build_video_composer_context
from app.agents.tools.media_processing.audio_processor import AudioProcessorTool
from app.agents.tools.storage.file_storage_tool import FileStorageTool
from app.agents.tools.tool_registry import get_tool_registry
from app.agents.tools.video_composition.composition_tool import CompositionTool
from app.agents.tools.video_processing.ffmpeg_tool import FFmpegTool
from app.agents.utils.memory_helpers import (
    ensure_agent_working_memory,
    ensure_mas_working_memory,
    write_shared_fact,
)
from app.agents.video_composer import VideoComposerAgent
from app.models import Task, TaskType
from app.services.memory_provider import build_memory_services
from app.services.video_composer_execution_contract import build_video_composer_execution_contract


def _run_cmd(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _make_scene_assets(tmp_dir: str, scene_number: int, duration: float = 0.5) -> tuple[str, str]:
    video_path = os.path.join(tmp_dir, f"scene_{scene_number}.mp4")
    audio_path = os.path.join(tmp_dir, f"voice_{scene_number}.wav")
    _run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240",
            "-t",
            str(duration),
            "-pix_fmt",
            "yuv420p",
            video_path,
        ]
    )
    _run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={440 + (scene_number * 20)}",
            "-t",
            str(duration),
            audio_path,
        ]
    )
    return video_path, audio_path


def _register_tools() -> None:
    registry = get_tool_registry()
    registry.register_tool(FFmpegTool)
    registry.register_tool(AudioProcessorTool)
    registry.register_tool(FileStorageTool)
    registry.register_tool(CompositionTool)


def _has_llm_key() -> bool:
    return bool(os.getenv("GLM_API_KEY") or os.getenv("ZHIPU_API_KEY"))


async def _apply_stub_llm(agent: VideoComposerAgent, scene_media_ref: str, output_filename: str) -> None:
    async def fake_llm_function_call(self, *args, **kwargs):
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "composition_tool.compose_story_video",
                        "arguments": {
                            "scene_media_ref": scene_media_ref,
                            "output_filename": output_filename,
                        },
                    }
                }
            ],
            "llm_response": {"content": "stub plan"},
        }

    async def fake_reflect(self, action_result, current_state, task, iteration):
        ok = bool(action_result.get("success")) if isinstance(action_result, dict) else False
        return {"success": ok, "reflection_summary": "stub", "task_complete": ok}

    agent.llm_function_call = types.MethodType(fake_llm_function_call, agent)
    agent._reflect_on_results = types.MethodType(fake_reflect, agent)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_video_composer_voiceover_flow() -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")

    use_real_llm = os.getenv("USE_REAL_LLM", "").strip() == "1"
    if use_real_llm and not _has_llm_key():
        pytest.skip("USE_REAL_LLM=1 set but no GLM_API_KEY/ZHIPU_API_KEY found")

    os.environ.setdefault("VIDEO_COMPOSER_MAX_ITERATIONS", "3")

    tmp_dir = tempfile.mkdtemp(prefix="composer_voice_")
    scenes = []
    for scene_number in (1, 2):
        video_path, audio_path = _make_scene_assets(tmp_dir, scene_number, duration=1.0)
        scenes.append((scene_number, video_path, audio_path))

    _register_tools()

    memory_services = build_memory_services()
    wf_id = f"wf-composer-voice-{uuid.uuid4().hex[:8]}"

    ensure_mas_working_memory(wf_id, service=memory_services.short_term)
    ensure_agent_working_memory(wf_id, "video_composer", service=memory_services.short_term)

    scene_outputs_video = {}
    scene_outputs_voice = {}
    overview_scenes = []
    for scene_number, video_path, audio_path in scenes:
        scene_outputs_video[str(scene_number)] = {
            "scene_number": scene_number,
            "video_path": video_path,
            "duration_sec": 1.0,
        }
        scene_outputs_voice[str(scene_number)] = {
            "scene_number": scene_number,
            "audio_path": audio_path,
            "duration_sec": 1.0,
        }
        overview_scenes.append({"scene_number": scene_number, "duration": 1.0})

    write_shared_fact(wf_id, "scene_outputs.video", scene_outputs_video, service=memory_services.short_term)
    write_shared_fact(wf_id, "scene_outputs.voice", scene_outputs_voice, service=memory_services.short_term)
    write_shared_fact(wf_id, "scene_overview", {"scenes": overview_scenes}, service=memory_services.short_term)

    static_context = build_video_composer_context(
        wf_id,
        service=memory_services.short_term,
        requests={"compose_requested": True, "voiceover_requested": True, "bgm_requested": False},
    )
    scene_media_ref = static_context.get("scene_media_ref") or ""
    assert scene_media_ref

    task = Task(
        title="composer-voiceover-flow",
        description="voiceover flow regression",
        task_type=TaskType.VIDEO_EDITING,
    )

    agent = VideoComposerAgent(memory_services=memory_services)
    output_filename = f"voiceover_{uuid.uuid4().hex[:6]}.mp4"
    if not use_real_llm:
        await _apply_stub_llm(agent, scene_media_ref, output_filename)

    input_data = {
        "workflow_state_id": wf_id,
        "user_prompt": "compose with voiceover",
        "execution_contract": build_video_composer_execution_contract(
            workflow_state_id=wf_id,
            compose_mode="voiceover",
        ),
        "static_context": static_context,
    }

    result = await agent.execute(task, input_data)

    final_path = result.get("final_video_path") or ""
    mix_receipt = result.get("mix_receipt") or {}
    mix_path = mix_receipt.get("output_path") or ""

    assert final_path and os.path.exists(final_path)
    assert mix_receipt.get("mix_type") == "voiceover"
    assert mix_path and os.path.exists(mix_path)

    if use_real_llm:
        assert result.get("subtask_state") == "complete"
        assert result.get("loop_end_reason") == "plan_contract_task_complete"
    else:
        assert result.get("success") is True
