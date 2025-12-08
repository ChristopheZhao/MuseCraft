"""
Video Composer Agent - Combines individual video clips into final video
"""
import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentType, Scene, Resource, ResourceType
from ..services.file_storage import FileStorageService
from ..core.config import settings
from .utils.artifacts import pick_artifact_path_from_results
from ..services.memory_provider import MemoryServices
from .utils.memory_helpers import read_shared_fact, write_shared_fact


class VideoComposerAgent(BaseAgent):
    """
    Video Composer Agent combines individual scene videos into a final cohesive video
    with transitions, audio, and effects
    """
    
    def __init__(self, llms=None, memory_services: Optional[MemoryServices] = None):
        super().__init__(
            agent_type=AgentType.VIDEO_COMPOSER,
            agent_name="video_composer",
            timeout_seconds=600,  # 10 minutes for video composition
            max_retries=2,
            llms=llms,
            memory_services=memory_services,
        )
        # Dedicated storage service for managing final deliverables.
        self.file_storage = FileStorageService()
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        db: Session
    ) -> Dict[str, Any]:
        """Compose final video from individual scene videos, or add background music if requested"""
        
        # Validate input
        self._validate_input(input_data, ["workflow_state_id"])
        
        workflow_state_id = input_data["workflow_state_id"]
        # 读取 MAS WorkingMemory 视图（不可用时降级到最小上下文，而非中断）
        from .utils.memory_helpers import get_mas_working_memory
        wm = None
        try:
            wm = get_mas_working_memory(str(workflow_state_id), service=self.short_term_service)
        except Exception as _wm_err:
            self.logger.warning(f"MAS WM unavailable, degrading: {str(_wm_err)}")

        # Unified ReAct planning: let the model decide VO/BGM composition steps
        # Build neutral observation (no tool names), include hints but do not hard-branch
        await self._update_progress(10, "Gathering composition context", db)
        final_video_facts = wm.get("project.final_video", {}) if wm else {}
        video_path = input_data.get("final_video_path") or final_video_facts.get("path", '')
        bgm_facts = wm.get("project.background_music", {}) if wm else {}
        voice_settings = wm.get("project.voice_settings", {}) if wm else {}
        voice_assets_facts = wm.get("project.voice_assets", {}) if wm else {}
        vm_state = wm.get("project.voice_mixing_state", {}) if wm else {}

        # 单写模式：从 artifacts 收集可用资产（compose/bgm/voiceover/video_only）
        try:
            from ..core.config import settings as _cfg
            single_write = bool(getattr(_cfg, 'ARTIFACTS_SINGLE_WRITE_MODE', False))
        except Exception:
            single_write = False

        # 兼容单写模式：从 MAS WM facts/scene_outputs 读取最新资产
        if single_write:
            # 优先使用已写入 facts，scene_outputs 中的音视频可选读取
            try:
                scene_outputs = wm.get("scene_outputs", {}) if wm else {}
            except Exception:
                scene_outputs = {}
            # compose 视频
            if not video_path:
                try:
                    video_bucket = scene_outputs.get("scene_outputs.video") or scene_outputs.get("video") or {}
                    latest_video = max(video_bucket.values(), key=lambda v: v.get("ts", 0)) if isinstance(video_bucket, dict) else {}
                    if isinstance(latest_video, dict):
                        video_path = latest_video.get("file_path") or latest_video.get("url") or video_path
                except Exception:
                    pass
            # bgm
            if not bgm_facts:
                try:
                    audio_bucket = scene_outputs.get("scene_outputs.audio") or scene_outputs.get("audio") or {}
                    latest_audio = max(audio_bucket.values(), key=lambda v: v.get("ts", 0)) if isinstance(audio_bucket, dict) else {}
                    if isinstance(latest_audio, dict):
                        bgm_facts = {
                            "audio_path": latest_audio.get("file_path", ""),
                            "audio_url": latest_audio.get("url", ""),
                            "duration": latest_audio.get("duration_sec") or 0.0,
                            "style": voice_settings.get("style_name") if isinstance(voice_settings, dict) else "",
                            "available": True,
                        }
                except Exception:
                    pass

        obs_unified = {
            "final_video": {"path": video_path, "url": final_video_facts.get("url", "")},
            "background_music": {
                "path": bgm_facts.get("audio_path", ""),
                "url": bgm_facts.get("audio_url", ""),
                "duration": bgm_facts.get("duration", 0.0),
                "style": bgm_facts.get("style", ""),
            },
            "voice_assets": [
                {
                    "scene_number": int(k) if str(k).isdigit() else k,
                    "local_path": (v or {}).get("local_path", ""),
                    "audio_url": (v or {}).get("audio_url", ""),
                    "duration": (v or {}).get("duration", 0.0),
                }
                for k, v in (voice_assets_facts.items() if isinstance(voice_assets_facts, dict) else [])
            ],
            "voice_settings": voice_settings,
            "ducking_config": vm_state.get("ducking_config", {}),
            "requests": {
                "voiceover_requested": bool(input_data.get("add_voiceover")),
                "bgm_requested": bool(input_data.get("add_bgm")),
            },
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是视频合成代理。根据观察到的事实，自主判断是否需要为现有成片添加配音或背景音乐，"
                    "或跳过处理。若需要：1) 产出本地可用的 mp4 成片路径；2) 遵循 ducking_config 等约束；"
                    "3) 如资源仅有 URL，应先按策略落盘后再混流；4) 仅进行函数调用，不要输出解释文本。"
                    f"观察：{json.dumps(obs_unified, ensure_ascii=False)}"
                ),
            },
            {"role": "user", "content": "符合条件时直接调用函数完成；否则无需调用。"},
        ]
        fc = await self.llm_function_call(
            messages=messages,
            context_description="video composer unified plan",
            temperature=0.2,
            tools_override=None,
        )
        executed_calls = []
        if isinstance(fc, dict) and fc.get("approach") == "function_call_plan" and fc.get("tool_calls"):
            executed_calls = await self.execute_tool_calls(fc["tool_calls"])
            # 统一抽取视频产物（先看last_round_results，再看executed_calls）
            try:
                last = []
            except Exception:
                last = []
            mixed_path = pick_artifact_path_from_results(last, kind="video", require_local=True)
            if not mixed_path:
                mixed_path = pick_artifact_path_from_results(executed_calls, kind="video", require_local=True)

            if mixed_path and os.path.exists(mixed_path):
                await self._update_progress(90, "Finalizing composed video", db)
                stored_path = self._store_final_video_output(mixed_path, suffix="final_composed")
                # 发布操作交由编排层（MAS）统一处理；此处仅生成本地可用产物并写回事实
                final_url = self._resolve_local_public_url("", stored_path)
                try:
                    fv = {
                        "path": stored_path,
                        "url": final_url,
                        # storage 字段保持最小本地描述，避免在 Agent 内做外部发布
                        "storage": {
                            "provider": "local",
                            "url": final_url,
                            "skipped": True,
                        },
                    }
                    # 始终写入 final_video 事实：供持久化读取最终交付物
                    write_shared_fact(str(workflow_state_id), "project.final_video", fv, service=self.short_term_service)
                    # 统一写回：记录本轮 Composer 产物（作为阶段性artifact）
                    self.write_shared_artifact(
                        kind="video",
                        stage="compose",
                        payload={"file_path": stored_path, "url": final_url, "metadata": {"source": "composer"}},
                        scene_number=None,
                        tool="composition_tool/ffmpeg_tool",
                        workflow_state_id=str(workflow_state_id),
                    )
                except Exception as exc:
                    self.logger.error("WM write final_video failed: %s", exc, exc_info=True)
                    raise AgentError("Shared WM write failed (final_video)") from exc

                return {
                    "final_video_path": stored_path,
                    "final_video_url": final_url,
                    "subtask_state": "complete",
                    "loop_end_reason": "natural_complete",
                    "workflow_state_id": workflow_state_id,
                }

            # FC已规划但无本地成片：遵循ReAct返回partial，由上层续派
            return {
                "subtask_state": "partial",
                "loop_end_reason": "no_planned_output",
                "workflow_state_id": workflow_state_id,
            }
        # End unified ReAct planning block; 如果未产出本地成片，则返回 partial 由上层续派
        return {
            "subtask_state": "partial",
            "loop_end_reason": "no_planned_output",
            "workflow_state_id": workflow_state_id,
        }

    # _resolve_voice_segment: 已移除（由高阶组合工具或 PLAN 决策使用的原子工具承担）

    # --- Helpers: artifact extraction (供应商与工具无关，中立字段优先) ---
    # Helpers moved to shared utils.artifacts.pick_artifact_path_from_results
    
        
    
    # deprecated: removed helpers (_create_composition_timeline/_find_scene_script/_get_transition_type/_prepare_audio_elements)
    
    # deprecated: compose via ffmpeg command builders removed
    
    # deprecated: filter graph helpers removed
    
    # deprecated
    
    # deprecated: DB persistence helpers removed
    
    # deprecated: metadata helpers removed
    
    # deprecated: summary helpers removed
    
    # deprecated: timeline/audio-elements helpers removed from agent scope
    
    # deprecated: compose_final_video_from_data removed; composition is planned via tools

    def _store_final_video_output(
        self,
        source_path: str,
        suffix: str = "final_video",
        move: bool = True
    ) -> str:
        """Persist the composed video into the protected final-output directory."""

        if not source_path or not os.path.exists(source_path):
            raise AgentError(f"Final video source missing: {source_path}")

        source = Path(source_path)
        destination_dir = self.file_storage.get_final_output_dir("video")
        extension = source.suffix or ".mp4"

        exec_id = self._current_execution_id or "run"
        candidate = destination_dir / f"{suffix}_{exec_id}{extension}"
        counter = 1
        while candidate.exists():
            candidate = destination_dir / f"{suffix}_{exec_id}_{counter}{extension}"
            counter += 1

        # Move or copy depending on caller intent.
        if move:
            shutil.move(str(source), candidate)
        else:
            shutil.copy2(str(source), candidate)

        # Harden permissions to avoid accidental deletion/overwrite.
        try:
            candidate.chmod(0o444)
        except Exception:
            # Some filesystems (e.g. Windows) may not support POSIX-style chmod.
            pass

        self.logger.info(f"📦 Final video stored in safeguarded directory: {candidate}")
        return str(candidate)

    def _build_local_serving_url(self, local_path: str) -> str:
        """根据本地存储路径生成可通过 FastAPI 静态目录访问的 URL。"""

        if not local_path:
            return ""

        try:
            resolved = Path(local_path).resolve()
            final_root = Path(settings.FINAL_OUTPUT_ROOT).resolve()
            # 如果资源位于最终输出根目录内，则转换为 /files/outputs 下的相对路径
            if final_root in resolved.parents or resolved == final_root:
                relative = resolved.relative_to(final_root)
                return f"/files/outputs/{relative.as_posix()}"
        except Exception:
            # 解析失败直接返回空串，调用方会降级到 file://
            return ""

        return ""

    def _resolve_local_public_url(self, publication_url: str, local_path: str) -> str:
        """优先使用已有的发布 URL，否则构建本地静态访问路径。"""

        if publication_url:
            return publication_url

        local_url = self._build_local_serving_url(local_path)
        if local_url:
            return local_url

        return f"file://{local_path}"

    async def _publish_final_video(
        self,
        local_path: str,
        workflow_state_id: str
    ) -> Dict[str, Any]:
        """Upload the final video to remote storage (OSS preferred)."""

        publication: Dict[str, Any] = {
            "url": "",
            "remote_path": "",
            "provider": "",
            "skipped": False,
        }

        if "oss_storage" in self._available_tools:
            try:
                oss_call = {
                    "function": {
                        "name": "oss_storage.upload",
                        "arguments": {
                            "local_path": local_path,
                            "remote_path": f"final_videos/{Path(local_path).name}",
                            "content_type": "video/mp4",
                            "public_read": True,
                            "overwrite": True,
                            "metadata": {
                                "workflow_state_id": workflow_state_id,
                                "agent": self.agent_name,
                                "execution_id": execution.id,
                            },
                        }
                    }
                }
                oss_exec = await self.execute_tool_calls([oss_call])
                payload = (oss_exec[0].get('result') if (oss_exec and isinstance(oss_exec[0], dict)) else {}) or {}
                if isinstance(payload, dict):
                    publication.update(
                        {
                            "url": payload.get("url", ""),
                            "remote_path": payload.get("remote_path", ""),
                            "provider": "oss",
                            "skipped": payload.get("skipped", False),
                        }
                    )
                    return publication
            except Exception as exc:
                self.logger.warning(f"OSS upload failed for final video: {exc}")

        # Fallback: provide a static-serving URL if possible，若失败再降级到 file://
        local_url = self._build_local_serving_url(local_path)
        if not local_url:
            local_url = f"file://{local_path}"

        publication.update(
            {
                "url": local_url,
                "provider": publication.get("provider") or "local",
            }
        )

        return publication

    
    
    # deprecated: metadata-from-data removed
    
    def _create_composition_summary_from_data(
        self, 
        timeline: List[Dict], 
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create summary from SceneData"""
        
        return {
            "total_scenes": len(timeline),
            "total_duration": metadata["duration"],
            "file_size_mb": metadata["file_size_mb"],
            "resolution": metadata["resolution"],
            "composition_success": True,
            "scene_breakdown": [
                {
                    "scene_number": entry["scene_number"],
                    "duration": entry["duration"],
                    "transition_in": entry["transition_in"],
                    "transition_out": entry["transition_out"]
                }
                for entry in timeline
            ],
            "technical_specs": {
                "format": metadata["format"],
                "codec": metadata["codec"],
                "frame_rate": metadata["frame_rate"]
            }
        }
