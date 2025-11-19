"""
Video Generator Agent - 基于 ReAct 的自主迭代实现。

重构目标：
- 移除硬编码流程与工具拦截，让 LLM 在明确先验下自主规划与组合工具；
- 通过 runtime 数据模型隔离业务状态，Agent 仅负责协调 ReAct 循环；
- 依赖工具与记忆模块（consistency_tool、video_prompt_builder 等）完成一致性治理。
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, Field, validator, ValidationError

from .react_agent import ReActAgent
from .base import AgentError
from ..models import AgentExecution, AgentType, Task
from ..core.config import settings
 
from ..core.video_config_manager import get_video_config
from .utils import ensure_persisted_videos, make_storage_uploader
from .utils.artifacts import normalize_executed_calls_to_artifacts
from .memory.short_term.working_memory import WorkingMemory, SceneArtifact, SceneSnapshot


class PlanningDecision(BaseModel):
    """规划阶段的最小 JSON 契约。"""

    intent: str = Field(..., description="execute | observe | replan | halt")
    selected_units: Optional[List[int]] = Field(
        default=None, description="当 intent=execute 时，需要执行的场景编号"
    )
    plan_digest: str = Field(..., description="当前计划摘要（自由文本）")
    rationale: Optional[str] = Field(default=None)
    adjust_batch_size: Optional[int] = Field(default=None)
    version: Optional[int] = Field(default=None)

    @validator("intent")
    def _check_intent(cls, value: str) -> str:
        allowed = {"execute", "observe", "replan", "halt"}
        if value not in allowed:
            raise ValueError(f"intent must be one of {allowed}")
        return value

    @validator("selected_units", always=True)
    def _validate_selected_units(cls, value: Optional[List[int]], values: Dict[str, Any]):
        if values.get("intent") != "execute":
            return None
        if not value or not isinstance(value, list):
            raise ValueError("selected_units is required when intent=execute")
        dedup: List[int] = []
        seen: Set[int] = set()
        for elem in value:
            if not isinstance(elem, int) or elem <= 0:
                raise ValueError("selected_units must be positive integers")
            if elem in seen:
                continue
            seen.add(elem)
            dedup.append(elem)
        return dedup

    def validate_against_executable(self, executable_ids: Set[int]) -> None:
        if self.intent != "execute":
            return
        missing = [sid for sid in self.selected_units or [] if sid not in executable_ids]
        if missing:
            raise ValueError(f"selected_units not executable: {missing}")


class VideoGeneratorAgent(ReActAgent):
    """ReAct 视频生成 Agent。"""

    def __init__(self, llms=None):
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            max_iterations=getattr(settings, "VIDEO_GENERATOR_MAX_ITERATIONS", 12),
            timeout_seconds=getattr(settings, "VIDEO_GENERATOR_TIMEOUT_SECONDS", 900),
            llms=llms,
        )
        self.video_config = get_video_config()
        self._video_uploader = None

    # === Working Memory Helpers ==========================================
    def _ensure_working_memory(self, input_data: Dict[str, Any]) -> WorkingMemory:
        workflow_state_id = input_data.get("workflow_state_id")
        if not workflow_state_id:
            raise AgentError("缺少 workflow_state_id")
        return self.ensure_iteration_memory(workflow_state_id)


    async def _build_observation_view(self, wm: WorkingMemory) -> Tuple[Dict[str, Any], List[int], List[int]]:
        # 加载该 Agent 的上下文策略（不在 Agent 内做裁剪，仅传递策略给编辑器）
        from ..core.obs_strategy import get_strategy_for_agent
        strategy = get_strategy_for_agent(self.agent_name)

        # 使用 WorkingMemory 导出观测视图；如预算超限则使用 LLM 压缩（严格模式，无兜底）
        observe_llm = self.get_llm("observe")
        target_model = getattr(observe_llm, "_model", None)
        compacted_view, _receipt = await wm.export_observation_async(
            llm=observe_llm,
            strategy=strategy,
            target_model=target_model,
        )
        self.logger.debug(
            "OBS usage_receipt: %s",
            json.dumps({
                "model": _receipt.get("model_name"),
                "budget": _receipt.get("input_budget_tokens"),
                "orig": _receipt.get("original_tokens"),
                "compacted": _receipt.get("compacted"),
                "compacted_tokens": _receipt.get("compacted_tokens"),
                "visible_counts": _receipt.get("visible_counts"),
                "strategy": _receipt.get("strategy"),
            }, ensure_ascii=False),
        )

        # ready/complete 集合
        def _coerce_int_list(values: List[Any]) -> List[int]:
            coerced: List[int] = []
            for val in values:
                if isinstance(val, int):
                    coerced.append(val)
                else:
                    try:
                        coerced.append(int(str(val)))
                    except (TypeError, ValueError):
                        continue
            return coerced

        # 取可见 ready 列表（兼容老键名 ready）
        ready_list = compacted_view.get("ready") or compacted_view.get("visible_ready") or []
        ready_ids_raw = [item.get("scene_number") for item in ready_list if isinstance(item, dict) and item.get("scene_number") is not None]
        ready_ids = _coerce_int_list(ready_ids_raw)

        completed_ids_raw = sorted(wm.completed.keys())
        # 从策略严格读取，不再回退配置项
        from ..core.obs_strategy import get_strategy_for_agent
        _strategy = get_strategy_for_agent(self.agent_name)
        if not isinstance(_strategy, dict) or "completed_limit" not in _strategy:
            raise AgentError("Observation strategy missing 'completed_limit'")
        try:
            completed_limit = int(_strategy.get("completed_limit"))
        except (TypeError, ValueError):
            raise AgentError("Observation strategy 'completed_limit' must be int")
        if completed_limit > 0:
            completed_ids_raw = completed_ids_raw[-completed_limit:]
        completed_ids = _coerce_int_list(completed_ids_raw)

        return compacted_view, ready_ids, completed_ids

    # 已移除：上下文裁剪逻辑由 Context Editor 统一处理

    # === OBSERVE ==========================================================
    async def _observe_current_state(
        self,
        input_data: Dict[str, Any],
        iteration_context: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        runtime = self._ensure_working_memory(input_data)
        summary, _ = runtime.classify_scenes()
        view, ready_ids, completed_ids = await self._build_observation_view(runtime)
        # 供通用日志与归一化使用的轻量场景列表（仅编号与状态），不驱动控制流
        try:
            scenes_min = []
            for sn in sorted(list(runtime.scenes.keys())):
                try:
                    st = runtime._scene_status(int(sn))  # 内部只读调用
                except Exception:
                    st = "ready" if sn in (ready_ids or []) else "pending"
                scenes_min.append({"scene_number": int(sn), "status": st})
        except Exception:
            scenes_min = []
        observation = {
            "summary": summary,
            "view": view,
            "ready_scene_numbers": ready_ids,
            "completed_scene_numbers": completed_ids,
            "notes": runtime.notes[-6:],
            # 仅用于通用观测日志与归一化
            "scenes": scenes_min,
            "completed_count": len(getattr(runtime, 'completed', {}) or {}),
            "failed_count": len(getattr(runtime, 'failed', {}) or {}),
        }
        iteration_context["observation"] = observation
        return observation

    # === PLAN =============================================================
    async def _build_plan_only_messages(
        self,
        input_data: Dict[str, Any],
        current_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        runtime = self._ensure_working_memory(input_data)
        observation = current_state or {}
        return self._build_planning_messages(runtime, observation, plan_only=True)

    async def _think_and_plan(
        self,
        current_state: Dict[str, Any],
        task: Task,
        execution: AgentExecution,
        iteration: int,
    ) -> Dict[str, Any]:
        runtime = self.get_iteration_memory_optional()
        if runtime is None:
            raise AgentError("运行时尚未初始化")
        decision = await self._request_planning_decision(runtime, current_state)
        self.iteration_context["last_decision"] = decision.dict()
        # 规划决策观测日志（简洁，不冗余）
        selected = list(getattr(decision, "selected_units", []) or [])
        preview = selected[:5]
        self.logger.info(
            "PLAN decision: intent=%s selected=%s total=%d",
            getattr(decision, "intent", None),
            preview,
            len(selected),
        )

        if decision.intent == "halt":
            return {"action": "complete_task", "parameters": {}}

        if decision.intent in {"observe", "replan"} or not decision.selected_units:
            return {"action": "observe", "parameters": {}}

        executable = runtime.ready_scene_numbers()
        batch = [sid for sid in decision.selected_units if sid in executable]
        if not batch:
            return {"action": "observe", "parameters": {}}

        return {
            "action": "batch_generate_videos",
            "parameters": {
                "scene_numbers": batch,
                "decision": decision.dict(),
                "observation": current_state,
            },
        }

    async def _request_planning_decision(
        self,
        runtime,
        observation: Dict[str, Any],
    ) -> PlanningDecision:
        messages = self._build_planning_messages(runtime, observation, plan_only=False)
        llm = self.get_llm("plan")
        max_tokens = getattr(settings, "LLM_MAX_TOKENS_STANDARD", 9172)
        response = await llm.chat_completion(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=max_tokens,
        )
        content = (response or {}).get("content")
        if not content:
            raise AgentError("规划阶段未返回内容")
        decision_dict = json.loads(content)
        decision = PlanningDecision(**decision_dict)
        decision.validate_against_executable(set(runtime.ready_scene_numbers()))
        return decision

    def _build_planning_messages(
        self,
        runtime,
        observation: Dict[str, Any],
        plan_only: bool,
    ) -> List[Dict[str, Any]]:
        summary_json = json.dumps(observation.get("summary", {}), ensure_ascii=False, indent=2)
        view_json = json.dumps(observation.get("view", {}), ensure_ascii=False, indent=2)
        ready_ids = observation.get("ready_scene_numbers") or runtime.ready_scene_numbers()
        ready_scene_numbers = ", ".join(str(n) for n in ready_ids) or "无"
        completed_ids = observation.get("completed_scene_numbers") or sorted(runtime.completed.keys())
        completed_scene_numbers = ", ".join(str(n) for n in completed_ids) or "无"
        history_digest = self._build_history_digest()
        decision_schema_json = json.dumps(self._planning_decision_schema(), ensure_ascii=False, indent=2)
        decision_example_json = json.dumps(
            {
                "intent": "execute",
                "selected_units": [1, 2],
                "plan_digest": "示例：优先处理已就绪的两个场景，完成后再评估剩余场景。",
                "rationale": "说明为什么选择该批次，例如保持剧情连贯或资源就绪。",
                "adjust_batch_size": None,
                "version": 1,
            },
            ensure_ascii=False,
            indent=2,
        )

        variables = {
            "goal_text": runtime.goal_text or "",
            "summary_json": summary_json,
            "view_json": view_json,
            "ready_scene_numbers": ready_scene_numbers,
            "completed_scene_numbers": completed_scene_numbers,
            "history_digest": history_digest,
            "max_plan_units_hint": getattr(settings, "VIDEO_GENERATOR_MAX_PLAN_SCENE_NUMS", 2),
            "retry_soft_hint": self._build_retry_soft_hint(runtime),
            "decision_schema": decision_schema_json,
            "decision_example": decision_example_json,
        }

        sys_text = self.prompt_manager.render_template(
            self.agent_name,
            "planning_round",
            variables,
            auto_reload=False,
        )
        if plan_only:
            user_text = "请基于上述事实输出首轮 PlanningDecision（仅 JSON）。"
        else:
            user_text = "请输出严格的 PlanningDecision JSON，不要额外文本。"
        return [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": user_text},
        ]

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
        history = self.iteration_context.get("iteration_history") or []
        if not history:
            return ""
        tail = history[-2:]
        parts: List[str] = []
        for record in tail:
            summary = record.get("action_result_summary") or record.get("reflection", {}).get("reflection_summary")
            if summary:
                parts.append(str(summary))
        return " | ".join(parts)

    async def _on_plan_only_completed(
        self,
        plan_round: Dict[str, Any],
        input_data: Dict[str, Any],
        current_state: Dict[str, Any],
    ) -> None:
        decision = self._extract_decision_from_fc(plan_round)
        if decision:
            self.iteration_context["initial_decision"] = decision.dict()
            # 将首轮规划的目标场景以“plan_only”事实写入 Iter WM，便于下一轮 OBS 可见
            wm = self.get_iteration_memory_optional()
            if wm is not None:
                try:
                    for sid in (decision.selected_units or []):
                        try:
                            sn = int(sid)
                            wm.record_event(scene_number=sn, action="plan_only", success=True)
                        except Exception:
                            continue
                except Exception:
                    pass

    # === ACT ==============================================================
    async def _execute_action(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db,
        iteration: int,
    ) -> Dict[str, Any]:
        action = action_plan["action"]
        runtime = self.get_iteration_memory_optional()
        if runtime is None:
            raise AgentError("运行时尚未初始化")

        if action == "observe":
            return {"action_performed": "observe", "generation_results": []}

        if action == "complete_task":
            return {
                "action_performed": "task_completed",
                "generation_results": runtime.completed_outputs(),
            }

        if action == "batch_generate_videos":
            scene_numbers: List[int] = action_plan["parameters"].get("scene_numbers") or []
            if not scene_numbers:
                return {"action_performed": "observe", "generation_results": []}
            decision = action_plan["parameters"].get("decision") or {}
            messages = self._build_execution_messages(runtime, scene_numbers, decision)
            round_outcome = await self.run_fc_round(
                messages=messages,
                context_description="video_generation",
                temperature=0.2,
            )
            executed_calls = round_outcome.get("executed_calls", []) or []
            # 使用通用规整器，将本轮执行的调用标准化为视频 artifacts，再做最小形态映射
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
            # 精简执行观测日志（不干预主流程）：planned/executed/success
            fc_plan = round_outcome.get("fc_plan") or {}
            planned_cnt = len(fc_plan.get("tool_calls") or []) if isinstance(fc_plan, dict) else 0
            success_cnt = sum(1 for r in (normalized_results or []) if r.get("success"))
            executed_cnt = len(executed_calls or [])
            self.logger.info(
                "ACT summary: planned=%d executed=%d success=%d",
                planned_cnt,
                executed_cnt,
                success_cnt,
            )
            self._integrate_generation_results(runtime, normalized_results)
            return {
                "action_performed": "batch_video_generation",
                "generation_results": normalized_results,
                "executed_calls": executed_calls,
                "llm_react_contract": round_outcome.get("contract"),
            }

        raise AgentError(f"未知的动作：{action}")

    

    def _build_execution_messages(
        self,
        runtime,
        scene_numbers: Sequence[int],
        decision: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        from ..core.obs_strategy import get_strategy_for_agent
        strategy = get_strategy_for_agent(self.agent_name)
        if not isinstance(strategy, dict) or "ready_event_limit" not in strategy:
            raise AgentError("Observation strategy missing 'ready_event_limit'")
        try:
            ready_event_limit = int(strategy.get("ready_event_limit"))
        except (TypeError, ValueError):
            raise AgentError("Observation strategy 'ready_event_limit' must be int")
        batch_view = [
            runtime.scene_view(sid, max_events=ready_event_limit)
            for sid in scene_numbers
            if runtime.has_scene(sid)
        ]
        variables = {
            "goal_text": runtime.goal_text or "",
            "batch_view_json": json.dumps(batch_view, ensure_ascii=False, indent=2),
            "decision_digest": json.dumps(decision or {}, ensure_ascii=False, indent=2),
        }
        sys_text = self.prompt_manager.render_template(
            self.agent_name,
            "execution_round",
            variables,
            auto_reload=False,
        )
        # 记录本轮目标场景，供缺失 scene_number 的容错归属（仅当目标唯一时使用）
        self.iteration_context['last_target_scene_ids'] = list(scene_numbers)
        user_text = "请根据系统提示选择并调用合适的工具完成当前批次场景。仅在必要时调用工具。"
        return [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": user_text},
        ]


    

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

    def _integrate_generation_results(
        self,
        runtime,
        results: List[Dict[str, Any]],
    ) -> None:
        for item in results or []:
            sn = item.get("scene_number")
            if sn is None:
                continue
            if item.get("success"):
                # 若该场景尚未注册到 WM 的场景列表，补充最小快照，确保后续 OBSERVE 能统计到 completed
                try:
                    if not runtime.has_scene(int(sn)):
                        try:
                            dur = float(item.get("duration") or 0)
                        except Exception:
                            dur = 0.0
                        snap = SceneSnapshot(
                            scene_number=int(sn),
                            duration=dur,
                            visual_description="",
                            narrative_description="",
                            image_url=str(item.get("image_url") or ""),
                            motion_beats=[],
                        )
                        runtime.upsert_scene(snap)
                except Exception:
                    pass
                artifact = SceneArtifact(
                    video_url=item.get("video_url", ""),
                    video_path=item.get("video_path", ""),
                    prompt_text=item.get("prompt_text", ""),
                    duration=float(item.get("duration") or 0),
                    metadata=item.get("metadata") or {},
                )
                runtime.mark_completed(int(sn), artifact)
                # 共享记忆（Shared WM）写回：便于后续连续性/合成与断点续跑
                from ..core.config import settings as _cfg
                write_mid = not bool(getattr(_cfg, "REACT_WRITE_WF_ON_COMPLETE_ONLY", True))
                from ..core.config import settings as _cfg2
                if write_mid and not bool(getattr(_cfg2, 'ARTIFACTS_SINGLE_WRITE_MODE', False)):
                    wf_id = runtime.workflow_state_id or self.iteration_context.get("workflow_state_id")
                    if not wf_id:
                        raise AgentError("Shared WM write failed: missing workflow_state_id")
                    from .services.mas_shared_memory import get_shared_wm
                    try:
                        shared = get_shared_wm()
                        shared.register_artifact_ref(
                            str(wf_id),
                            int(sn),
                            artifact,
                        )
                        # 统一写回：将video-only阶段的产物追加到 artifacts 时间线（便于Composer选择最新）
                        self.write_shared_artifact(
                            kind="video",
                            stage="video_only",
                            payload={
                                "file_path": item.get("video_path", ""),
                                "url": item.get("video_url", ""),
                                "duration": item.get("duration"),
                                "prompt_text": item.get("prompt_text", ""),
                                "metadata": item.get("metadata") or {},
                            },
                            scene_number=int(sn),
                            tool="video_generation",
                            workflow_state_id=str(wf_id),
                        )
                    except Exception as e:
                        self.logger.error("Shared WM mid-write failed for scene=%s: %s", sn, e, exc_info=True)
                        raise AgentError("Shared WM write failed (mid-iteration)") from e
            else:
                reason = item.get("error") or "video_generation_failed"
                # 依据可配置错误类型判定是否允许重试（默认允许）
                err_type = (item.get("metadata") or {}).get("error_type") or item.get("error_type")
                hard_block_types = set(getattr(settings, "REACT_HARD_BLOCK_ERROR_TYPES", []) or [])
                retryable = not (err_type in hard_block_types)
                runtime.mark_failed(int(sn), reason, item.get("metadata"), retryable=retryable)

    # === REFLECT ==========================================================
    async def _reflect_on_results(
        self,
        action_result: Dict[str, Any],
        current_state: Dict[str, Any],
        task: Task,
        iteration: int,
    ) -> Dict[str, Any]:
        runtime = self.get_iteration_memory_optional()
        if runtime is None:
            return {"success": True, "task_complete": False, "should_stop": False, "context_updates": {}, "reflection_summary": "无运行时"}

        performed = action_result.get("action_performed")
        if performed in {"observe"}:
            return {
                "success": True,
                "task_complete": False,
                "should_stop": False,
                "context_updates": {},
                "reflection_summary": "本轮仅观察，未执行工具。",
            }
        if performed == "task_completed":
            return {
                "success": True,
                "task_complete": True,
                "should_stop": True,
                "context_updates": {},
                "reflection_summary": "任务已完成。",
            }

        completed_now = [r for r in action_result.get("generation_results", []) if r.get("success")]
        failed_now = [r for r in action_result.get("generation_results", []) if not r.get("success")]

        summary_bits: List[str] = []
        if completed_now:
            summary_bits.append(f"完成 {len(completed_now)} 个场景")
        if failed_now:
            summary_bits.append(f"{len(failed_now)} 个场景失败")
        summary_text = "；".join(summary_bits) if summary_bits else "本轮无新增产物"

        summary, _ = runtime.classify_scenes()
        total = int(summary.get("total", 0) or 0)
        completed = int(summary.get("completed", 0) or 0)
        task_complete = total == 0 or completed >= total
        return {
            "success": True,
            "task_complete": task_complete,
            "should_stop": task_complete,
            "context_updates": {},
            "reflection_summary": summary_text,
        }

    # === FINALIZE =========================================================
    async def _finalize_success_results(
        self,
        final_action_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        base = await super()._finalize_success_results(final_action_result, context)
        runtime = self.get_iteration_memory_optional()
        finals, failed = self._build_final_scene_records(runtime)

        result = dict(base or {})
        if runtime:
            result["workflow_state_id"] = runtime.workflow_state_id
            result["notes"] = list(getattr(runtime, "notes", []))
            result["videos"] = runtime.completed_outputs()
            result["failed"] = runtime.failed_outputs()
        else:
            result.setdefault("videos", [])
            result.setdefault("failed", [])
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
        runtime = self.get_iteration_memory_optional()
        finals, failed = self._build_final_scene_records(runtime)

        result = dict(base or {})
        if runtime:
            result["workflow_state_id"] = runtime.workflow_state_id
            result["notes"] = list(getattr(runtime, "notes", []))
            result["videos"] = runtime.completed_outputs()
            result["failed"] = runtime.failed_outputs()
        else:
            result.setdefault("videos", [])
            result.setdefault("failed", [])
        result["final_completed_scenes"] = finals
        result["final_failed_scenes"] = failed
        self.reset_iteration_memory_cache()
        return result

    def _build_final_scene_records(
        self, runtime
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if runtime is None:
            return [], []

        finals: List[Dict[str, Any]] = []
        for scene_number, artifact in sorted(runtime.completed.items(), key=lambda item: item[0]):
            finals.append(
                {
                    "scene_number": scene_number,
                    "video_url": artifact.video_url,
                    "video_path": artifact.video_path,
                    "prompt_text": artifact.prompt_text,
                }
            )

        failed: List[Dict[str, Any]] = []
        for scene_number, info in sorted(runtime.failed.items(), key=lambda item: item[0]):
            failed.append(
                {
                    "scene_number": scene_number,
                    "error": info.get("reason"),
                    "metadata": info.get("metadata", {}),
                }
            )
        return finals, failed

    # === Utilities ========================================================
    # 工具概览描述已移除：遵循 Prompt Neutrality，工具发现交由 FC schema

    def _extract_decision_from_fc(self, fc_payload: Dict[str, Any]) -> Optional[PlanningDecision]:
        fc_plan = fc_payload.get("fc_plan") if isinstance(fc_payload, dict) else None
        if not isinstance(fc_plan, dict):
            return None
        content = None
        llm_resp = fc_plan.get("llm_response")
        if isinstance(llm_resp, dict):
            content = llm_resp.get("content")
        if not content:
            content = fc_plan.get("content")
        if not content:
            return None
        text = self._strip_code_fence(content)
        if not text:
            return None
        try:
            data = json.loads(text)
            return PlanningDecision(**data)
        except (json.JSONDecodeError, ValidationError):
            return None

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            first_line = text.split("\n", 1)[0]
            if first_line.startswith("```json"):
                text = text[len(first_line):].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        return text

    @staticmethod
    def _planning_decision_schema() -> Dict[str, Any]:
        try:
            return PlanningDecision.model_json_schema()
        except AttributeError:
            return PlanningDecision.schema()
