"""
Video Composer Agent - Combines individual video clips into final video
"""
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .react_agent import ReActAgent
from .base import AgentError
from ..models import Task, AgentType
from ..core.config import settings
from .utils.artifacts import pick_artifact_path_from_results
from .utils.memory_helpers import write_shared_fact
from ..services.video_composer_execution_contract import (
    get_video_composer_compose_mode,
    get_video_composer_execution_contract,
)


class VideoComposerAgent(ReActAgent):
    """
    Video Composer Agent combines individual scene videos into a final cohesive video
    with transitions, audio, and effects
    """

    def __init__(self, llms=None, memory_services: Optional[Any] = None):
        max_iters = int(getattr(settings, "VIDEO_COMPOSER_MAX_ITERATIONS", 3))
        if max_iters < 2:
            max_iters = 2
        timeout_seconds = int(getattr(settings, "VIDEO_COMPOSER_TIMEOUT_SECONDS", 600))
        super().__init__(
            agent_type=AgentType.VIDEO_COMPOSER,
            agent_name="video_composer",
            timeout_seconds=timeout_seconds,
            max_retries=2,
            max_iterations=max_iters,
            tools=[
                "composition_tool",
                "ffmpeg_tool",
                "audio_processor",
            ],
            llms=llms,
            memory_services=memory_services,
        )

    async def _think_and_plan(self, current_state: Dict[str, Any], task: Task, iteration: int) -> Dict[str, Any]:
        """PLAN：使用模板和分区化上下文生成 FC 规划。"""
        messages = self.build_plan_messages(current_state or {})
        fc_plan = await self.llm_function_call(
            messages=messages,
            context_description="video_composer_plan_fc",
            temperature=0.2,
            tools_override=None,
        )
        planned_calls = list(fc_plan.get("tool_calls") or []) if isinstance(fc_plan, dict) else []
        plan_llm = fc_plan.get("llm_response") if isinstance(fc_plan, dict) else None

        if not planned_calls:
            return {
                "action": "noop",
                "plan_llm": plan_llm,
                "reason": "no_calls_planned",
            }

        return {
            "action": "execute_planned_calls",
            "tool_calls": planned_calls,
            "plan_llm": plan_llm,
        }

    def _resolve_execution_contract(
        self,
        input_data: Dict[str, Any],
        workflow_state_id: str,
    ) -> Dict[str, Any]:
        try:
            return get_video_composer_execution_contract(
                input_data,
                workflow_state_id=str(workflow_state_id or ""),
            )
        except ValueError as exc:
            raise AgentError(f"Invalid video_composer execution boundary: {exc}") from exc

    def _resolve_execution_boundary(
        self,
        input_data: Dict[str, Any],
        workflow_state_id: str,
    ) -> Dict[str, Any]:
        execution_contract = self._resolve_execution_contract(input_data, workflow_state_id)
        return {
            "execution_contract": execution_contract,
            "compose_mode": get_video_composer_compose_mode(execution_contract),
        }

    def _resolve_output_suffix(self, mix_type: str) -> str:
        if mix_type == "bgm":
            return "final_with_bgm"
        if mix_type == "voiceover":
            return "final_with_voiceover"
        return "final_composed"

    def _build_mix_receipt(
        self,
        *,
        input_data: Dict[str, Any],
        mix_type: str,
        output_path: str,
        output_url: str,
    ) -> Dict[str, Any]:
        static_ctx = input_data.get("static_context") if isinstance(input_data, dict) else {}
        static_ctx = static_ctx if isinstance(static_ctx, dict) else {}
        final_video_ctx = static_ctx.get("final_video") if isinstance(static_ctx, dict) else {}
        bgm_ctx = static_ctx.get("background_music") if isinstance(static_ctx, dict) else {}
        voice_assets_ctx = static_ctx.get("voice_assets") if isinstance(static_ctx, dict) else []

        receipt: Dict[str, Any] = {
            "mix_type": mix_type,
            "output_path": output_path,
            "output_url": output_url,
            "inputs": {},
            "execution_id": self._get_execution_id() or "",
            "ts": time.time(),
        }
        if isinstance(final_video_ctx, dict) and (final_video_ctx.get("path") or final_video_ctx.get("url")):
            receipt["inputs"]["video"] = {
                "path": final_video_ctx.get("path", ""),
                "url": final_video_ctx.get("url", ""),
            }
        if mix_type == "bgm" and isinstance(bgm_ctx, dict):
            receipt["inputs"]["background_music"] = {
                "path": bgm_ctx.get("path", ""),
                "url": bgm_ctx.get("url", ""),
            }
        if mix_type == "voiceover" and isinstance(voice_assets_ctx, list):
            receipt["inputs"]["voice_assets"] = voice_assets_ctx
        return receipt

    async def _execute_action(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
        db: Session,
        iteration: int,
    ) -> Dict[str, Any]:
        """ACT：执行规划的工具调用并写回成片事实。"""
        act = (action_plan or {}).get("action")
        params = (action_plan or {}).get("parameters", {})
        call_tools = list(action_plan.get("tool_calls") or params.get("call_tools") or [])
        plan_llm = action_plan.get("plan_llm") or params.get("plan_llm")
        if act == "noop" or not call_tools:
            return {
                "success": True,
                "executed_calls": [],
                "plan_llm": plan_llm,
            }

        executed_calls = await self.execute_tool_calls(call_tools)
        mixed_path = pick_artifact_path_from_results(
            executed_calls,
            kind="video",
            require_local=True,
        )

        if not mixed_path or not os.path.exists(mixed_path):
            return {
                "success": False,
                "action_performed": "video_composition",
                "executed_calls": executed_calls,
                "plan_llm": plan_llm,
            }

        workflow_id = str(input_data.get("workflow_state_id") or self.workflow_state_id or "")
        boundary = self._resolve_execution_boundary(input_data, workflow_id)
        mix_type = boundary["compose_mode"]
        stored_path = mixed_path
        final_url = self._resolve_local_public_url("", stored_path)
        mix_receipt = self._build_mix_receipt(
            input_data=input_data,
            mix_type=mix_type,
            output_path=stored_path,
            output_url=final_url,
        )
        if workflow_id:
            payload = {
                "path": stored_path,
                "url": final_url,
                "storage": {
                    "provider": "local",
                    "url": final_url,
                    "skipped": True,
                },
            }
            try:
                write_shared_fact(
                    workflow_id,
                    "project.final_video",
                    payload,
                    service=self.short_term_service,
                )
            except Exception as exc:
                self.logger.warning(
                    "MAS write failed: project.final_video agent=%s wf_id=%s err=%s",
                    self.agent_name,
                    workflow_id,
                    exc,
                    exc_info=True,
                )
            if isinstance(mix_receipt, dict) and mix_receipt:
                try:
                    write_shared_fact(
                        workflow_id,
                        "project.final_video_mix",
                        dict(mix_receipt),
                        service=self.short_term_service,
                    )
                except Exception as exc:
                    self.logger.warning(
                        "MAS write failed: project.final_video_mix agent=%s wf_id=%s err=%s",
                        self.agent_name,
                        workflow_id,
                        exc,
                        exc_info=True,
                    )
        return {
            "success": True,
            "action_performed": "video_composition",
            "final_video_path": stored_path,
            "final_video_url": final_url,
            "mix_receipt": mix_receipt,
            "orchestration_report": {
                "status": "completed",
                "boundary_event": "compose_completed",
                "gate_triggers": ["workflow_global_bgm_mix_delivery"] if mix_type == "bgm" else [],
                "artifacts": [
                    {"kind": "shared_fact", "ref": "project.final_video"},
                    {"kind": "shared_fact", "ref": "project.final_video_mix"},
                ],
                "reflection": {
                    "completion_state": "completed",
                    "mix_type": mix_type,
                    "reported_gaps": [],
                    "reported_hints": [],
                },
            },
            "executed_calls": executed_calls,
            "plan_llm": plan_llm,
        }

    async def _reflect_on_results(
        self,
        action_result: Dict[str, Any],
        current_state: Dict[str, Any],
        task: Task,
        iteration: int,
    ) -> Dict[str, Any]:
        ok = bool(action_result.get("success"))
        summary = "合成成功" if ok else "合成未成功"
        return {"success": ok, "reflection_summary": summary}

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
        workflow_state_id: str,
    ) -> Dict[str, Any]:
        """Upload the final video to remote storage (OSS preferred)."""

        publication: Dict[str, Any] = {
            "url": "",
            "remote_path": "",
            "provider": "",
            "skipped": False,
        }
        exec_id = self._get_execution_id() or "run"

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
                                "execution_id": exec_id,
                            },
                        },
                    }
                }
                oss_exec = await self.execute_tool_calls([oss_call])
                payload = (oss_exec[0].get("result") if (oss_exec and isinstance(oss_exec[0], dict)) else {}) or {}
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

    def _create_composition_summary_from_data(
        self,
        timeline: List[Dict],
        metadata: Dict[str, Any],
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
                    "transition_out": entry["transition_out"],
                }
                for entry in timeline
            ],
            "technical_specs": {
                "format": metadata["format"],
                "codec": metadata["codec"],
                "frame_rate": metadata["frame_rate"],
            },
        }
