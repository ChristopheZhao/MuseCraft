"""
Video Generator Agent - 基于 ReAct 的自主迭代实现。

重构目标：
- 移除硬编码流程与工具拦截，让 LLM 在明确先验下自主规划与组合工具；
- 通过 runtime 数据模型隔离业务状态，Agent 仅负责协调 ReAct 循环；
- 依赖工具与记忆模块（consistency_tool、video_prompt_builder 等）完成一致性治理。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

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
)
from .memory.short_term.working_memory import WorkingMemory
from .utils.progress_snapshot import emit_progress_snapshot
from .utils.memory_helpers import get_mas_working_memory



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
        """单段式纯 ReAct：在 PLAN 阶段一次 FC 产出完整 tool_calls，ACT 仅执行。

        设计要点：
        - 不再在 ACT 内进行二次 FC；PLAN 即产出调用清单（如无调用则返回合同 JSON）。
        - 工具可见性与参数策略完全由 ToolManager/policy 决定；Agent 不做过滤。
        - 为了给模型充分上下文，优先提供“就绪场景”的批次视图；允许模型在该集合内自主选择并编排调用顺序。
        """
        runtime = self.wm
        if runtime is None:
            raise AgentError("运行时尚未初始化")

        # 通过统一模板构造 PLAN 消息（分区上下文）
        messages = self.build_plan_messages(current_state or {})

        # 仅规划：调用 FC 获取 tool_calls，不执行
        fc = await self.llm_function_call(
            messages=messages,
            context_description="video_generation_plan_fc",
            temperature=0.2,
        )

        planned_calls = list(fc.get("tool_calls") or []) if isinstance(fc, dict) else []
        plan_llm = fc.get("llm_response") if isinstance(fc, dict) else None

        # 诊断日志（不干预流程）：计划数量 + 目标场景推断（最多预览若干）
        try:
            scene_numbers: List[int] = []
            for call in planned_calls:
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
                    len(planned_calls),
                    scene_numbers[:6],
                )
            else:
                self.logger.info("PLAN: tool_calls=%d", len(planned_calls))
        except Exception:
            pass

        # 关键可观测性：当 tool_calls=0 时，打印本轮 PLAN 文本预览，便于定位“为何未触发工具调用”
        if not planned_calls:
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

        # 若未产出任何调用，尝试解析合同 JSON 作为回退；否则进入执行阶段
        if not planned_calls:
            # 无调用：回到观察，让下一轮根据 WM 事实自纠
            return {
                "action": "observe",
                "parameters": {"reason": "no_calls_planned"},
                "plan_llm": plan_llm,
                "reason": "no_calls_planned",
            }

        return {
            "action": "execute_planned_calls",
            "tool_calls": planned_calls,
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

        if action == "execute_planned_calls":
            params = action_plan.get("parameters", {}) or {}
            planned_calls: List[Dict[str, Any]] = list(
                action_plan.get("tool_calls")
                or action_plan.get("call_tools")
                or params.get("tool_calls")
                or params.get("call_tools")
                or []
            )
            if not planned_calls:
                return {"action_performed": "observe", "generation_results": [], "executed_calls": []}
            plan_llm = action_plan.get("plan_llm") or params.get("plan_llm")
            wf_id = (
                runtime.workflow_state_id
                or input_data.get("workflow_state_id")
                or self.workflow_state_id
            )
            wf_id = str(wf_id) if wf_id else ""

            # 执行规划好的调用序列（顺序执行，不做阶段过滤）
            executed_calls = await self.execute_tool_calls(planned_calls)
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

            # 执行摘要
            success_cnt = sum(1 for r in (normalized_results or []) if r.get("success"))
            self.logger.info(
                "ACT summary: planned=%d executed=%d success=%d",
                len(planned_calls),
                len(executed_calls or []),
                success_cnt,
            )
            return {
                "action_performed": "batch_video_generation",
                "generation_results": normalized_results,
                "executed_calls": executed_calls,
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
