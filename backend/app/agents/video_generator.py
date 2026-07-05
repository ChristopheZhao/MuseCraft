"""
Video Generator Agent - 基于 ReAct 的自主迭代实现。

重构目标：
- 移除硬编码流程与工具拦截，让 LLM 在明确先验下自主规划与组合工具；
- 通过 runtime 数据模型隔离业务状态，Agent 仅负责协调 ReAct 循环；
- 依赖工具与记忆模块（consistency_tool、video_prompt_builder 等）完成一致性治理。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .react_agent import ReActAgent
from .base import AgentError
from ..models import AgentType, Task
from ..core.config import settings
 
from ..core.video_config_manager import get_video_config
from .utils import ensure_persisted_videos, make_storage_uploader
from .utils.artifacts import (
    normalize_executed_calls_to_artifacts,
    persist_scene_outputs,
    finalize_scene_outputs,
    evaluate_scene_output_acceptance,
)
from .memory.short_term.working_memory import WorkingMemory
from .utils.progress_snapshot import emit_progress_snapshot
from .utils.memory_helpers import get_mas_working_memory
from ..services.video_execution_contract import get_video_generation_execution_contract



class VideoGeneratorAgent(ReActAgent):
    """ReAct 视频生成 Agent。"""

    def __init__(self, llms=None,memory_services=None):
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            max_iterations=getattr(settings, "VIDEO_GENERATOR_MAX_ITERATIONS", 12),
            timeout_seconds=getattr(settings, "VIDEO_GENERATOR_TIMEOUT_SECONDS", 900),
            llms=llms,
            memory_services=memory_services,
        )
        self.video_config = get_video_config()
        self._video_uploader = None

    # === Working Memory Helpers ==========================================
    def _ensure_working_memory(self, input_data: Dict[str, Any]) -> WorkingMemory:
        workflow_state_id = input_data.get("workflow_state_id")
        if not workflow_state_id:
            raise AgentError("缺少 workflow_state_id")
        # Orchestrator 负责预建；此处只读访问
        return self.wm


    # === PLAN =============================================================
    # 首轮 plan-only 已默认关闭，且不再自定义消息构造

    async def _think_and_plan(
        self,
        current_state: Dict[str, Any],
        task: Task,
        iteration: int,
    ) -> Dict[str, Any]:
        """单段式纯 ReAct：本轮 FC 产出 tool_calls，并在紧随其后的 ACT 中执行。

        设计要点：
        - 不再在 ACT 内进行二次 FC；FC 输出的调用请求不作为跨轮计划状态保存。
        - 工具可见性与参数策略完全由 ToolManager/policy 决定；Agent 不做过滤。
        - 为了给模型充分上下文，优先提供“就绪场景”的批次视图；允许模型在该集合内自主选择并编排调用顺序。
        """
        runtime = self.wm
        if runtime is None:
            raise AgentError("运行时尚未初始化")

        # 通过统一模板构造 PLAN 消息（分区上下文）
        messages = self.build_plan_messages(current_state or {})

        # 单轮 FC：产出 tool_calls 后由同一 ReAct 迭代的 ACT 立即执行。
        fc = await self.llm_function_call(
            messages=messages,
            context_description="video_generation_plan_fc",
            temperature=0.2,
        )

        tool_calls = list(fc.get("tool_calls") or []) if isinstance(fc, dict) else []
        plan_llm = fc.get("llm_response") if isinstance(fc, dict) else None

        # 诊断日志（不干预流程）：计划数量 + 目标场景推断（最多预览若干）
        try:
            scene_numbers: List[int] = []
            for call in tool_calls:
                args = ((call or {}).get("function") or {}).get("arguments") or {}
                if isinstance(args, str):
                    import json as _json
                    try:
                        args = _json.loads(args)
                    except Exception:
                        args = {}
                if isinstance(args, dict) and args.get("scene_number") is not None:
                    try:
                        sn = int(args.get("scene_number")) if str(args.get("scene_number")).isdigit() else None
                        if sn is not None:
                            scene_numbers.append(sn)
                    except Exception:
                        pass
            if scene_numbers:
                self.logger.info(
                    "PLAN: tool_calls=%d scenes=%s",
                    len(tool_calls),
                    scene_numbers[:6],
                )
            else:
                self.logger.info("PLAN: tool_calls=%d", len(tool_calls))
        except Exception:
            pass

        # 关键可观测性：当 tool_calls=0 时，打印本轮 PLAN 文本预览，便于定位“为何未触发工具调用”
        if not tool_calls:
            content = None
            finish_reason = None
            model = None
            provider = None
            if isinstance(plan_llm, dict):
                content = plan_llm.get("content")
                finish_reason = plan_llm.get("finish_reason")
                model = plan_llm.get("model")
                provider = plan_llm.get("provider")
            content_str = (content or "").strip() if isinstance(content, str) else ""
            if content_str:
                preview = content_str
                if len(preview) > 800:
                    preview = preview[:800] + "...(truncated)"
                self.logger.warning(
                    "PLAN_NO_TOOL_CALLS agent=%s iter=%d finish_reason=%s model=%s provider=%s content_preview=%s",
                    self.agent_name,
                    iteration + 1,
                    finish_reason,
                    model,
                    provider,
                    preview,
                )
            else:
                self.logger.warning(
                    "PLAN_NO_TOOL_CALLS agent=%s iter=%d finish_reason=%s model=%s provider=%s (empty content)",
                    self.agent_name,
                    iteration + 1,
                    finish_reason,
                    model,
                    provider,
                )

        # 若未产出任何调用，回到观察，让下一轮根据 WM 事实自纠；否则进入同轮执行阶段。
        if not tool_calls:
            # 无调用：回到观察，让下一轮根据 WM 事实自纠
            return {
                "action": "observe",
                "parameters": {"reason": "no_calls_planned"},
                "plan_llm": plan_llm,
                "reason": "no_calls_planned",
            }

        return {
            "action": "execute_tool_calls",
            "tool_calls": tool_calls,
            "plan_llm": plan_llm,
        }

    # 旧版规划消息/决策路径已移除：改为单次 FC 直接产出 tool_calls

    def _build_retry_soft_hint(self, runtime) -> str:
        """构造“连续失败软提示”（不包含工具名/参数名）。
        当某些场景重试次数已达到阈值时，给出简短提示，供 LLM 在规划时参考。
        """
        threshold = int(getattr(settings, "VIDEO_GENERATOR_FALLBACK_AFTER_RETRIES", 2))
        if threshold <= 0:
            return ""
        pairs: List[Tuple[int, int]] = []
        for sn, cnt in (runtime.retry_counts or {}).items():
            try:
                cnt_i = int(cnt)
            except (TypeError, ValueError):
                continue
            if cnt_i >= threshold:
                try:
                    sn_i = int(sn)
                except (TypeError, ValueError):
                    continue
                pairs.append((sn_i, cnt_i))
        if not pairs:
            return ""
        pairs.sort(key=lambda x: (-x[1], x[0]))
        top = pairs[:5]
        items = ", ".join([f"场景{sn}({cnt}次)" for sn, cnt in top])
        return f"连续失败提示：{items}。建议本轮谨慎安排，优先调整输入策略或暂缓其中部分，避免重复无效尝试。"

    def _build_history_digest(self) -> str:
        # 不再维护跨回合的 agent 内部历史；如需摘要，请从 WM/日志系统派生
        return ""

    # 旧版 plan-only 钩子移除（默认关闭 plan-only 回合）

    # === ACT ==============================================================
    async def _execute_action(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
        db,
        iteration: int,
    ) -> Dict[str, Any]:
        action = action_plan["action"]
        runtime = self.wm
        if runtime is None:
            raise AgentError("运行时尚未初始化")

        if action == "observe":
            # 记录上一轮行为摘要（局部传递，不落入Agent状态）
            try:
                reason = (action_plan.get("parameters") or {}).get("reason")
            except Exception:
                reason = None
            return {"action_performed": "observe", "generation_results": []}

        if action == "complete_task":
            return {
                "action_performed": "task_completed",
                "generation_results": runtime.completed_outputs(),
            }

        if action == "execute_tool_calls":
            params = action_plan.get("parameters", {}) or {}
            tool_calls: List[Dict[str, Any]] = list(
                action_plan.get("tool_calls")
                or action_plan.get("call_tools")
                or params.get("tool_calls")
                or params.get("call_tools")
                or []
            )
            if not tool_calls:
                return {"action_performed": "observe", "generation_results": [], "executed_calls": []}
            plan_llm = action_plan.get("plan_llm") or params.get("plan_llm")
            wf_id = (
                runtime.workflow_state_id
                or input_data.get("workflow_state_id")
                or self.workflow_state_id
            )
            wf_id = str(wf_id) if wf_id else ""
            execution_contract = self._resolve_execution_contract(input_data, wf_id)
            self._validate_video_generation_calls_against_contract(
                tool_calls,
                execution_contract=execution_contract,
            )
            tool_calls = self._bind_execution_context_to_tool_calls(
                tool_calls,
                execution_contract=execution_contract,
            )

            # 执行本轮 FC 产出的调用序列（顺序执行，不做阶段过滤）
            executed_calls = await self.execute_tool_calls(tool_calls)
            # 规范化为 artifacts（视频），随后最小形态映射
            artifacts = normalize_executed_calls_to_artifacts(executed_calls, kind="video", include_prompt=True)
            normalized_results: List[Dict[str, Any]] = []
            for a in artifacts:
                normalized_results.append({
                    "success": True,
                    "scene_number": a.get("scene_number"),
                    "video_url": a.get("video_url", ""),
                    "video_path": a.get("file_path") or a.get("video_path", ""),
                    "prompt_text": a.get("prompt_text", ""),
                    "duration": a.get("duration_sec") or 0,
                    "metadata": {},
                })
            normalized_results = await self._ensure_video_persistence(normalized_results)
            shared_wm = get_mas_working_memory(wf_id, service=self.short_term_service) if wf_id else None
            normalized_results = await persist_scene_outputs(
                artifacts=normalized_results,
                kind="video",
                agent_memory=None,
                shared_memory=shared_wm,
                include_prompt=True,
            )
            delivery_receipts = self._build_delivery_receipts(
                normalized_results,
                workflow_state_id=wf_id,
            )
            try:
                local_count = sum(1 for r in normalized_results if r.get("video_path"))
                url_only = sum(1 for r in normalized_results if r.get("video_url") and not r.get("video_path"))
                self.logger.info(
                    "VIDEO_PERSISTENCE summary: total=%s local_paths=%s url_only=%s",
                    len(normalized_results),
                    local_count,
                    url_only,
                )
            except Exception:
                pass

            # 执行摘要
            success_cnt = sum(1 for r in (normalized_results or []) if r.get("success"))
            self.logger.info(
                "ACT summary: requested=%d executed=%d success=%d",
                len(tool_calls),
                len(executed_calls or []),
                success_cnt,
            )
            return {
                "action_performed": "batch_video_generation",
                "generation_results": normalized_results,
                "executed_calls": executed_calls,
                "delivery_receipts": delivery_receipts,
                "plan_llm": plan_llm,
            }

        raise AgentError(f"未知的动作：{action}")

    

    # 旧版执行消息构造（基于 ready 子集）已废弃：改为使用 build_neutral_act_messages 注入完整 OBS


    

    async def _ensure_video_persistence(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not results:
            return results
        uploader = self._get_video_uploader()
        if not uploader:
            return results
        return await ensure_persisted_videos(results, uploader)

    def _resolve_execution_contract(
        self,
        input_data: Dict[str, Any],
        workflow_id: str,
    ) -> Dict[str, Any]:
        return get_video_generation_execution_contract(
            input_data,
            workflow_state_id=str(workflow_id or ""),
        )

    def _build_execution_context(
        self,
        execution_contract: Dict[str, Any],
    ) -> Dict[str, Any]:
        storage = execution_contract.get("storage") if isinstance(execution_contract, dict) else {}
        if not isinstance(storage, dict):
            storage = {}
        workflow_state_id = str(storage.get("workflow_state_id") or "").strip()
        context: Dict[str, Any] = {
            "execution_contract": dict(execution_contract or {}),
        }
        if workflow_state_id:
            context["workflow_state_id"] = workflow_state_id
        return context

    def _bind_execution_context_to_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        *,
        execution_contract: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        bound_calls: List[Dict[str, Any]] = []
        execution_context = self._build_execution_context(execution_contract)
        for call in tool_calls:
            if not isinstance(call, dict):
                bound_calls.append(call)
                continue
            call_copy = dict(call)
            fn_meta = dict(call_copy.get("function") or {})
            fn_name = str(fn_meta.get("name") or "")
            if not fn_name.startswith("video_generation."):
                bound_calls.append(call_copy)
                continue

            raw_args = fn_meta.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception as exc:
                    raise AgentError(f"视频生成工具参数不是合法 JSON: {exc}") from exc
            elif isinstance(raw_args, dict):
                args = dict(raw_args)
            else:
                args = {}
            if not isinstance(args, dict):
                raise AgentError("视频生成工具参数必须是对象")

            stripped_fields: List[str] = []
            if "workflow_state_id" in args:
                args.pop("workflow_state_id", None)
                stripped_fields.append("workflow_state_id")
            if "generate_audio" in args:
                args.pop("generate_audio", None)
                stripped_fields.append("generate_audio")
            if stripped_fields:
                self.logger.warning(
                    "VIDEO_EXECUTION_BINDING_NORMALIZED fn=%s stripped_fields=%s",
                    fn_name,
                    stripped_fields,
                )
            fn_meta["arguments"] = args
            call_copy["function"] = fn_meta
            call_copy["execution_context"] = dict(execution_context)
            bound_calls.append(call_copy)
        return bound_calls

    def _build_delivery_receipts(
        self,
        results: List[Dict[str, Any]],
        *,
        workflow_state_id: str,
    ) -> List[Dict[str, Any]]:
        receipts: List[Dict[str, Any]] = []
        accepted_at = datetime.now(timezone.utc).isoformat()
        for item in results or []:
            if not isinstance(item, dict) or not item.get("success"):
                continue
            scene_number = item.get("scene_number")
            try:
                scene_number = int(scene_number)
            except Exception:
                continue
            video_url = str(item.get("video_url") or "").strip()
            video_path = str(item.get("video_path") or "").strip()
            if not video_url and not video_path:
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            storage_diag = item.get("storage") if isinstance(item.get("storage"), dict) else {}
            if not storage_diag and isinstance(metadata, dict):
                storage_diag = metadata.get("storage") if isinstance(metadata.get("storage"), dict) else {}
            fallback_reasons = item.get("fallback_reasons") if isinstance(item.get("fallback_reasons"), list) else []
            if not fallback_reasons and isinstance(metadata, dict):
                diagnostics = metadata.get("diagnostics")
                if isinstance(diagnostics, list):
                    fallback_reasons = [
                        str(entry.get("fallback_reason"))
                        for entry in diagnostics
                        if isinstance(entry, dict) and entry.get("fallback_reason")
                    ]
            storage_status = str(storage_diag.get("status") or "").strip().lower() if storage_diag else ""
            storage_fallback_reason = (
                str(storage_diag.get("fallback_reason") or "").strip() if storage_diag else ""
            )
            if (
                not video_path
                and not storage_fallback_reason
                and "artifact_not_persisted" not in fallback_reasons
            ):
                fallback_reasons = list(fallback_reasons) + ["artifact_not_persisted"]
            if storage_fallback_reason and storage_fallback_reason not in fallback_reasons:
                fallback_reasons = list(fallback_reasons) + [storage_fallback_reason]
            is_accepted = bool(video_path) and storage_status != "failed"
            receipt = {
                "scene_number": scene_number,
                "status": "accepted" if is_accepted else "failed",
                "artifact_kind": "video",
                "delivery_surface": "scene_outputs.video",
                "delivery_ref": f"scene_outputs.video.{scene_number}",
                "workflow_state_id": str(workflow_state_id or ""),
            }
            if is_accepted:
                receipt["accepted_at"] = accepted_at
            else:
                receipt["failure_reason"] = storage_fallback_reason or "artifact_not_persisted"
            if storage_diag:
                receipt["storage_status"] = str(storage_diag.get("status") or "")
                if storage_fallback_reason:
                    receipt["storage_fallback_reason"] = storage_fallback_reason
            if fallback_reasons:
                receipt["fallback_reasons"] = sorted(set(str(reason) for reason in fallback_reasons if reason))
            receipts.append(receipt)
        return receipts

    def _collect_accepted_video_scene_numbers(
        self,
        workflow_state_id: str,
    ) -> List[int]:
        agent_memory = None
        if workflow_state_id and getattr(self, "workflow_state_id", None):
            try:
                agent_memory = self.wm
            except Exception:
                agent_memory = None
        contract = evaluate_scene_output_acceptance(
            kind="video",
            workflow_id=workflow_state_id or None,
            agent_memory=agent_memory,
            service=self.short_term_service,
            require_expected_scenes=False,
        )
        return _coerce_int_list(contract.get("accepted_scene_numbers"))

    def _validate_video_generation_calls_against_contract(
        self,
        tool_calls: List[Dict[str, Any]],
        *,
        execution_contract: Dict[str, Any],
    ) -> None:
        if not isinstance(tool_calls, list) or not tool_calls:
            return

        storage = execution_contract.get("storage") if isinstance(execution_contract, dict) else {}
        if not isinstance(storage, dict):
            storage = {}
        constraints = execution_contract.get("constraints") if isinstance(execution_contract, dict) else {}
        if not isinstance(constraints, dict):
            constraints = {}

        required_generate_audio = constraints.get("generate_audio")

        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            fn_meta = call.get("function")
            if not isinstance(fn_meta, dict):
                continue
            fn_name = str(fn_meta.get("name") or "")
            if not fn_name.startswith("video_generation."):
                continue

            raw_args = fn_meta.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception as exc:
                    raise AgentError(f"视频生成工具参数不是合法 JSON: {exc}") from exc
            elif isinstance(raw_args, dict):
                args = dict(raw_args)
            else:
                args = {}
            if not isinstance(args, dict):
                raise AgentError("视频生成工具参数必须是对象")

            expected_workflow_state_id = str(storage.get("workflow_state_id") or "").strip()
            explicit_workflow_state_id = str(args.get("workflow_state_id") or "").strip()
            if explicit_workflow_state_id and expected_workflow_state_id and explicit_workflow_state_id != expected_workflow_state_id:
                raise AgentError(
                    "视频生成调用提供了与 execution context 冲突的 workflow_state_id"
                )

            if isinstance(required_generate_audio, bool):
                actual_generate_audio = args.get("generate_audio")
                if actual_generate_audio is None:
                    continue
                if not isinstance(actual_generate_audio, bool):
                    raise AgentError(
                        "视频生成调用的 generate_audio 必须为 boolean"
                    )
                if bool(actual_generate_audio) != bool(required_generate_audio):
                    raise AgentError(
                        "视频生成调用提供了与 execution context 冲突的 generate_audio"
                    )

    def _get_video_uploader(self):
        if self._video_uploader is not None:
            return self._video_uploader
        if "file_storage_tool" not in self._available_tools:
            self._video_uploader = None
            return None
        prefix = getattr(settings, "VIDEO_GENERATOR_STORAGE_PREFIX", "videos")
        extension = getattr(settings, "VIDEO_GENERATOR_STORAGE_EXTENSION", "mp4")
        self._video_uploader = make_storage_uploader(
            self.use_tool,
            tool_name="file_storage_tool",
            action="upload_from_url",
            destination_prefix=prefix,
            file_extension=extension,
            source_tag=f"{self.agent_name}_persist",
        )
        return self._video_uploader

    def _get_plan_progress_kind(self) -> Optional[str]:
        return "video"

    def _include_execution_contract_in_plan_context(self) -> bool:
        return False

    def _accept_completion_request(
        self,
        *,
        stage: str,
        input_data: Dict[str, Any],
        plan_context: Dict[str, Any],
        iteration_context: Optional[Dict[str, Any]],
        iteration: int,
        plan_contract: Optional[Dict[str, Any]] = None,
        reflection: Optional[Dict[str, Any]] = None,
        action_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        progress_read_model = plan_context.get("progress_read_model") if isinstance(plan_context, dict) else {}
        if not isinstance(progress_read_model, dict):
            progress_read_model = {}
        planned_scene_numbers = _coerce_int_list(progress_read_model.get("planned_scene_numbers"))
        workflow_state_id = str(
            input_data.get("workflow_state_id") or self.workflow_state_id or ""
        ).strip()
        accepted_scene_numbers = self._collect_accepted_video_scene_numbers(workflow_state_id)
        if planned_scene_numbers:
            accepted_set = set(accepted_scene_numbers)
            missing_scene_numbers = [
                scene_number
                for scene_number in planned_scene_numbers
                if scene_number not in accepted_set
            ]
            if not missing_scene_numbers:
                return {
                    "accepted": True,
                    "accepted_scene_numbers": accepted_scene_numbers,
                }
            return {
                "accepted": False,
                "reason": "missing_delivery_acceptance",
                "planned_scene_numbers": planned_scene_numbers,
                "accepted_scene_numbers": accepted_scene_numbers,
                "missing_scene_numbers": missing_scene_numbers,
                "stage": stage,
            }
        return {
            "accepted": False,
            "reason": "planned_scene_membership_missing",
            "planned_scene_numbers": planned_scene_numbers,
            "accepted_scene_numbers": accepted_scene_numbers,
            "stage": stage,
        }

    # === REFLECT ==========================================================
    @emit_progress_snapshot
    async def _reflect_on_results(
        self,
        action_result: Dict[str, Any],
        current_state: Dict[str, Any],
        task: Task,
        iteration: int,
    ) -> Dict[str, Any]:
        performed = action_result.get("action_performed")
        if performed in {"observe"}:
            return {"success": True, "reflection_summary": "本轮仅观察，未执行工具。"}

        completed_now = [r for r in (action_result.get("generation_results") or []) if isinstance(r, dict) and r.get("success")]
        failed_now = [r for r in (action_result.get("generation_results") or []) if isinstance(r, dict) and not r.get("success")]

        summary_bits: List[str] = []
        if completed_now:
            summary_bits.append(f"完成 {len(completed_now)} 个场景")
        if failed_now:
            summary_bits.append(f"{len(failed_now)} 个场景失败")
        summary_text = "；".join(summary_bits) if summary_bits else "本轮无新增产物"
        return {"success": True, "reflection_summary": summary_text}

    # === FINALIZE =========================================================
    async def _finalize_success_results(
        self,
        final_action_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        base = await super()._finalize_success_results(final_action_result, context)
        runtime = self.wm
        wf_id = ""
        if runtime and runtime.workflow_state_id:
            wf_id = str(runtime.workflow_state_id)
        elif context.get("workflow_state_id"):
            wf_id = str(context.get("workflow_state_id"))

        finals, failed = finalize_scene_outputs(
            kind="video",
            workflow_id=wf_id or None,
            agent_memory=self.wm,
        )

        result = dict(base or {})
        if runtime:
            result["workflow_state_id"] = runtime.workflow_state_id
            result["notes"] = list(getattr(runtime, "notes", []))
        result["videos"] = finals
        result["failed"] = failed
        result["final_completed_scenes"] = finals
        result["final_failed_scenes"] = failed
        result["orchestration_report"] = {
            "status": "completed",
            "boundary_event": "scene_video_completed",
            "gate_triggers": ["workflow_video_audio_delivery"],
            "artifacts": [{"kind": "shared_fact", "ref": "scene_outputs.video"}],
            "reflection": {
                "completion_state": "completed",
                "reported_gaps": [],
                "reported_hints": [],
                "completed_scene_count": len(finals),
                "failed_scene_count": len(failed),
            },
        }
        self.reset_iteration_memory_cache()
        return result

    async def _finalize_incomplete_results(
        self,
        context: Dict[str, Any],
        task: Task,
    ) -> Dict[str, Any]:
        base = await super()._finalize_incomplete_results(context, task)
        runtime = self.wm
        wf_id = ""
        if runtime and runtime.workflow_state_id:
            wf_id = str(runtime.workflow_state_id)
        elif context.get("workflow_state_id"):
            wf_id = str(context.get("workflow_state_id"))

        finals, failed = finalize_scene_outputs(
            kind="video",
            workflow_id=wf_id or None,
            agent_memory=self.wm,
        )

        result = dict(base or {})
        if runtime:
            result["workflow_state_id"] = runtime.workflow_state_id
            result["notes"] = list(getattr(runtime, "notes", []))
        result["videos"] = finals
        result["failed"] = failed
        result["final_completed_scenes"] = finals
        result["final_failed_scenes"] = failed
        result["orchestration_report"] = {
            "status": "partial",
            "boundary_event": "scene_video_completed",
            "gate_triggers": ["workflow_video_audio_delivery"],
            "artifacts": [{"kind": "shared_fact", "ref": "scene_outputs.video"}],
            "reflection": {
                "completion_state": str(result.get("subtask_state") or "partial"),
                "reported_gaps": ["scene_video_generation_incomplete"],
                "reported_hints": [],
                "completed_scene_count": len(finals),
                "failed_scene_count": len(failed),
            },
        }
        self.reset_iteration_memory_cache()
        return result

    # === Utilities ========================================================
    # 工具概览描述已移除：遵循 Prompt Neutrality，工具发现交由 FC schema

    # 旧版决策解析/Schema 已移除


def _coerce_int_list(values: Any) -> List[int]:
    if values is None:
        return []
    if not isinstance(values, list):
        try:
            values = list(values) if isinstance(values, (set, tuple)) else [values]
        except Exception:
            values = [values]
    nums: List[int] = []
    for v in values:
        try:
            nums.append(int(v))
        except Exception:
            continue
    return sorted(set(nums))
