"""
Video Composer Agent - Combines individual video clips into final video
"""
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from .react_agent import ReActAgent
from .base import AgentError
from ..domain import AgentTaskReference, AgentType
from ..core.config import settings
from .utils.artifacts import pick_artifact_path_from_results
from .utils.media_runtime import build_local_public_url
from ..services.video_composer_execution_contract import (
    get_video_composer_compose_mode,
    get_video_composer_execution_contract,
)


_FINALIZE_BOUNDARY_KEY = "composer_finalize_boundary"


class VideoComposerFinalizeBoundaryError(AgentError):
    """Raised when final success is not bound to an explicit compose receipt."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


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

    async def _think_and_plan(
        self, current_state: Dict[str, Any], task: AgentTaskReference, iteration: int
    ) -> Dict[str, Any]:
        """PLAN：使用模板和分区化上下文生成本轮 FC 调用请求。"""
        messages = self.build_plan_messages(current_state or {})
        fc_plan = await self.llm_function_call(
            messages=messages,
            context_description="video_composer_plan_fc",
            temperature=0.2,
            tools_override=None,
        )
        tool_calls = list(fc_plan.get("tool_calls") or []) if isinstance(fc_plan, dict) else []
        plan_llm = fc_plan.get("llm_response") if isinstance(fc_plan, dict) else None

        if not tool_calls:
            return {
                "action": "noop",
                "plan_llm": plan_llm,
                "reason": "no_calls_planned",
            }

        return {
            "action": "execute_tool_calls",
            "tool_calls": tool_calls,
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

    def _build_success_orchestration_report(self, mix_type: str) -> Dict[str, Any]:
        return {
            "status": "completed",
            "boundary_event": "compose_completed",
            "gate_triggers": ["workflow_global_bgm_mix_delivery"] if mix_type == "bgm" else [],
            "artifacts": [
                {"kind": "shared_fact", "ref": "project.final_video"},
                {"kind": "shared_fact", "ref": "project.final_video_mix"},
            ],
            "reflection": {
                "mix_type": mix_type,
                "reported_gaps": [],
                "reported_hints": [],
            },
        }

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
        if isinstance(final_video_ctx, dict) and (
            final_video_ctx.get("path") or final_video_ctx.get("url")
        ):
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

    def _remember_finalize_boundary(
        self,
        *,
        input_data: Dict[str, Any],
        execution_contract: Dict[str, Any],
        output_path: str,
        output_url: str,
    ) -> None:
        execution_id = self._get_execution_id()
        if (
            type(execution_id) is not str
            or not execution_id
            or execution_id != execution_id.strip()
        ):
            raise VideoComposerFinalizeBoundaryError(
                "Video composer finalize boundary requires current execution_id",
                reason_code="video_composer_finalize_boundary_execution_missing",
            )
        get_video_composer_compose_mode(execution_contract)
        static_ctx = input_data.get("static_context") if isinstance(input_data, dict) else {}
        static_ctx = static_ctx if isinstance(static_ctx, dict) else {}
        boundary_input: Dict[str, Any] = {
            "static_context": {
                "final_video": dict(static_ctx.get("final_video") or {})
                if isinstance(static_ctx.get("final_video"), dict)
                else {},
                "background_music": dict(static_ctx.get("background_music") or {})
                if isinstance(static_ctx.get("background_music"), dict)
                else {},
                "voice_assets": list(static_ctx.get("voice_assets") or [])
                if isinstance(static_ctx.get("voice_assets"), list)
                else [],
            },
        }
        self.wm.put(
            _FINALIZE_BOUNDARY_KEY,
            {
                "contract_version": "v1",
                "execution_id": execution_id,
                "execution_contract": dict(execution_contract),
                "output_path": output_path,
                "output_url": output_url,
                "receipt_input": boundary_input,
            },
        )

    def _load_finalize_boundary(
        self,
        *,
        expected_workflow_state_id: str,
        expected_execution_id: str,
    ) -> Dict[str, Any]:
        try:
            payload = self.wm.get(_FINALIZE_BOUNDARY_KEY, {})
        except Exception as exc:
            raise VideoComposerFinalizeBoundaryError(
                f"Video composer finalize boundary read failed: {exc}",
                reason_code="video_composer_finalize_boundary_unavailable",
            ) from exc
        if not isinstance(payload, dict) or not payload:
            raise VideoComposerFinalizeBoundaryError(
                "Video composer finalize boundary is required",
                reason_code="video_composer_finalize_boundary_missing",
            )
        boundary = dict(payload)
        if boundary.get("contract_version") != "v1":
            raise VideoComposerFinalizeBoundaryError(
                "Video composer finalize boundary contract_version is invalid",
                reason_code="video_composer_finalize_boundary_invalid",
            )
        if (
            type(expected_execution_id) is not str
            or not expected_execution_id
            or expected_execution_id != expected_execution_id.strip()
        ):
            raise VideoComposerFinalizeBoundaryError(
                "Video composer finalize boundary requires current execution_id",
                reason_code="video_composer_finalize_boundary_execution_missing",
            )
        execution_id = boundary.get("execution_id")
        if (
            type(execution_id) is not str
            or not execution_id
            or execution_id != execution_id.strip()
            or execution_id != expected_execution_id
        ):
            raise VideoComposerFinalizeBoundaryError(
                "Video composer finalize boundary execution_id does not match",
                reason_code="video_composer_finalize_boundary_execution_mismatch",
            )
        receipt_contract = boundary.get("execution_contract")
        try:
            validated_contract = get_video_composer_execution_contract(
                {"execution_contract": receipt_contract},
                workflow_state_id=expected_workflow_state_id,
            )
        except ValueError as exc:
            raise VideoComposerFinalizeBoundaryError(
                f"Video composer finalize boundary execution_contract is invalid: {exc}",
                reason_code="video_composer_finalize_boundary_identity_mismatch",
            ) from exc
        boundary["execution_contract"] = validated_contract
        for field_name in ("output_path", "output_url"):
            value = boundary.get(field_name)
            if type(value) is not str:
                raise VideoComposerFinalizeBoundaryError(
                    f"Video composer finalize boundary {field_name} must be a string",
                    reason_code="video_composer_finalize_boundary_invalid",
                )
        if not (boundary["output_path"].strip() or boundary["output_url"].strip()):
            raise VideoComposerFinalizeBoundaryError(
                "Video composer finalize boundary has no output reference",
                reason_code="video_composer_finalize_boundary_invalid",
            )
        if not isinstance(boundary.get("receipt_input"), dict):
            raise VideoComposerFinalizeBoundaryError(
                "Video composer finalize boundary receipt_input must be an object",
                reason_code="video_composer_finalize_boundary_invalid",
            )
        return boundary

    async def _execute_action(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        """ACT：执行本轮 FC 返回的工具调用并写回成片事实。"""
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
        execution_contract = boundary["execution_contract"]
        mix_type = boundary["compose_mode"]
        stored_path = mixed_path
        final_url = self._resolve_local_public_url("", stored_path)
        self._remember_finalize_boundary(
            input_data=input_data,
            execution_contract=execution_contract,
            output_path=stored_path,
            output_url=final_url,
        )
        mix_receipt = self._build_mix_receipt(
            input_data=input_data,
            mix_type=mix_type,
            output_path=stored_path,
            output_url=final_url,
        )
        return {
            "success": True,
            "action_performed": "video_composition",
            "final_video_path": stored_path,
            "final_video_url": final_url,
            "mix_receipt": mix_receipt,
            "orchestration_report": self._build_success_orchestration_report(mix_type),
            "executed_calls": executed_calls,
            "plan_llm": plan_llm,
        }

    async def _finalize_success_results(
        self,
        final_action_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = dict(await super()._finalize_success_results(final_action_result, context) or {})
        workflow_id = str(context.get("workflow_state_id") or self.workflow_state_id or "")
        if workflow_id:
            result.setdefault("workflow_state_id", workflow_id)

        finalize_boundary = self._load_finalize_boundary(
            expected_workflow_state_id=workflow_id,
            expected_execution_id=self._get_execution_id() or "",
        )

        final_path = str(finalize_boundary.get("output_path") or "").strip()
        final_url = str(finalize_boundary.get("output_url") or "").strip()
        for field_name, receipt_value in (
            ("final_video_path", final_path),
            ("final_video_url", final_url),
        ):
            candidate = result.get(field_name)
            if candidate is None:
                continue
            if type(candidate) is not str or candidate.strip() != receipt_value:
                raise VideoComposerFinalizeBoundaryError(
                    f"Video composer finalize result {field_name} conflicts with receipt",
                    reason_code="video_composer_finalize_boundary_output_mismatch",
                )

        if final_path:
            result["final_video_path"] = final_path
        if final_url:
            result["final_video_url"] = final_url

        mix_type = get_video_composer_compose_mode(finalize_boundary["execution_contract"])
        receipt_input = finalize_boundary.get("receipt_input")
        receipt_input = dict(receipt_input)

        result["mix_receipt"] = self._build_mix_receipt(
            input_data=receipt_input,
            mix_type=mix_type,
            output_path=final_path,
            output_url=final_url,
        )
        result["orchestration_report"] = self._build_success_orchestration_report(mix_type)

        return result

    async def _reflect_on_results(
        self,
        action_result: Dict[str, Any],
        current_state: Dict[str, Any],
        task: AgentTaskReference,
        iteration: int,
    ) -> Dict[str, Any]:
        ok = bool(action_result.get("success"))
        summary = "合成成功" if ok else "合成未成功"
        return {"success": ok, "reflection_summary": summary}

    def _build_local_serving_url(self, local_path: str) -> str:
        """根据本地存储路径生成可通过 FastAPI 静态目录访问的 URL。"""
        return build_local_public_url(local_path)

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
                payload = (
                    oss_exec[0].get("result")
                    if (oss_exec and isinstance(oss_exec[0], dict))
                    else {}
                ) or {}
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
