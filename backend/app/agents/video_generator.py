"""
Video Generator Agent - ReAct with autonomous FC parameter selection
"""
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass
import json as _json
import re
import time

from sqlalchemy.orm import Session

from .react_agent import ReActAgent
from .base import AgentError
from ..models import Task, AgentExecution, AgentType
from ..core.video_config_manager import get_video_config
from ..core.consistency_policy import get_consistency_policy
from ..core.config import settings
from ..core.scene_continuity_memory import get_scene_continuity_memory

# ===== Strict planning/reflection schemas (T2) =====
from pydantic import BaseModel, Field, validator


@dataclass
class ConstraintMergeResult:
    locked: List[str]
    suggestions: List[str]
    flattened: List[str]


class PlanningDecision(BaseModel):
    intent: str = Field(..., description="execute | observe | replan | halt")
    selected_units: Optional[List[int]] = Field(
        default=None, description="IDs for next execution batch when intent=execute"
    )
    adjust_batch_size: Optional[int] = Field(default=None)
    plan_update: Optional[Dict[str, Any]] = Field(default=None)
    plan_digest: str = Field(...)
    rationale: Optional[str] = Field(default=None)
    version: Optional[int] = Field(default=None)

    @validator("intent")
    def _check_intent(cls, v: str) -> str:
        allowed = {"execute", "observe", "replan", "halt"}
        if v not in allowed:
            raise ValueError(f"intent must be one of {allowed}")
        return v

    @validator("selected_units", always=True)
    def _check_selected_units(cls, v: Optional[List[int]], values: Dict[str, Any]):
        intent = values.get("intent")
        if intent == "execute":
            if not v or not isinstance(v, list):
                raise ValueError("selected_units is required when intent=execute")
            # unique positive ints
            s = []
            seen = set()
            for x in v:
                if not isinstance(x, int) or x <= 0:
                    raise ValueError("selected_units must be positive integers")
                if x in seen:
                    continue
                seen.add(x)
                s.append(x)
            return s
        else:
            # when not execute, selected_units should be None or empty list
            return None

    def validate_against_executable(self, executable_ids: Set[int]) -> None:
        if self.intent == "execute":
            missing = [x for x in (self.selected_units or []) if x not in executable_ids]
            if missing:
                raise ValueError(f"selected_units not executable: {missing}")


class ReflectionResult(BaseModel):
    progress_state: str = Field(..., description="no_progress | partial | complete")
    newly_completed: int = Field(..., ge=0)
    failed_units: List[int] = Field(default_factory=list)
    blocked_units: List[Dict[str, Any]] = Field(default_factory=list)
    halt_recommendation: bool = Field(...)
    reason: Optional[str] = Field(default=None)
    plan_update: Optional[Dict[str, Any]] = Field(default=None)
    evidence_digest: Optional[str] = Field(default=None)

    @validator("progress_state")
    def _check_state(cls, v: str) -> str:
        allowed = {"no_progress", "partial", "complete"}
        if v not in allowed:
            raise ValueError(f"progress_state must be one of {allowed}")
        return v

    @validator("failed_units")
    def _check_failed_units(cls, v: List[int]) -> List[int]:
        for x in v:
            if not isinstance(x, int) or x <= 0:
                raise ValueError("failed_units must be positive integers")
        return list(dict.fromkeys(v))



class VideoGeneratorAgent(ReActAgent):
    """
    Video Generator (ReAct)
    - OBSERVE: derive executable scenes and dependencies from working state
    - THINK/PLAN: batching strategy
    - ACT: FC chooses tools/parameters (no pre-optimization)
    - REFLECT: merge results, decide continuation
    """

    def __init__(self, llms=None):
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            max_iterations=settings.VIDEO_GENERATOR_MAX_ITERATIONS,
            timeout_seconds=getattr(settings, 'VIDEO_GENERATOR_TIMEOUT_SECONDS', 900),
            llms=llms,
        )
        self.video_config = get_video_config()
        self.max_image_regen_attempts = 2

    def _build_tool_context(self, tool_name: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """扩展工具上下文，向执行层提供连续性所需信息。"""
        context = super()._build_tool_context(tool_name, action, parameters)
        try:
            ws = self.iteration_context.get('working_state', {}) or {}
        except Exception:
            ws = {}
        ctx = ws.get('context') if isinstance(ws, dict) else {}
        wf_id = ctx.get('workflow_state_id') if isinstance(ctx, dict) else None
        if not wf_id:
            wf_id = self.iteration_context.get('workflow_state_id')
        if tool_name == 'video_generation':
            try:
                prepared = ws.get('prepared_last_frames') if isinstance(ws, dict) else None
                current_batch = ws.get('current_batch') if isinstance(ws, dict) else None
                context.update({
                    'workflow_state_id': wf_id,
                    'prepared_last_frames': prepared or {},
                    'current_batch': current_batch or [],
                    'force_generate_only': bool(self.iteration_context.get('force_generate_only')),
                    'target_resolution': self.iteration_context.get('target_resolution'),
                })
            except Exception:
                context.setdefault('workflow_state_id', wf_id)
        elif tool_name == 'scene_continuity_preparation':
            try:
                prepared = ws.get('prepared_last_frames') if isinstance(ws, dict) else None
                context.update({
                    'workflow_state_id': wf_id,
                    'prepared_last_frames': prepared or {},
                })
            except Exception:
                context.setdefault('workflow_state_id', wf_id)
        return context

    # ==== PLAN/OBSERVE ====
    def _get_goal_text(self, workflow_state_id: Optional[str]) -> str:
        if not workflow_state_id:
            raise AgentError("缺少 workflow_state_id，无法提取任务目标(goal_text)")
        try:
            from ..core.workflow_state import workflow_manager
            wf = workflow_manager.get_workflow(workflow_state_id)
            goal = getattr(wf, 'user_prompt', None)
            if isinstance(goal, str) and goal.strip():
                return goal.strip()
        except Exception as e:
            raise AgentError(f"读取 WorkflowState 失败: {e}")
        raise AgentError("无法从 WorkflowState 读取用户目标(user_prompt)")

    def _get_constraints_snapshot(self) -> Dict[str, Any]:
        try:
            pcfg = self.video_config.get_current_provider_config()
            return {
                "provider": getattr(pcfg, 'provider_name', ''),
                "model": getattr(pcfg, 'model_name', ''),
                "duration_options": list(getattr(pcfg, 'duration_capabilities', []) or []),
                "max_duration": getattr(pcfg, 'max_duration', None),
                "default_duration": getattr(pcfg, 'default_duration', None),
                "supports_first_last_frame": getattr(pcfg, 'supports_first_last_frame', None),
            }
        except Exception as e:
            raise AgentError(f"读取视频提供商约束失败: {e}")

    def _extract_executable_ids(self, current_state: Dict[str, Any]) -> Set[int]:
        ids: Set[int] = set()
        for s in current_state.get("executable_scenes", []) or []:
            try:
                sn = s.get("scene_number")
                if sn is not None:
                    ids.add(int(sn))
            except Exception:
                continue
        return ids

    @staticmethod
    def _planning_decision_schema() -> Dict[str, Any]:
        """统一的 PlanningDecision JSON Schema。"""
        return {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": ["execute", "observe", "replan", "halt"]},
                "selected_units": {"type": ["array", "null"], "items": {"type": "integer"}},
                "adjust_batch_size": {"type": ["integer", "null"]},
                "plan_update": {"type": ["object", "null"]},
                "plan_digest": {"type": "string"},
                "rationale": {"type": ["string", "null"]},
                "version": {"type": ["integer", "null"]}
            },
            "required": ["intent", "plan_digest"]
        }

    async def _planning_round0(self, current_state: Dict[str, Any]) -> Dict[str, Any]:
        # 构造模板变量
        ws = self.iteration_context.get("working_state", {}) or {}
        ctx = ws.get("context", {}) or {}
        wf_id = ctx.get("workflow_state_id")
        goal_text = self._get_goal_text(wf_id)
        constraints = self._get_constraints_snapshot()
        scenes = ctx.get("scenes_to_generate", []) or []
        if not scenes:
            raise AgentError("没有可用的 scenes_to_generate，无法进行首轮规划")
        variables = {
            "goal_text": goal_text,
            "constraints_json": _json.dumps(constraints, ensure_ascii=False),
            "scenes_json": _json.dumps(scenes, ensure_ascii=False),
        }
        # 渲染模板并请求结构化 JSON
        try:
            sys_text = self.prompt_manager.render_template(self.agent_name, "planning_round0", variables, auto_reload=False)
        except Exception as e:
            raise AgentError(f"首轮规划模板渲染失败: {e}")
        messages = [{"role": "system", "content": sys_text}]
        # 补充最小 user 提示，满足Zhipu对messages结构的要求（至少一条user）
        messages.append({
            "role": "user",
            "content": "请严格按上面的系统指令，仅输出一个严格的总体规划 JSON（不要额外文字/不要代码围栏）。"
        })
        schema = self._planning_decision_schema()
        data = await self.llm_structured_observation(messages, schema)
        if not isinstance(data, dict):
            raise AgentError("首轮规划未返回有效JSON")
        try:
            decision = PlanningDecision(**data)
        except Exception as e:
            raise AgentError(f"首轮规划JSON不符合Schema: {e}")
        # 校验与可执行集合一致
        decision.validate_against_executable(self._extract_executable_ids(current_state))
        return decision.dict()

    async def _planning_roundN(self, current_state: Dict[str, Any]) -> Dict[str, Any]:
        ws = self.iteration_context.get("working_state", {}) or {}
        ctx = ws.get("context", {}) or {}
        aop = ctx.get("agent_overall_plan", {}) or {}
        plan_digest = str(aop.get("plan_digest", ""))
        if not plan_digest:
            raise AgentError("缺少 agent_overall_plan.plan_digest，无法进行滚动规划")
        # 计划纲要（截断）
        try:
            steps = aop.get("steps") or aop.get("stages") or []
            outline = steps[:6]
            plan_outline = _json.dumps(outline, ensure_ascii=False)
        except Exception:
            plan_outline = "[]"
        progress_summary = self.build_progress_summary() or ""
        scratchpad = self.build_scratchpad(k=2) or ""
        observation_json = _json.dumps(current_state, ensure_ascii=False)
        variables = {
            "plan_digest": plan_digest,
            "plan_outline": plan_outline,
            "progress_summary": progress_summary,
            "scratchpad": scratchpad,
            "observation_json": observation_json,
        }
        try:
            sys_text = self.prompt_manager.render_template(self.agent_name, "planning_roundN", variables, auto_reload=False)
        except Exception as e:
            raise AgentError(f"滚动规划模板渲染失败: {e}")
        messages = [{"role": "system", "content": sys_text}]
        # 补充最小 user 提示，避免仅system导致的400（messages参数非法）。
        messages.append({
            "role": "user",
            "content": "请基于上述信息进行本轮决策：文本部分仅输出严格的 PlanningDecision JSON（不要其他文字/围栏）。"
        })
        try:
            system_len = len(sys_text)
            user_len = len(messages[-1].get("content", ""))
            observation_len = len(observation_json)
            total_len = sum(
                len(msg.get("content", ""))
                for msg in messages
                if isinstance(msg, dict) and isinstance(msg.get("content"), str)
            )
            self.logger.info(
                "PLAN_PROMPT_LEN: system=%d user=%d observation_json=%d total=%d",
                system_len,
                user_len,
                observation_len,
                total_len,
            )
        except Exception:
            pass
        schema = self._planning_decision_schema()
        data = await self.llm_structured_observation(messages, schema)
        if not isinstance(data, dict):
            raise AgentError("滚动规划未返回有效JSON")
        try:
            decision = PlanningDecision(**data)
        except Exception as e:
            raise AgentError(f"滚动规划JSON不符合Schema: {e}")
        decision.validate_against_executable(self._extract_executable_ids(current_state))
        return decision.dict()

    async def _plan_execution_initial(self, task: Task, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize working state from workflow"""
        self._validate_input(input_data, ["workflow_state_id"])
        workflow_state_id = input_data["workflow_state_id"]

        from ..core.workflow_state import workflow_manager
        workflow_state_obj = workflow_manager.get_workflow(workflow_state_id)
        scenes_data = workflow_state_obj.scenes if workflow_state_obj else []

        scenes_to_generate: List[Dict[str, Any]] = []
        independent_scenes: List[Dict[str, Any]] = []
        dependent_scenes: List[Dict[str, Any]] = []

        for scene in scenes_data:
            depends_on_scene = getattr(scene, 'depends_on_scene', None)
            visual_description = (getattr(scene, 'visual_description', '') or '').strip()
            if not visual_description:
                raise AgentError(
                    f"workflow_scene_{getattr(scene, 'scene_number', '?')} 缺少 visual_description，无法初始化视频生成任务"
                )

            script_text = (getattr(scene, 'script_text', '') or '').strip()
            narrative_description = (getattr(scene, 'narrative_description', '') or '').strip()
            action_sequence_description = (
                getattr(scene, 'action_sequence_description', '') or ''
            ).strip()
            timing_structure_description = (
                getattr(scene, 'timing_structure_description', '') or ''
            ).strip()
            initial_state_description = (
                getattr(scene, 'initial_state_description', '') or ''
            ).strip()
            target_outcome_description = (
                getattr(scene, 'target_outcome_description', '') or ''
            ).strip()
            complete_video_description = (
                getattr(scene, 'complete_video_description', '') or ''
            ).strip()

            info = {
                "scene_number": scene.scene_number,
                "title": getattr(scene, 'title', ''),
                "visual_description": visual_description,
                "duration": getattr(scene, 'duration', 5),
                "depends_on_scene": depends_on_scene,
                "image_url": getattr(scene, 'image_url', ''),
                "video_url": getattr(scene, 'video_url', ''),
                "narrative_description": narrative_description,
                "script_text": script_text,
                "action_sequence_description": action_sequence_description,
                "timing_structure_description": timing_structure_description,
                "motion_beats": getattr(scene, 'motion_beats', []),
                "initial_state_description": initial_state_description,
                "target_outcome_description": target_outcome_description,
                "complete_video_description": complete_video_description,
            }

            if not any(
                [
                    script_text,
                    action_sequence_description,
                    timing_structure_description,
                    complete_video_description,
                ]
            ):
                try:
                    self.logger.warning(
                        "SCENE_CONTEXT_GAP: scene=%s 缺少脚本/动作节奏信息，仅有视觉语境。请检查上游 Script/Concept 输出。",
                        scene.scene_number,
                    )
                except Exception:
                    pass

            scenes_to_generate.append(info)
            (dependent_scenes if depends_on_scene else independent_scenes).append(info)

        task_context = {
            "task_type": "batch_video_generation",
            "total_scenes": len(scenes_data),
            "scenes_to_generate": scenes_to_generate,
            "independent_scenes": independent_scenes,
            "dependent_scenes": dependent_scenes,
            "workflow_state_id": workflow_state_id,
            "video_config": self.video_config.get_current_provider_config().__dict__,
            "target_resolution": input_data.get("resolution") or settings.DEFAULT_VIDEO_RESOLUTION,
            # 提前挂入概念计划（若可用），便于执行期读取 per-scene 角色出现
            "concept_plan": input_data.get("concept_plan")
                if isinstance(input_data, dict) and input_data.get("concept_plan") is not None
                else (getattr(workflow_state_obj, 'concept_plan', None) if workflow_state_obj else None),
        }

        try:
            self.iteration_context['target_resolution'] = task_context.get("target_resolution")
        except Exception:
            pass

        return {
            "plan": "",
            "context": task_context,
            "completed_scenes": {},  # scene_number -> result
            "failed_scenes": [],
            "current_batch": [],
            # inner_react_state 扩展：结果台账与迭代历史（跨轮累积，任务级保留）
            "results_ledger": [],
            "iteration_history": [],
        }

    async def _observe_current_state(
        self,
        input_data: Dict[str, Any],
        context: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        try:
            self.iteration_context['source_input'] = input_data
        except Exception:
            pass
        working_state = self.iteration_context.get("working_state")
        if working_state is None:
            working_state = await self._plan_execution_initial(self._current_task, input_data)
            self.iteration_context["working_state"] = working_state

        # merge any react updates
        try:
            ws = dict(self.iteration_context.get("working_state", {}) or {})
            ws = self.merge_react_state_into(ws)
            self.iteration_context["working_state"] = ws
            working_state = ws
        except Exception:
            pass

        return await self._observe_state_internal(working_state)

    async def _observe_state_internal(self, workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        # 注：workflow_state 即内部 inner_react_state（跨轮累积的内部状态），非外部 WF
        context = workflow_state.get("context", {})
        scenes_to_generate = context.get("scenes_to_generate", []) or []
        independent_scenes = context.get("independent_scenes", []) or []
        dependent_scenes = context.get("dependent_scenes", []) or []

        completed_scenes = workflow_state.get("completed_scenes", {}) or {}
        failed_scenes = workflow_state.get("failed_scenes", []) or []
        
        # 完成集合来源：默认仅使用内部 inner_react_state（符合分层原则）
        completed_scene_numbers_internal: set = set()
        try:
            if isinstance(completed_scenes, dict):
                for k, v in completed_scenes.items():
                    try:
                        if isinstance(v, dict) and (v.get('video_url') or v.get('video_path')):
                            completed_scene_numbers_internal.add(int(k))
                    except Exception:
                        continue
            elif isinstance(completed_scenes, list):
                for it in completed_scenes:
                    try:
                        sn = int(it.get('scene_number')) if isinstance(it, dict) and it.get('scene_number') is not None else None
                        if sn is not None and (it.get('video_url') or it.get('video_path')):
                            completed_scene_numbers_internal.add(sn)
                    except Exception:
                        continue
        except Exception:
            pass
        # 可选并集：仅用于兼容阶段；若策略需要，可将外部 WF 的完成资产合并入完成集合（不推荐）
        completed_scene_numbers = set(completed_scene_numbers_internal)
        try:
            from ..core.config import settings as _cfg
            source = getattr(_cfg, 'REACT_OBSERVE_COMPLETION_SOURCE', 'internal')
            if str(source).lower() != 'internal':
                try:
                    from ..core.workflow_state import workflow_manager
                    wf_id = context.get("workflow_state_id")
                    wf = workflow_manager.get_workflow(wf_id) if wf_id else None
                    if wf:
                        for sc in getattr(wf, 'scenes', []) or []:
                            try:
                                sn = int(getattr(sc, 'scene_number', 0) or 0)
                                vu = getattr(sc, 'video_url', '') or ''
                                vp = getattr(sc, 'video_path', '') or ''
                                if sn and (vu or vp):
                                    completed_scene_numbers.add(sn)
                            except Exception:
                                continue
                except Exception:
                    pass
        except Exception:
            pass
        failed_scene_numbers = {s.get("scene_number") for s in failed_scenes if isinstance(s, dict)}

        pending_regen_map, blocked_for_regen = self._extract_pending_image_regen(workflow_state, sanitize=True)

        # independent scenes pending
        # 独立场景：失败不做永久排除，允许后续轮次重试
        pending_independent = [
            s for s in independent_scenes
            if s.get("scene_number") not in completed_scene_numbers
            and self._normalize_scene_number(s.get('scene_number')) not in blocked_for_regen
        ]

        executable_dependent: List[Dict[str, Any]] = []
        pending_dependent: List[Dict[str, Any]] = []
        for s in dependent_scenes:
            sn = s.get("scene_number")
            # 失败不做永久排除，允许后续轮次重试
            if sn in completed_scene_numbers:
                continue
            if self._normalize_scene_number(sn) in blocked_for_regen:
                continue
            dep = s.get("depends_on_scene")
            if dep in completed_scene_numbers:
                executable_dependent.append(s)
            else:
                pending_dependent.append(s)

        executable_scenes = pending_independent + executable_dependent
        # 若存在优先执行队列（已准备连续性帧），将对应场景置顶排序
        try:
            pr_ids = list(workflow_state.get('priority_prepared_ids') or [])
            if pr_ids:
                def _prio_key(s):
                    sn = s.get('scene_number')
                    try:
                        return (0 if sn in pr_ids else 1, pr_ids.index(sn) if sn in pr_ids else 9999)
                    except Exception:
                        return (1, 9999)
                executable_scenes = sorted(executable_scenes, key=_prio_key)
        except Exception:
            pass

        total_targets = len(scenes_to_generate)
        observation = {
            "total_scenes": total_targets,
            # 口径统一：completed_count 以内部 inner_react_state 为准
            "completed_count": len(completed_scene_numbers_internal),
            "failed_count": len(failed_scenes),
            "executable_count": len(executable_scenes),
            "pending_dependent_count": len(pending_dependent),
            "executable_scenes": executable_scenes,
            "pending_dependent_scenes": pending_dependent,
            "pending_image_regen": pending_regen_map,
            "blocked_scenes": [
                {
                    "scene_number": sn,
                    **(pending_regen_map.get(sn) or {}),
                }
                for sn in sorted(blocked_for_regen)
            ],
            # 完成门槛：无可执行且无待依赖，且无失败，且完成数达到目标
            "task_status": (
                "completed"
                if (not executable_scenes and not pending_dependent and len(failed_scenes) == 0 and len(completed_scene_numbers_internal) >= total_targets)
                else "in_progress"
            ),
        }
        try:
            self.logger.info(
                f"OBS_STATE: executable={len(executable_scenes)} pending_dep={len(pending_dependent)} "
                f"completed_internal={len(completed_scene_numbers_internal)} failed={len(failed_scenes)}"
            )
        except Exception:
            pass
        # 记录最近一次观察，供后续 planning_roundN 模板使用
        try:
            self.iteration_context["last_observation"] = observation
        except Exception:
            pass
        return observation

    # ==== THINK/PLAN ====
    async def _think_and_reason(
        self,
        observation: Dict[str, Any],
        workflow_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        executable_scenes = observation.get("executable_scenes", []) or []
        pending_dependent = observation.get("pending_dependent_scenes", []) or []
        if observation.get("task_status") == "completed":
            return {"strategy": "complete_task", "reasoning": "all done", "action_needed": False}
        if not executable_scenes:
            if pending_dependent:
                return {
                    "strategy": "wait_for_dependencies",
                    "reasoning": f"waiting for {len(pending_dependent)} deps",
                    "action_needed": False,
                    "pending_scenes": pending_dependent,
                }
            return {"strategy": "complete_task", "reasoning": "nothing to do", "action_needed": False}

        ctx = workflow_state.get("context", {})
        video_config = ctx.get("video_config", {})
        # 合并式路径：不在此处做裁剪，由 FC 的 planning_roundN 选择 selected_units
        return {
            "strategy": "rolling_plan",
            "reasoning": f"{len(executable_scenes)} executable; delegate selection to FC",
            "action_needed": True,
            "video_config": video_config,
            "executable_scenes": executable_scenes,
        }

    async def _plan_next_action(
        self,
        reasoning: Dict[str, Any],
        workflow_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        # 存储最近观察，供 planning_roundN 模板使用
        try:
            self.iteration_context["last_observation"] = self.iteration_context.get("last_observation") or {}
        except Exception:
            pass
        if not reasoning.get("action_needed", False):
            if reasoning.get("strategy") == "wait_for_dependencies":
                return {"action": "wait_dependencies", "parameters": {"pending_scenes": reasoning.get("pending_scenes", [])}}
            return {"action": "complete_task", "parameters": {"final_status": reasoning.get("strategy", "completed")}}

        # 直接将可执行集合作为候选交给 FC；由 LLM 在 planning_roundN 中选择 selected_units
        current_batch = reasoning.get("executable_scenes", []) or []
        return {
            "action": "batch_generate_videos",
            "parameters": {
                "scenes_batch": current_batch,
                "video_config": reasoning.get("video_config", {}),
                "generation_strategy": "fc_autonomous",
            },
        }

    # ==== ACT ====
    async def _execute_action(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session,
        iteration: int,
    ) -> Dict[str, Any]:
        workflow_state = self.iteration_context.get("working_state") or await self._plan_execution_initial(self._current_task, input_data)
        self.iteration_context["working_state"] = workflow_state

        action = action_plan["action"]
        params = action_plan["parameters"]
        if action == "batch_generate_videos":
            scenes_batch = params.get("scenes_batch", [])
            # Fallback guard: prompt 已提醒单轮最多选择 N 个场景，但若模型偶尔超出，
            # 在此裁剪以避免一次性拼接过长上下文。将 VIDEO_GENERATOR_MAX_BATCH 设为 0
            # 可关闭该兜底，完全按模型输出执行。
            max_batch_size = max(int(getattr(settings, 'VIDEO_GENERATOR_MAX_BATCH', 0) or 0), 0)
            if max_batch_size and len(scenes_batch) > max_batch_size:
                deferred = scenes_batch[max_batch_size:]
                scenes_batch = scenes_batch[:max_batch_size]
                params["scenes_batch"] = scenes_batch
                try:
                    deferred_ids = []
                    for s in deferred:
                        try:
                            deferred_ids.append(int(s.get('scene_number')))
                        except Exception:
                            deferred_ids.append(s.get('scene_number'))
                    if deferred_ids:
                        self.logger.info(
                            "BATCH_LIMIT: truncated to %d scenes (deferred=%s)",
                            max_batch_size,
                            deferred_ids,
                        )
                        self.iteration_context['diag_last_deferred'] = deferred_ids
                except Exception:
                    pass
            try:
                ws = self.iteration_context.get("working_state") or {}
                ws["current_batch"] = list(scenes_batch)
                self.iteration_context["working_state"] = ws
            except Exception:
                pass
            # 预判就绪：优先利用 prepared_last_frames 或现有参考图
            try:
                ws0 = self.iteration_context.get("working_state", {}) or {}
                prepared_map = dict(ws0.get('prepared_last_frames') or {})

                def _scene_ready_to_generate(s: Dict[str, Any]) -> bool:
                    # 场景是否具备生成条件：
                    # - 无依赖：直接就绪
                    # - 有依赖：当前场景的连续性帧已准备好（prepared_last_frames[scene_number]）或已有参考图像
                    dep = s.get('depends_on_scene')
                    has_ref = bool(s.get('image_url'))
                    try:
                        sn = int(s.get('scene_number')) if s.get('scene_number') is not None else None
                    except Exception:
                        sn = None
                    if dep is not None and str(dep).isdigit():
                        return (sn is not None and sn in prepared_map) or has_ref
                    return True  # 无依赖 → 直接可生成

                # 子集就绪：若至少一个就绪且存在未就绪，优先生成就绪子集（最小暴露）
                try:
                    filled = list(scenes_batch or [])
                    ready_scenes = [s for s in filled if _scene_ready_to_generate(s)]
                    if ready_scenes and len(ready_scenes) < len(filled):
                        try:
                            subset_ids = []
                            for s in ready_scenes:
                                try:
                                    subset_ids.append(int(s.get('scene_number')))
                                except Exception:
                                    subset_ids.append(s.get('scene_number'))
                            key = tuple(sorted([x for x in subset_ids if x is not None]))
                            last_key = self.iteration_context.get('diag_last_ready_subset')
                            if key != last_key:
                                self.logger.info(f"READY_SUBSET scenes={list(key)}")
                                self.iteration_context['diag_last_ready_subset'] = key
                        except Exception:
                            pass
                        scenes_batch = ready_scenes
                        # 覆盖 working_state.current_batch 以便后续日志与注入一致
                        try:
                            ws_cur = self.iteration_context.get("working_state", {}) or {}
                            ws_cur["current_batch"] = list(ready_scenes)
                            self.iteration_context["working_state"] = ws_cur
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                pass

            force_generate_only = bool(self.iteration_context.get('force_generate_only'))

            # Build neutral facts and let FC pick tools/params（使用可能调整后的 scenes_batch）
            messages = self.build_fc_messages_for_batch(scenes_batch, workflow_state)
            round_outcome = await self.run_fc_round(messages=messages, context_description="batch video generation", temperature=0.2)
            executed_calls = round_outcome.get("executed_calls", []) or []
            # 合规提醒：有可执行但无 tool_calls → 记录一次空转
            if (scenes_batch and not executed_calls):
                try:
                    self.logger.warning("PLAN_COMPLIANCE: executable>0 but no tool_calls in this round (void turn)")
                    rm = dict(self.iteration_context.get('react_metrics', {}) or {})
                    vt = int(rm.get('void_turns', 0) or 0)
                    rm['void_turns'] = vt + 1
                    self.iteration_context['react_metrics'] = rm
                except Exception:
                    pass
            # 统一以 executed_calls 解析为准，避免只保留最后一次调用结果导致的缺失
            # 先处理连续性准备类调用，写入 working_state 以便后续轮次复用/优先调度
            try:
                ws0 = self.iteration_context.get("working_state", {}) or {}
                prepared_map = dict(ws0.get('prepared_last_frames') or {})
                priority_ids = list(ws0.get('priority_prepared_ids') or [])
                for ec in executed_calls:
                    try:
                        fn = ec.get('tool') or (ec.get('function', {}) or {}).get('name') or ''
                        if fn == 'scene_continuity_preparation.prepare_scene_input':
                            args = ec.get('args') or {}
                            payload = ec.get('result') or {}
                            # 兼容 ToolOutput
                            try:
                                if hasattr(payload, 'result'):
                                    payload = getattr(payload, 'result')
                            except Exception:
                                pass
                            sn = args.get('scene_number')
                            url = payload.get('image_url') if isinstance(payload, dict) else None
                            if sn is not None and url:
                                try:
                                    sn = int(sn)
                                except Exception:
                                    pass
                                prepared_map[sn] = url
                                if sn not in priority_ids:
                                    priority_ids.append(sn)
                    except Exception:
                        continue
                ws0['prepared_last_frames'] = prepared_map
                ws0['priority_prepared_ids'] = priority_ids
                self.iteration_context['working_state'] = ws0
            except Exception:
                pass

            parsed = await self._postprocess_executed_results(executed_calls)
            base_results = [
                r for r in (round_outcome.get("results") or [])
                if isinstance(r, dict) and (r.get("video_url") or r.get("video_path"))
            ]
            try:
                by_id = {}
                def _score(x):
                    if not isinstance(x, dict):
                        return 0
                    return int(bool(x.get('video_url'))) + int(bool(x.get('video_path') or x.get('file_path')))
                for r in base_results:
                    sn = r.get('scene_number')
                    if sn is not None:
                        by_id[int(sn)] = r
                for r in (parsed or []):
                    sn = r.get('scene_number')
                    if sn is None:
                        continue
                    prev = by_id.get(int(sn))
                    if (prev is None) or (_score(r) >= _score(prev)):
                        by_id[int(sn)] = r
                results = list(by_id.values())
                # ACT 诊断：输出本轮解析/合并后的场景
                try:
                    parsed_scenes = [r.get('scene_number') for r in (parsed or []) if isinstance(r, dict)]
                    merged_scenes = [r.get('scene_number') for r in (results or []) if isinstance(r, dict)]
                    exec_scenes = []
                    for c in (executed_calls or []):
                        try:
                            args = c.get('args') or {}
                            sn = args.get('scene_number')
                            exec_scenes.append(sn)
                        except Exception:
                            continue
                    fc_plan = round_outcome.get('fc_plan') if isinstance(round_outcome, dict) else None
                    planned_calls = 0
                    if isinstance(fc_plan, dict):
                        planned_calls = len(fc_plan.get('tool_calls') or [])
                    self.logger.info(f"ACT_DIAG(video): planned={planned_calls} executed={len(executed_calls)} parsed={len(parsed or [])} merged={len(results or [])} exec_scenes={exec_scenes} parsed_scenes={parsed_scenes} merged_scenes={merged_scenes}")
                except Exception:
                    pass
            except Exception:
                results = base_results or parsed or []
            try:
                results = self._align_results_with_batch(results, scenes_batch)
            except Exception:
                pass
            results = await self._ensure_persisted_videos(results)
            try:
                self.iteration_context['last_round_results'] = list(results)
            except Exception:
                pass
            # 记录本轮标准化结果到 inner_react_state.results_ledger（追加）
            try:
                ws = self.iteration_context.get("working_state", {}) or {}
                ledger = list(ws.get('results_ledger') or [])
                import time as _t
                ts = int(_t.time()*1000)
                for r in results or []:
                    if not isinstance(r, dict) or not r.get('success'):
                        continue
                    entry = {
                        'scene_number': r.get('scene_number'),
                        'video_url': r.get('video_url'),
                        'file_path': r.get('video_path') or r.get('file_path'),
                        'prompt_text': r.get('prompt_text'),
                        'duration': r.get('duration'),
                        'ts': ts,
                        'agent': 'video_generator'
                    }
                    ledger.append(entry)
                ws['results_ledger'] = ledger
                self.iteration_context['working_state'] = ws
            except Exception:
                pass
            # 轻量诊断：统计本轮是否使用连续性帧或参考图（基于工具返回的 execution_params）
            try:
                used_cont, used_ref = 0, 0
                for ec in executed_calls:
                    try:
                        payload = ec.get('result')
                        # 兼容 ToolOutput：若为对象则取其 result 字段
                        try:
                            if hasattr(payload, 'result'):
                                payload = getattr(payload, 'result')
                        except Exception:
                            pass
                        ex = payload.get('execution_params') if isinstance(payload, dict) else None
                        if isinstance(ex, dict):
                            used_cont += 1 if bool(ex.get('has_continuity_frame')) else 0
                            used_ref += 1 if bool(ex.get('has_reference_image')) else 0
                        else:
                            # 回退：从调用参数推断（当 execution_params 缺失时）
                            args = ec.get('args') or {}
                            if isinstance(args, dict):
                                if bool(args.get('continuity_frame')):
                                    used_cont += 1
                                # 若提供了 image_url 但无 continuity_frame，则计作参考图
                                elif bool(args.get('image_url')):
                                    used_ref += 1
                    except Exception:
                        continue
                self.logger.info(
                    f"CONTINUITY_DIAG: continuity_frame={used_cont} reference_image={used_ref} calls={len(executed_calls)}"
                )
            except Exception:
                pass

            # 无进展轮次保护：若连续出现仅prepare且无生成，则下一轮强制仅生成
            try:
                def _fname(c):
                    return c.get('tool') or (c.get('function', {}) or {}).get('name')
                progressed = any(_fname(c) == 'video_generation.generate_with_continuity' for c in executed_calls)
                only_prepare = executed_calls and all(_fname(c) == 'scene_continuity_preparation.prepare_scene_input' for c in executed_calls)
                np = int(self.iteration_context.get('no_progress_rounds', 0) or 0)
                if progressed:
                    self.iteration_context['no_progress_rounds'] = 0
                    self.iteration_context.pop('force_generate_only', None)
                elif only_prepare:
                    self.iteration_context['no_progress_rounds'] = np + 1
                    try:
                        from ..core.config import settings as _cfg
                        max_np = int(getattr(_cfg, 'REACT_NO_PROGRESS_MAX_ROUNDS', 2) or 2)
                    except Exception:
                        max_np = 2
                    if self.iteration_context['no_progress_rounds'] >= max_np:
                        self.iteration_context['force_generate_only'] = True
                        self.iteration_context['no_progress_rounds'] = 0
                else:
                    self.iteration_context['no_progress_rounds'] = 0
                    self.iteration_context.pop('force_generate_only', None)
            except Exception:
                pass

            return {
                "action_performed": "batch_video_generation",
                "batch_size": len(scenes_batch),
                "generation_results": results,
                "executed_calls": executed_calls,
                "llm_react_contract": round_outcome.get("contract")
            }

        if action == "wait_dependencies":
            return await self._execute_dependency_wait(params)
        if action == "complete_task":
            return await self._execute_task_completion(workflow_state)
        raise AgentError(f"Unknown action: {action}")

    async def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Override to inject stable args for video generation calls before execution.

        - Inject workflow_state_id for continuity bookkeeping
        - Ensure scene_number is present when determinable (single-item batch fallback)
        - Default emit_last_frame to 'auto' for generate_with_continuity
        """
        calls: List[Dict[str, Any]] = []
        blocked_results: List[Dict[str, Any]] = []
        try:
            ws = self.iteration_context.get("working_state", {}) or {}
            ctx = ws.get("context", {}) or {}
            wf_id = ctx.get("workflow_state_id") or self.iteration_context.get("workflow_state_id")
            target_resolution = ctx.get("target_resolution") or self.iteration_context.get("target_resolution")
            if not target_resolution:
                try:
                    src = self.iteration_context.get("source_input") or {}
                    if isinstance(src, dict):
                        target_resolution = src.get("resolution")
                except Exception:
                    target_resolution = None
            current_batch = ws.get("current_batch") or []
            single_sn = None
            try:
                if isinstance(current_batch, list) and len(current_batch) == 1:
                    single_sn = current_batch[0].get("scene_number")
            except Exception:
                single_sn = None
            for tc in tool_calls or []:
                try:
                    fn = tc.get("function", {}).get("name")
                    raw = tc.get("function", {}).get("arguments")
                    import json as _json
                    args = _json.loads(raw) if isinstance(raw, str) else (raw or {})
                    skip_call = False
                    if isinstance(args, dict):
                        # Inject for video_generation.generate_with_continuity
                        if fn == 'video_generation.generate_with_continuity':
                            if wf_id and not args.get('workflow_state_id'):
                                args['workflow_state_id'] = wf_id
                            if args.get('emit_last_frame') is None:
                                args['emit_last_frame'] = 'auto'
                            if args.get('scene_number') is None and single_sn is not None:
                                args['scene_number'] = single_sn
                            if target_resolution and not args.get('resolution') and not args.get('rs'):
                                args['resolution'] = target_resolution
                            # 稳定利用已准备的连续性帧：优先注入当前场景的 prepared_last_frames
                            try:
                                ws_prepared = (self.iteration_context.get('working_state') or {}).get('prepared_last_frames') or {}
                                if isinstance(ws_prepared, dict):
                                    sn_try = args.get('scene_number')
                                    try:
                                        sn_val = int(sn_try) if sn_try is not None else None
                                    except Exception:
                                        sn_val = None
                                    if sn_val is not None:
                                        cont_url = ws_prepared.get(sn_val)
                                        if isinstance(cont_url, str) and cont_url and not args.get('image_url'):
                                            args['image_url'] = cont_url
                            except Exception:
                                pass
                            # 若 previous_video_url 实际是图片（尾帧），将其改写为 image_url，避免触发 media_type 警告
                            try:
                                prev_video_url = args.get('previous_video_url')
                                if self._looks_like_image(prev_video_url):
                                    if not args.get('image_url'):
                                        args['image_url'] = prev_video_url
                                    args.pop('previous_video_url', None)
                            except Exception:
                                pass

                            # 回退（仅限非依赖场景）：若仍无 image_url，则读取 WF 场景的参考图像
                            try:
                                # 识别是否为连续场景
                                dep_val = args.get('depends_on_scene')
                                is_dependent = False
                                try:
                                    if dep_val is not None and str(dep_val).isdigit() and int(dep_val) > 0:
                                        is_dependent = True
                                except Exception:
                                    is_dependent = False

                                if (not args.get('image_url')) and (not is_dependent):
                                    from ..core.workflow_state import workflow_manager
                                    wf = workflow_manager.get_workflow(wf_id) if wf_id else None
                                    sn_try = args.get('scene_number')
                                    try:
                                        sn_val = int(sn_try) if sn_try is not None else None
                                    except Exception:
                                        sn_val = None
                                    if wf and sn_val is not None:
                                        sc = wf.get_scene(sn_val)
                                        iu = getattr(sc, 'image_url', '') if sc else ''
                                        if isinstance(iu, str) and iu:
                                            args['image_url'] = iu
                            except Exception:
                                pass
                            # 可选注入 depends_on_scene（来源于场景清单），便于工具做更精确诊断
                            try:
                                if args.get('depends_on_scene') is None:
                                    ctx_scenes = ((self.iteration_context.get('working_state') or {}).get('context') or {}).get('scenes_to_generate') or []
                                    sn_try = args.get('scene_number')
                                    try:
                                        sn_val = int(sn_try) if sn_try is not None else None
                                    except Exception:
                                        sn_val = None
                                    if sn_val is not None:
                                        for sc in ctx_scenes:
                                            if isinstance(sc, dict) and sc.get('scene_number') == sn_val:
                                                dep_v = sc.get('depends_on_scene')
                                                if dep_v is not None:
                                                    try:
                                                        args['depends_on_scene'] = int(dep_v) if str(dep_v).isdigit() else dep_v
                                                    except Exception:
                                                        args['depends_on_scene'] = dep_v
                                                break
                            except Exception:
                                pass

                            # 结构化参数增强：默认补充画风与角色一致性约束
                            try:
                                policy = get_consistency_policy()

                                style_defaults = self._get_style_constraints()
                                merged_style = self._merge_style_constraints(
                                    args.get('style_constraints'),
                                    style_defaults,
                                    policy,
                                )
                                if merged_style.flattened:
                                    args['style_constraints'] = merged_style.flattened
                                meta_bucket = args.setdefault('_consistency_meta', {})
                                style_meta = meta_bucket.setdefault('style', {})
                                current_scene_id = args.get('scene_number')
                                style_meta[str(current_scene_id) if current_scene_id is not None else 'global'] = {
                                    "locked": merged_style.locked,
                                    "suggestions": merged_style.suggestions,
                                }

                                wf_id2 = args.get('workflow_state_id') or wf_id
                                sn2_raw = args.get('scene_number')
                                sn2 = int(sn2_raw) if sn2_raw is not None and str(sn2_raw).isdigit() else None
                                if wf_id2 and sn2 is not None:
                                    wf_obj2 = self._get_workflow_state_obj(wf_id2)
                                    concept_plan_local = self._get_concept_plan(wf_obj2)
                                    char_structs, char_texts = self._get_scene_character_constraints(wf_id2, sn2)
                                    if char_structs:
                                        merged_structs = self._merge_struct_list(
                                            args.get('character_constraints_struct'),
                                            char_structs,
                                        )
                                        if merged_structs:
                                            args['character_constraints_struct'] = merged_structs
                                    if char_texts:
                                        merged_text = self._merge_character_text_constraints(
                                            args.get('character_constraints'),
                                            char_texts,
                                            policy,
                                        )
                                        if merged_text:
                                            args['character_constraints'] = merged_text

                                    merged_neg = self._merge_negative_constraints(
                                        args.get('negative_constraints'),
                                        char_structs,
                                        char_texts,
                                        concept_plan_local,
                                        sn2,
                                        policy,
                                    )
                                    if merged_neg.flattened:
                                        args['negative_constraints'] = merged_neg.flattened
                                    negative_meta = meta_bucket.setdefault('negative', {})
                                    negative_meta[str(sn2)] = {
                                        "locked": merged_neg.locked,
                                        "suggestions": merged_neg.suggestions,
                                    }
                            except Exception:
                                pass
                        # Normalize scene_number to int when possible
                        try:
                            if args.get('scene_number') is not None:
                                sn = int(args.get('scene_number'))
                                args['scene_number'] = sn
                        except Exception:
                            pass
                        # Normalize depends_on_scene to int when possible
                        try:
                            if args.get('depends_on_scene') is not None and str(args.get('depends_on_scene')).isdigit():
                                args['depends_on_scene'] = int(args.get('depends_on_scene'))
                        except Exception:
                            pass
                        # Write back
                        if isinstance(raw, str):
                            tc['function']['arguments'] = _json.dumps(args, ensure_ascii=False)
                        else:
                            tc['function']['arguments'] = args

                        if fn == 'video_generation.generate_with_continuity':
                            sn_val = self._normalize_scene_number(args.get('scene_number'))
                            entry = self._get_pending_regen_entry(sn_val) if sn_val is not None else None
                            status = str((entry or {}).get('status', '')).lower()
                            if entry and status in {'waiting', 'regenerating'}:
                                skip_call = True
                                meta = {
                                    'scene_number': sn_val,
                                    'status': status,
                                    'attempts': entry.get('attempts'),
                                    'reason': entry.get('reason'),
                                }
                                blocked_results.append({
                                    'tool': fn,
                                    'args': args,
                                    'scene_number': sn_val,
                                    'success': False,
                                    'error': 'scene pending image regeneration',
                                    'error_type': 'pending_image_regen',
                                    'metadata': meta,
                                })
                                try:
                                    self.logger.warning(
                                        "SKIP_VIDEO_CALL_PENDING_REGEN: scene=%s status=%s attempts=%s",
                                        sn_val,
                                        status,
                                        entry.get('attempts'),
                                    )
                                except Exception:
                                    pass
                        elif fn == 'image_generation.generate_with_autoprompt':
                            sn_val = self._normalize_scene_number(args.get('scene_number'))
                            if sn_val is not None and self._get_pending_regen_entry(sn_val):
                                self._set_pending_regen_status(sn_val, 'regenerating')
                    if skip_call:
                        continue
                except Exception:
                    skip_call = False
                if not skip_call:
                    calls.append(tc)
        except Exception:
            calls = list(tool_calls or [])
        # Delegate to base for actual execution and logging
        results = await super().execute_tool_calls(calls)
        if blocked_results:
            results.extend(blocked_results)
        return results

    def build_fc_messages_for_batch(self, scenes_batch: List[Dict[str, Any]], workflow_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        completed = workflow_state.get("completed_scenes", {}) or {}
        prev_completed = len(completed)
        prev_failed = len(workflow_state.get("failed_scenes", []) or [])
        notes = workflow_state.get("reflection_notes", []) or []
        note_str = " | ".join(notes[-3:]) if notes else ""
        force_generate_only = bool(self.iteration_context.get('force_generate_only'))
        image_map: Dict[int, str] = {}
        video_map: Dict[int, str] = {}
        depends_map: Dict[int, Optional[int]] = {}
        reason_map: Dict[int, str] = {}
        conf_map: Dict[int, float] = {}
        last_frame_map: Dict[int, str] = {}
        prepared_map: Dict[int, str] = {}
        priority_ids: List[int] = []
        pending_regen_map: Dict[int, Dict[str, Any]] = {}
        blocked_regen_ids: Set[int] = set()
        motion_beats_map: Dict[int, List[Dict[str, Any]]] = {}
        try:
            from ..core.workflow_state import workflow_manager
            wf_id = workflow_state.get('context', {}).get('workflow_state_id') or self.iteration_context.get('workflow_state_id')
            wf = workflow_manager.get_workflow(wf_id) if wf_id else None
            if wf:
                for sc in getattr(wf, 'scenes', []) or []:
                    try:
                        sn = int(getattr(sc, 'scene_number', 0) or 0)
                    except Exception:
                        continue
                    if sn:
                        iu = getattr(sc, 'image_url', '') or ''
                        vu = getattr(sc, 'video_url', '') or ''
                        dp = getattr(sc, 'depends_on_scene', None)
                        rs = getattr(sc, 'continuity_reason', '') or ''
                        cf = float(getattr(sc, 'continuity_confidence', 0.0) or 0.0)
                        lf = getattr(sc, 'last_frame_url', '') or ''
                        if iu:
                            image_map[sn] = iu
                        if vu:
                            video_map[sn] = vu
                        depends_map[sn] = dp
                        if rs:
                            reason_map[sn] = rs
                        if cf:
                            conf_map[sn] = cf
                        if lf:
                            last_frame_map[sn] = lf
            # 合并 inner_react_state 的已完成视频（作为视频事实来源，不依赖中途写WF）
            try:
                ws_inner = self.iteration_context.get("working_state", {}) or {}
                completed_inner = ws_inner.get("completed_scenes") or {}
                if isinstance(completed_inner, dict):
                    for k, v in completed_inner.items():
                        try:
                            sn = int(k)
                        except Exception:
                            continue
                        if not isinstance(v, dict):
                            continue
                        vu = v.get('video_url') or v.get('video_path') or ''
                        iu = v.get('image_url') or ''
                        if vu and sn not in video_map:
                            video_map[sn] = vu
                        if iu and sn not in image_map:
                            image_map[sn] = iu
                elif isinstance(completed_inner, list):
                    for it in completed_inner:
                        if not isinstance(it, dict):
                            continue
                        try:
                            sn = int(it.get('scene_number')) if it.get('scene_number') is not None else None
                        except Exception:
                            sn = None
                        if not sn:
                            continue
                        vu = it.get('video_url') or it.get('video_path') or ''
                        iu = it.get('image_url') or ''
                        if vu and sn not in video_map:
                            video_map[sn] = vu
                        if iu and sn not in image_map:
                            image_map[sn] = iu
            except Exception:
                pass
            # 读取已准备的连续性帧与优先级
            try:
                pm = workflow_state.get('prepared_last_frames') or {}
                if isinstance(pm, dict):
                    prepared_map = {int(k): v for k, v in pm.items() if isinstance(v, str)}
            except Exception:
                prepared_map = {}
            try:
                priority_ids = list(workflow_state.get('priority_prepared_ids') or [])
                priority_ids = [int(x) for x in priority_ids if isinstance(x, (int, str)) and str(x).isdigit()]
            except Exception:
                priority_ids = []
            try:
                pending_regen_map, blocked_regen_ids = self._extract_pending_image_regen(workflow_state, sanitize=True)
            except Exception:
                pending_regen_map, blocked_regen_ids = {}, set()
            try:
                ctx_scenes = (workflow_state.get('context') or {}).get('scenes_to_generate') or []
                for sc in ctx_scenes:
                    if not isinstance(sc, dict):
                        continue
                    sn = sc.get('scene_number')
                    if sn is None:
                        continue
                    beats = sc.get('motion_beats')
                    if isinstance(beats, list) and beats:
                        try:
                            motion_beats_map[int(sn)] = beats
                        except Exception:
                            continue
            except Exception:
                motion_beats_map = {}
        except Exception:
            image_map, video_map = {}, {}
            depends_map, reason_map, conf_map, last_frame_map = {}, {}, {}, {}
            pending_regen_map, blocked_regen_ids = {}, set()
            motion_beats_map = {}

        target_resolution = None
        try:
            context_info = (workflow_state.get("context") or {})
            target_resolution = context_info.get("target_resolution") or context_info.get("resolution")
            if not target_resolution:
                vc = context_info.get("video_config") or {}
                target_resolution = vc.get("default_resolution")
        except Exception:
            target_resolution = None
        if not target_resolution:
            try:
                src_input = self.iteration_context.get("source_input") or {}
                if isinstance(src_input, dict):
                    target_resolution = src_input.get("resolution")
            except Exception:
                target_resolution = None

        # 填充就绪批次（避免破坏连续链路）：
        # - 依赖场景：仅在 prepared_last_frames 命中时注入 image_url（连续性帧）；不要回退到场景自身图像，
        #   以免误导 LLM 跳过连续性准备，扰乱 DAG 顺序与尾帧链路。
        # - 非依赖场景：若无连续性帧，可回退使用该场景自身的 image_url（来自 WF 的 image_map），稳定 I2V。
        filled_batch: List[Dict[str, Any]] = []
        try:
            for s in (scenes_batch or []):
                s1 = dict(s or {})
                if not s1.get('image_url'):
                    try:
                        sn = int(s1.get('scene_number')) if s1.get('scene_number') is not None else None
                    except Exception:
                        sn = None
                    if sn is not None:
                        dep = depends_map.get(sn)
                        # 1) 连续性帧优先（仅在有依赖时注入连续帧）
                        if sn in prepared_map:
                            s1['image_url'] = prepared_map[sn]
                        else:
                            # 2) 非依赖场景允许回退到场景参考图，避免退化为 T2V
                            if dep in (None, "", 0):
                                if sn in image_map:
                                    s1['image_url'] = image_map[sn]
                filled_batch.append(s1)
        except Exception:
            filled_batch = list(scenes_batch or [])
        # 构造 planning_roundN system 消息（滚动规划 + 执行合一）
        try:
            ws = self.iteration_context.get("working_state", {}) or {}
            ctx = ws.get("context", {}) or {}
            aop = ctx.get("agent_overall_plan", {}) or {}
            plan_digest = str(aop.get("plan_digest") or '').strip()
            try:
                steps = aop.get("steps") or aop.get("stages") or []
                plan_outline = _json.dumps(steps[:6], ensure_ascii=False)
            except Exception:
                plan_outline = "[]"
            progress_summary = self.build_progress_summary() or ""
            scratchpad = self.build_scratchpad(k=2) or ""
            obs = self.iteration_context.get("last_observation") or {
                "executable_scenes": filled_batch,
                "pending_dependent_scenes": [],
                "task_status": "in_progress"
            }
            # 始终以 filled_batch 覆盖可执行集合（带入已准备的连续性帧），避免 last_observation 中的过时空 image_url 误导 FC
            obs_aug = dict(obs)
            obs_aug["executable_scenes"] = filled_batch
            if target_resolution:
                obs_aug["target_resolution"] = target_resolution
            # 注入全局风格指导（来自 concept_plan 或 orchestrator 的 creative_guidance），供FC保持风格一致
            try:
                style_guidance = {}
                # 1) 从概念计划读取智能风格设计
                try:
                    cp = ctx.get('concept_plan') or {}
                    if isinstance(cp, dict):
                        isd = cp.get('intelligent_style_design') or {}
                        if isinstance(isd, dict) and isd:
                            style_guidance = isd
                except Exception:
                    pass
                # 2) 回退：从 orchestrator 注入的 creative_guidance 读取
                if not style_guidance:
                    try:
                        src_in = dict(self.iteration_context.get('source_input') or {})
                        cg = src_in.get('creative_guidance') or {}
                        if isinstance(cg, dict) and cg:
                            style_guidance = cg
                    except Exception:
                        pass
                if style_guidance:
                    obs_aug['style_guidance'] = style_guidance
            except Exception:
                pass
            # 汇入角色一致性“事实”供FC参考（不包含工具/参数名）
            project_ctx = ctx.get('project_context') or {}
            character_bible = project_ctx.get('character_bible') if isinstance(project_ctx, dict) else {}
            if isinstance(character_bible, dict) and character_bible:
                obs_aug['character_bible'] = character_bible
            try:
                # 角色来源：WF.scene 优先；缺失回退 concept_plan.scenes；再回退 orchestrator.scene_guidances
                char_names: Dict[int, List[str]] = {}
                char_descs: Dict[int, List[str]] = {}
                alias_lookup: Dict[str, str] = {}
                for cid, profile in (character_bible or {}).items():
                    if not isinstance(profile, dict):
                        continue
                    display = str(profile.get('display_name') or '').strip()
                    if display:
                        alias_lookup.setdefault(display.casefold(), cid)
                    for alias in profile.get('aliases') or []:
                        alias_name = str(alias).strip()
                        if alias_name:
                            alias_lookup.setdefault(alias_name.casefold(), cid)
                try:
                    wf_id = ctx.get("workflow_state_id")
                    if wf_id:
                        from ..core.workflow_state import workflow_manager
                        wf = workflow_manager.get_workflow(wf_id)
                        for sc in getattr(wf, 'scenes', []) or []:
                            try:
                                sn = int(getattr(sc, 'scene_number', 0) or 0)
                            except Exception:
                                continue
                            if not sn:
                                continue
                            nms = list(getattr(sc, 'characters_present', []) or [])
                            dcs = list(getattr(sc, 'character_descriptions', []) or [])
                            if nms:
                                char_names[sn] = [str(x) for x in nms if str(x).strip()]
                            if dcs:
                                char_descs[sn] = [str(x) for x in dcs if str(x).strip()]
                except Exception:
                    pass
                if not char_names:
                    try:
                        cp = ctx.get('concept_plan') or {}
                        for s in (cp.get('scenes') or []):
                            try:
                                sid = int(s.get('scene_number')) if s.get('scene_number') is not None else None
                            except Exception:
                                sid = None
                            if sid is None:
                                continue
                            nms = (((s.get('content_elements') or {}).get('characters_present')) or [])
                            if nms:
                                char_names[sid] = [str(x) for x in nms if str(x).strip()]
                    except Exception:
                        pass
                if not char_names and not char_descs:
                    try:
                        src_in = dict(self.iteration_context.get('source_input') or {})
                        sgs = src_in.get('scene_guidances') or {}
                        for k, v in (sgs.items() if isinstance(sgs, dict) else []):
                            try:
                                if str(k).startswith('scene_'):
                                    sid = int(str(k).split('_')[-1])
                                else:
                                    sid = None
                            except Exception:
                                sid = None
                            if sid is None:
                                continue
                            nms = (v or {}).get('characters_present') or (v or {}).get('characters') or []
                            if nms:
                                char_names[sid] = [str(x) for x in nms if str(x).strip()]
                    except Exception:
                        pass
                char_facts: Dict[int, Dict[str, Any]] = {}
                for sn in set(list(char_names.keys()) + list(char_descs.keys())):
                    names = char_names.get(sn, [])
                    descs = char_descs.get(sn, [])
                    entry = {"names": names, "descriptions": descs}
                    matched_ids: List[str] = []
                    for nm in names:
                        token = str(nm).strip()
                        if not token:
                            continue
                        canonical = alias_lookup.get(token.casefold())
                        if canonical and canonical not in matched_ids:
                            matched_ids.append(canonical)
                    if matched_ids:
                        entry["character_ids"] = matched_ids
                    char_facts[sn] = entry
            except Exception:
                char_facts = {}

            # 对 LLM 暴露的中立事实中，不包含供应商视频直链映射，避免误用/截断导致403；
            # 仍保留是否已有连续性帧/参考图的事实信号（通过 last_frame_map / prepared_last_frames / image_map 等）。
            obs_aug["facts"] = {
                "image_map": image_map,
                "depends_on": depends_map,
                "continuity_reason": reason_map,
                "continuity_confidence": conf_map,
                "last_frame_map": last_frame_map,
                "prepared_last_frames": prepared_map,
                "priority_prepared_ids": priority_ids,
                "pending_image_regen": pending_regen_map,
                "motion_beats_map": motion_beats_map,
                "characters_map": char_facts,
            }
            # 适度诊断：DEBUG 级别输出可见的风格/角色事实摘要（不打印大对象）
            try:
                if self.logger.isEnabledFor(__import__('logging').DEBUG):
                    ch_map = ((obs_aug.get('facts') or {}).get('characters_map')) or {}
                    ch_cnt = len(ch_map) if isinstance(ch_map, dict) else 0
                    has_style = bool(obs_aug.get('style_guidance'))
                    self.logger.debug(
                        f"FC_FACTS(video): style={'yes' if has_style else 'no'}, roles_scenes={ch_cnt}"
                    )
            except Exception:
                pass
            observation_json = _json.dumps(obs_aug, ensure_ascii=False)
            from ..core.prompt_manager import get_prompt_manager
            pm = get_prompt_manager()
            sys_text = pm.render_template(self.agent_name, "planning_roundN", {
                "plan_digest": plan_digest,
                "plan_outline": plan_outline,
                "progress_summary": progress_summary,
                "scratchpad": scratchpad,
                "observation_json": observation_json,
            }, auto_reload=False)
        except Exception:
            sys_text = None

        messages: List[Dict[str, Any]] = []
        if sys_text:
            messages.append({"role": "system", "content": sys_text})
        # 用户消息：中立事实摘要 + 强约束回复要求
        facts_lines: List[str] = []
        facts_lines.append(
            f"批次候选数量：{len(scenes_batch)}；进度：已完成 {prev_completed}，失败 {prev_failed}。" + (f" 最近反思：{note_str}" if note_str else "")
        )
        if force_generate_only:
            facts_lines.append("⚠️ 最近几轮仅执行准备步骤，请直接调用视频生成工具完成当前批次，不要只调用准备类动作。")
        if blocked_regen_ids:
            for sn in sorted(blocked_regen_ids):
                info = pending_regen_map.get(sn) or {}
                reason_txt = info.get('reason') or '参考图被判敏感'
                attempts_txt = info.get('attempts') or 0
                facts_lines.append(
                    f"场景{sn}需先生成安全参考图（已尝试{attempts_txt}次：{reason_txt}）。"
                )
        if target_resolution:
            facts_lines.append(f"目标输出分辨率：{target_resolution}。如需调整，请在响应中说明原因。")
        for s in filled_batch:
            try:
                sn = s.get("scene_number")
                parts = [f"场景{sn}"]
                if sn in depends_map and depends_map[sn]:
                    parts.append(f"依赖场景{depends_map[sn]}")
                if sn in video_map:
                    parts.append("已有视频")
                elif sn in image_map:
                    # 仅对非依赖场景标注“有参考图”，避免连续场景被误判为已具备参考输入
                    dep = depends_map.get(sn)
                    if dep in (None, "", 0):
                        parts.append("有参考图")
                # 标注：本场景是否已准备连续性输入（prepared_last_frames）
                try:
                    if sn in prepared_map:
                        parts.append("已准备连续性输入")
                except Exception:
                    pass
                if sn in last_frame_map:
                    parts.append("有连续性尾帧")
                if sn in priority_ids:
                    parts.append("优先执行")
                beats_preview = motion_beats_map.get(sn)
                if beats_preview:
                    parts.append(f"节奏{len(beats_preview)}段")
                facts_lines.append("- " + "，".join(parts))
            except Exception:
                continue
        user_instr = (
            "\n请基于上述信息进行本轮决策：当 intent 为 execute 时，必须在同一响应中通过函数调用执行所选对象；"
            "文本部分仅输出一个严格的 PlanningDecision JSON（不要其他文字/围栏）。"
        )
        messages.append({"role": "user", "content": "\n".join(facts_lines) + user_instr})
        return messages

    async def _postprocess_executed_results(self, executed_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """标准化执行结果：
        - 成功：收集包含 video_url 的项并持久化
        - 失败：对无产物或调用失败的项返回 success=False，以便反射阶段记录 failed_scenes
        """
        results: List[Dict[str, Any]] = []
        for call in executed_calls or []:
            try:
                args = call.get("args") or {}
                payload = call.get("result") or {}
                fn = call.get('tool') or (call.get('function', {}) or {}).get('name') or ''
                metadata = call.get('metadata') or {}
                error_type = call.get('error_type')
                scene_num = call.get('scene_number')
                if scene_num is None and isinstance(args, dict):
                    scene_num = args.get("scene_number")
                try:
                    if scene_num is not None and str(scene_num).isdigit():
                        scene_num = int(scene_num)
                except Exception:
                    pass
                # 仅处理本代理的视频生成调用
                if isinstance(fn, str) and fn.startswith('image_generation.'):
                    # 处理重新生成的参考图
                    try:
                        if hasattr(payload, 'result'):
                            payload = getattr(payload, 'result')
                    except Exception:
                        pass
                    image_url = payload.get('image_url') if isinstance(payload, dict) else None
                    if image_url:
                        await self._apply_regenerated_image(scene_num, payload)
                        results.append({
                            "success": True,
                            "scene_number": scene_num,
                            "artifact_type": "image_regen",
                            "image_url": image_url,
                            "prompt_text": (args.get('prompt') if isinstance(args, dict) else None) or payload.get('prompt_text') or '',
                        })
                    else:
                        err_msg = None
                        if isinstance(payload, dict):
                            err_msg = payload.get('error') or payload.get('message') or payload.get('status')
                        if not err_msg:
                            err_msg = call.get('error') if isinstance(call.get('error'), str) else 'image_regen_failed'
                        self._note_image_regen_failure(scene_num, err_msg or 'image_regen_failed')
                        results.append({
                            "success": False,
                            "scene_number": scene_num,
                            "artifact_type": "image_regen",
                            "error": err_msg or 'image_regen_failed',
                            "error_type": call.get('error_type') or 'image_regen_failed',
                        })
                    continue

                if not (isinstance(fn, str) and fn.startswith('video_generation.')):
                    continue
                # 兼容 ToolOutput：若为对象则取其 result 字段
                try:
                    if hasattr(payload, 'result'):
                        payload = getattr(payload, 'result')
                except Exception:
                    pass
                if isinstance(payload, dict) and payload.get("video_url"):
                    # 成功路径
                    try:
                        if scene_num is not None and str(scene_num).isdigit():
                            scene_num = int(scene_num)
                    except Exception:
                        pass
                    storage_result = await self._store_generated_video(payload.get("video_url", ""), scene_num)
                    file_path = ""
                    if isinstance(storage_result, dict):
                        file_path = storage_result.get("file_path") or storage_result.get("local_path") or ""
                    results.append({
                        "success": True,
                        "scene_number": scene_num,
                        "video_url": payload.get("video_url", ""),
                        "video_path": file_path or payload.get("file_path", ""),
                        "prompt_text": (args.get("prompt") if isinstance(args, dict) else None) or payload.get("prompt_text") or payload.get("prompt") or "",
                        "duration": (args.get("duration") if isinstance(args, dict) else None) or payload.get("duration") or 5,
                    })
                else:
                    # 失败/空产物路径：标记失败，避免无限重试
                    try:
                        if scene_num is not None:
                            err = None
                            if isinstance(payload, dict):
                                err = payload.get('error') or payload.get('status') or payload.get('message')
                            if not err and isinstance(call.get('error'), str):
                                err = call.get('error')
                            failure_entry = {
                                "success": False,
                                "scene_number": int(scene_num) if str(scene_num).isdigit() else scene_num,
                                "error": err or "video_generation returned no artifact",
                                "duration": (args.get("duration") if isinstance(args, dict) else None) or 5,
                            }
                            if error_type:
                                failure_entry["error_type"] = error_type
                            if metadata.get('error_details_struct'):
                                failure_entry["error_details"] = metadata.get('error_details_struct')
                            elif metadata.get('error_details'):
                                failure_entry["error_details"] = metadata.get('error_details')
                            results.append(failure_entry)
                            if error_type == 'sensitive_input_image':
                                details_struct = metadata.get('error_details_struct') or {}
                                await self._handle_sensitive_image_failure(
                                    int(scene_num) if str(scene_num).isdigit() else scene_num,
                                    details_struct,
                                    args if isinstance(args, dict) else {},
                                )
                    except Exception:
                        pass
            except Exception:
                continue
        return results

    async def _ensure_persisted_videos(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """确保成功的视频结果具有稳定的 file_path。
        对缺失路径的项，通过存储工具进行上传补全。
        """
        if not results:
            return results
        updated: List[Dict[str, Any]] = []
        for r in results:
            try:
                if not r or not r.get("success"):
                    updated.append(r)
                    continue
                if r.get("video_path"):
                    updated.append(r)
                    continue
                video_url = r.get("video_url")
                scene_num = r.get("scene_number")
                if video_url:
                    storage_result = await self._store_generated_video(video_url, scene_num)
                    file_path = ""
                    if isinstance(storage_result, dict):
                        file_path = storage_result.get("file_path") or storage_result.get("local_path") or ""
                    r = dict(r)
                    r["video_path"] = file_path or r.get("video_path", "")
                updated.append(r)
            except Exception:
                updated.append(r)
        return updated

    async def _store_generated_video(self, video_url: str, scene_num: Any) -> Dict[str, Any]:
        """将远程视频 URL 落盘到本地/持久化存储，并返回包含 file_path 的字典。
        通过 file_storage_tool.upload_from_url 工具实现，遵循“工具优先、供应商解耦”。
        """
        if not video_url:
            return {}
        try:
            if 'file_storage_tool' not in self._available_tools:
                return {}
            dest = f"videos/scene_{scene_num}.mp4" if scene_num is not None else f"videos/video_{int(__import__('time').time())}.mp4"
            res = await self.use_tool(
                tool_name='file_storage_tool',
                action='upload_from_url',
                parameters={
                    'url': video_url,
                    'destination_key': dest,
                    'metadata': {
                        'scene_number': scene_num,
                        'source': 'video_generator_persist'
                    }
                }
            )
            payload = getattr(res, 'result', res)
            if isinstance(payload, dict):
                if 'file_path' not in payload and 'local_path' in payload:
                    payload = dict(payload)
                    payload['file_path'] = payload.get('local_path')
                return payload
            return {}
        except Exception:
            return {}

    # === 敏感参考图回收与再生成辅助 ===

    def _normalize_scene_number(self, value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.strip():
                txt = value.strip()
                if txt.isdigit():
                    return int(txt)
            return int(value)
        except Exception:
            return None

    def _get_working_state(self) -> Dict[str, Any]:
        ws = self.iteration_context.get("working_state")
        if not isinstance(ws, dict):
            ws = {}
            self.iteration_context["working_state"] = ws
        return ws

    def _get_pending_regen_entry(self, scene_number: int) -> Optional[Dict[str, Any]]:
        ws = self._get_working_state()
        pending = ws.get('pending_image_regen')
        if not isinstance(pending, dict):
            return None
        entry = pending.get(scene_number)
        if entry is None:
            entry = pending.get(str(scene_number))
        return entry if isinstance(entry, dict) else None

    def _upsert_pending_regen_entry(self, scene_number: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        ws = self._get_working_state()
        pending = ws.get('pending_image_regen')
        if not isinstance(pending, dict):
            pending = {}
        entry = dict(self._get_pending_regen_entry(scene_number) or {})
        # 仅保留非 None 的字段，避免旧字段被覆盖为 None
        for key, value in updates.items():
            if value is not None:
                entry[key] = value
        pending[int(scene_number)] = entry
        ws['pending_image_regen'] = pending
        self.iteration_context['working_state'] = ws
        return entry

    def _set_pending_regen_status(self, scene_number: int, status: str, **extra: Any) -> None:
        sn = self._normalize_scene_number(scene_number)
        if sn is None:
            return
        payload = {"status": str(status).lower(), "updated_at": time.time()}
        payload.update(extra)
        self._upsert_pending_regen_entry(sn, payload)

    def _extract_pending_image_regen(
        self,
        workflow_state: Dict[str, Any],
        *,
        sanitize: bool = True,
    ) -> Tuple[Dict[int, Dict[str, Any]], Set[int]]:
        pending_raw = {}
        try:
            pending_raw = workflow_state.get('pending_image_regen') or {}
        except Exception:
            pending_raw = {}
        sanitized: Dict[int, Dict[str, Any]] = {}
        blocked: Set[int] = set()
        if not isinstance(pending_raw, dict):
            return sanitized, blocked

        for key, entry in pending_raw.items():
            if not isinstance(entry, dict):
                continue
            sn = self._normalize_scene_number(key)
            if sn is None:
                sn = self._normalize_scene_number(entry.get('scene_number'))
            if sn is None:
                continue
            status = str(entry.get('status', 'waiting')).lower()
            info: Dict[str, Any] = {
                'status': status,
                'attempts': int(entry.get('attempts', 0) or 0),
                'reason': entry.get('reason') or 'input_image_sensitive',
            }
            if entry.get('blocked_at'):
                info['blocked_at'] = entry.get('blocked_at')
            if entry.get('last_error'):
                info['last_error'] = entry.get('last_error')
            if status in {'waiting', 'regenerating'}:
                info['needs_image_regen'] = True
                blocked.add(sn)
            if status == 'aborted':
                info['aborted'] = True
            if not sanitize:
                info['blocked_image_url'] = entry.get('blocked_image_url')
                info['last_prompt'] = entry.get('last_prompt')
            sanitized[sn] = info
        return sanitized, blocked

    def _append_image_regen_history(self, scene_number: int, record: Dict[str, Any]) -> None:
        ws = self._get_working_state()
        history = ws.get('image_regen_history')
        if not isinstance(history, list):
            history = []
        history.append(record)
        if len(history) > 20:
            history = history[-20:]
        ws['image_regen_history'] = history
        self.iteration_context['working_state'] = ws

    async def _clear_sensitive_references(self, scene_number: int, *, reason: str = '') -> None:
        sn = self._normalize_scene_number(scene_number)
        if sn is None:
            return
        ws = self._get_working_state()
        changed = False
        try:
            prepared = dict(ws.get('prepared_last_frames') or {})
            if sn in prepared:
                prepared.pop(sn, None)
                ws['prepared_last_frames'] = prepared
                changed = True
        except Exception:
            pass
        try:
            pr_list = [
                self._normalize_scene_number(x)
                for x in ws.get('priority_prepared_ids') or []
                if self._normalize_scene_number(x) is not None
            ]
            pr_list = [x for x in pr_list if x is not None and x != sn]
            ws['priority_prepared_ids'] = pr_list
            changed = True
        except Exception:
            pass
        try:
            ctx = ws.get('context') or {}
            scenes = ctx.get('scenes_to_generate') or []
            for sc in scenes:
                if not isinstance(sc, dict):
                    continue
                if self._normalize_scene_number(sc.get('scene_number')) != sn:
                    continue
                old_url = sc.get('image_url')
                if old_url:
                    sc['last_sensitive_image_url'] = old_url
                    sc['image_url'] = ''
                    sc['image_cleared_reason'] = reason or 'input_image_sensitive'
                    changed = True
            ctx['scenes_to_generate'] = scenes
            ws['context'] = ctx
        except Exception:
            pass
        if changed:
            self.iteration_context['working_state'] = ws

    async def _handle_sensitive_image_failure(
        self,
        scene_number: Any,
        details_struct: Dict[str, Any],
        args: Dict[str, Any],
    ) -> None:
        sn = self._normalize_scene_number(scene_number)
        if sn is None:
            return
        await self._clear_sensitive_references(sn, reason='input_image_sensitive')

        ws = self._get_working_state()
        attempts = ws.get('image_regen_attempts')
        if not isinstance(attempts, dict):
            attempts = {}
        attempts[sn] = int(attempts.get(sn, 0) or 0) + 1
        ws['image_regen_attempts'] = attempts
        self.iteration_context['working_state'] = ws

        provider = None
        blocked_url = None
        reason = 'input_image_sensitive'
        if isinstance(details_struct, dict):
            provider = details_struct.get('provider')
            blocked_url = details_struct.get('image_url')
            reason = details_struct.get('provider_error', {}).get('message') or reason

        entry = self._upsert_pending_regen_entry(sn, {
            'scene_number': sn,
            'status': 'waiting',
            'reason': reason,
            'blocked_at': time.time(),
            'blocked_image_url': blocked_url,
            'provider': provider,
            'attempts': attempts.get(sn, 1),
            'last_prompt': args.get('prompt'),
        })

        max_attempts = max(int(getattr(self, 'max_image_regen_attempts', 2) or 2), 1)
        if entry.get('attempts', 0) > max_attempts:
            entry['status'] = 'aborted'
            entry['aborted_at'] = time.time()
            ws = self._get_working_state()
            pending = ws.get('pending_image_regen') or {}
            pending[int(sn)] = entry
            ws['pending_image_regen'] = pending
            failed_list = list(ws.get('failed_scenes') or [])
            failed_list.append({
                'scene_number': sn,
                'error': 'input_image_sensitive_exceeded_regen',
                'reason': reason,
                'attempts': entry.get('attempts'),
            })
            ws['failed_scenes'] = failed_list
            self.iteration_context['working_state'] = ws
            try:
                self.logger.error(
                    "IMAGE_REGEN_ABORTED: scene=%s attempts=%s reason=%s",
                    sn,
                    entry.get('attempts'),
                    reason,
                )
            except Exception:
                pass
            return

        try:
            self.logger.warning(
                "IMAGE_REGEN_REQUIRED: scene=%s attempts=%s provider=%s", sn, entry.get('attempts'), provider
            )
        except Exception:
            pass

    async def _apply_regenerated_image(self, scene_number: Any, payload: Dict[str, Any]) -> None:
        sn = self._normalize_scene_number(scene_number)
        if sn is None:
            return
        image_url = None
        if isinstance(payload, dict):
            image_url = payload.get('image_url')
        if not image_url:
            return

        ws = self._get_working_state()
        ctx = ws.get('context') or {}
        scenes = ctx.get('scenes_to_generate') or []
        for sc in scenes:
            if not isinstance(sc, dict):
                continue
            if self._normalize_scene_number(sc.get('scene_number')) != sn:
                continue
            sc['image_url'] = image_url
            sc['image_regen_prompt_text'] = payload.get('prompt_text') or payload.get('prompt') or ''
            sc['image_regenerated_at'] = time.time()
        ctx['scenes_to_generate'] = scenes
        ws['context'] = ctx

        prepared = ws.get('prepared_last_frames')
        if not isinstance(prepared, dict):
            prepared = {}
        prepared[sn] = image_url
        ws['prepared_last_frames'] = prepared

        pr_list = [
            self._normalize_scene_number(x)
            for x in ws.get('priority_prepared_ids') or []
            if self._normalize_scene_number(x) is not None and self._normalize_scene_number(x) != sn
        ]
        pr_list.insert(0, sn)
        ws['priority_prepared_ids'] = pr_list[:8]

        pending = ws.get('pending_image_regen')
        if isinstance(pending, dict) and sn in pending:
            entry = dict(pending.pop(sn) or {})
        else:
            entry = {}
        ws['pending_image_regen'] = pending or {}
        ws['last_image_regen_scene'] = sn
        self.iteration_context['working_state'] = ws

        history_record = {
            'scene_number': sn,
            'image_url': image_url,
            'prompt_text': payload.get('prompt_text') or payload.get('prompt'),
            'applied_at': time.time(),
            'attempts': entry.get('attempts') or (ws.get('image_regen_attempts') or {}).get(sn),
        }
        self._append_image_regen_history(sn, history_record)

        try:
            self.logger.info("IMAGE_REGEN_APPLIED: scene=%s url=%s", sn, image_url)
        except Exception:
            pass

    def _note_image_regen_failure(self, scene_number: Any, error_message: str) -> None:
        sn = self._normalize_scene_number(scene_number)
        if sn is None:
            return
        entry = self._upsert_pending_regen_entry(sn, {
            'status': 'waiting',
            'last_error': error_message,
            'updated_at': time.time(),
        })
        try:
            self.logger.warning("IMAGE_REGEN_FAILED: scene=%s error=%s", sn, error_message)
        except Exception:
            pass

    # === 风格与角色一致性辅助方法 ===

    def _get_style_constraints(self) -> List[str]:
        cached = self.iteration_context.get('_style_constraints_cache')
        if cached is not None:
            return list(cached)

        constraints: List[str] = []
        concept_plan = self._get_concept_plan()

        try:
            isd = concept_plan.get('intelligent_style_design', {}) if isinstance(concept_plan, dict) else {}
            if isinstance(isd, dict):
                for key in [
                    'style_name', 'style_description', 'production_taste',
                    'narrative_style', 'visual_approach', 'emotional_tone'
                ]:
                    val = isd.get(key)
                    if isinstance(val, str) and val.strip():
                        constraints.append(val.strip())
                taxonomy = isd.get('taxonomy')
                if isinstance(taxonomy, dict):
                    for tag_key in ['substyle_label', 'family_label', 'substyle_key']:
                        tag_val = taxonomy.get(tag_key)
                        if isinstance(tag_val, str) and tag_val.strip():
                            constraints.append(tag_val.strip())
                    for token in taxonomy.get('positive_tokens') or []:
                        if isinstance(token, str) and token.strip():
                            constraints.append(token.strip())
            cg = concept_plan.get('consistency_guidelines', {}) if isinstance(concept_plan, dict) else {}
            if isinstance(cg, dict):
                for key in ['style_consistency', 'environment_consistency', 'character_consistency', 'object_consistency']:
                    val = cg.get(key)
                    if isinstance(val, str) and val.strip():
                        constraints.append(val.strip())
        except Exception:
            pass

        try:
            source_input = self.iteration_context.get('source_input') or {}
            creative_guidance = source_input.get('creative_guidance') if isinstance(source_input, dict) else {}
            if isinstance(creative_guidance, dict):
                for key in ['style_notes', 'visual_style', 'production_taste']:
                    val = creative_guidance.get(key)
                    if isinstance(val, str) and val.strip():
                        constraints.append(val.strip())
        except Exception:
            pass

        merged = self._merge_string_list([], constraints)
        if len(merged) > 8:
            merged = merged[:8]
        self.iteration_context['_style_constraints_cache'] = list(merged)
        return merged

    def _get_scene_character_constraints(
        self,
        workflow_state_id: Optional[str],
        scene_number: int
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        cache = self.iteration_context.get('_scene_char_cache') or {}
        wf_key = workflow_state_id or '__default__'
        wf_cache = cache.get(wf_key) or {}
        if scene_number in wf_cache:
            return wf_cache[scene_number]

        wf = self._get_workflow_state_obj(workflow_state_id)
        concept_plan = self._get_concept_plan(wf)
        char_defs = self._get_character_definitions(concept_plan, workflow_state_id)

        names: List[str] = []
        descriptions: List[str] = []
        scene_structs: List[Dict[str, Any]] = []
        scene_texts: List[str] = []

        try:
            if wf:
                sc = wf.get_scene(scene_number)
                if sc is not None:
                    names = [str(n).strip() for n in getattr(sc, 'characters_present', []) or [] if str(n).strip()]
                    descriptions = [str(d).strip() for d in getattr(sc, 'character_descriptions', []) or [] if str(d).strip()]
        except Exception:
            names, descriptions = [], []

        # 若场景缺失，则尝试从概念计划的场景描述中提取
        if not names:
            try:
                sc_defs = (concept_plan.get('scenes') if isinstance(concept_plan, dict) else []) or []
                for entry in sc_defs:
                    try:
                        sid = int(entry.get('scene_number')) if entry.get('scene_number') is not None else None
                    except Exception:
                        sid = None
                    if sid == scene_number:
                        content_el = entry.get('content_elements') or {}
                        possible = content_el.get('characters_present') or []
                        names = [str(n).strip() for n in possible if str(n).strip()]
                        if not descriptions:
                            desc = entry.get('narrative_description') or entry.get('visual_description')
                            if isinstance(desc, str) and desc.strip():
                                descriptions.append(desc.strip())
                        break
            except Exception:
                pass

        # 组装结构化角色约束
        pooled_texts: List[str] = list(descriptions)
        for raw_name in names:
            defn = self._lookup_character_definition(char_defs, raw_name)
            struct = self._build_character_struct(defn, raw_name, descriptions)
            if struct:
                scene_structs.append(struct)
            if not pooled_texts and defn:
                summary = self._summarize_character_definition(defn)
                if summary:
                    pooled_texts.append(summary)

        if names and not scene_structs:
            # 退化：仍构造基础结构描述
            struct = self._build_character_struct({}, "、".join(names), descriptions)
            if struct:
                scene_structs.append(struct)

        candidate_aliases: List[str] = []
        for struct in scene_structs:
            display = struct.get('display_name') if isinstance(struct, dict) else None
            if isinstance(display, str) and display.strip():
                candidate_aliases.append(display.strip())
        if not candidate_aliases:
            candidate_aliases = list(names[:1]) if names else []

        guideline_snippets = self._extract_character_guideline_snippets(
            concept_plan,
            candidate_aliases or names,
            scene_number
        )
        scene_texts = self._merge_string_list([], pooled_texts)
        scene_texts = self._merge_string_list(scene_texts, guideline_snippets)
        if not scene_texts and names:
            scene_texts = ["角色：" + "、".join(names)]

        # 缓存结果
        wf_cache[scene_number] = (scene_structs, scene_texts)
        cache[wf_key] = wf_cache
        self.iteration_context['_scene_char_cache'] = cache
        return scene_structs, scene_texts

    def _merge_string_list(self, existing, additions) -> List[str]:
        result: List[str] = []
        seen = set()

        def _iter(source) -> List[str]:
            if isinstance(source, list):
                return [str(x) for x in source]
            if isinstance(source, (str, int, float)):
                return [str(source)]
            return []

        for item in _iter(existing):
            text = item.strip()
            if text and text not in seen:
                result.append(text)
                seen.add(text)

        for item in _iter(additions):
            text = item.strip()
            if text and text not in seen:
                result.append(text)
                seen.add(text)
        return result

    def _constraint_items(self, values, source: str, default_category: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if not isinstance(values, list):
            values = [values] if values else []
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            items.append({
                "text": text,
                "source": source,
                "category": default_category,
                "lock": "soft",
            })
        return items

    def _merge_items_with_policy(
        self,
        fc_items: List[Dict[str, Any]],
        memory_items: List[Dict[str, Any]],
        merge_mode: str,
        lock_sections: List[str],
    ) -> List[Dict[str, Any]]:
        lock_set = set(lock_sections or [])
        ordered: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        def _mark_lock(entry: Dict[str, Any]) -> Dict[str, Any]:
            if entry.get("category") in lock_set:
                entry["lock"] = "hard"
            return entry

        def _append(items: List[Dict[str, Any]]):
            for entry in items:
                entry = _mark_lock(entry)
                text = entry.get("text", "").strip()
                if not text or text in seen:
                    continue
                ordered.append(entry)
                seen.add(text)

        if merge_mode == "fc_over_memory":
            _append(fc_items)
            _append(memory_items)
        elif merge_mode == "memory_over_fc":
            _append(memory_items)
            _append(fc_items)
        elif merge_mode == "merge_all":
            _append(memory_items)
            _append(fc_items)
        else:
            _append(memory_items)
            _append(fc_items)
        return ordered

    def _build_merge_result(self, items: List[Dict[str, Any]]) -> ConstraintMergeResult:
        locked = [entry["text"] for entry in items if entry.get("lock") == "hard"]
        suggestions = [entry["text"] for entry in items if entry.get("lock") != "hard"]
        flattened = [entry["text"] for entry in items]
        return ConstraintMergeResult(locked=locked, suggestions=suggestions, flattened=flattened)

    def _merge_style_constraints(
        self,
        fc_styles: List[Any],
        style_defaults: List[str],
        policy,
    ) -> ConstraintMergeResult:
        fc_items = self._constraint_items(fc_styles or [], "fc", "style")
        memory_items = self._constraint_items(style_defaults or [], "memory", "style_anchors")
        merged_items = self._merge_items_with_policy(
            fc_items,
            memory_items,
            getattr(policy.merge_policy, "style_constraints", "memory_over_fc"),
            policy.lock_sections,
        )
        return self._build_merge_result(merged_items)

    def _merge_negative_constraints(
        self,
        fc_negatives: List[Any],
        char_structs: List[Dict[str, Any]],
        char_texts: List[str],
        concept_plan: Dict[str, Any],
        scene_number: int,
        policy,
    ) -> ConstraintMergeResult:
        fc_items = self._constraint_items(fc_negatives or [], "fc", "general")
        memory_items = self._collect_negative_constraints(
            char_structs,
            char_texts,
            concept_plan,
            scene_number,
        )
        merged_items = self._merge_items_with_policy(
            fc_items,
            memory_items,
            getattr(policy.merge_policy, "negative_constraints", "memory_over_fc"),
            policy.lock_sections,
        )
        return self._build_merge_result(merged_items)

    def _merge_character_text_constraints(
        self,
        fc_texts: List[Any],
        memory_texts: List[str],
        policy,
    ) -> List[str]:
        fc_items = self._constraint_items(fc_texts or [], "fc", "character_text")
        memory_items = self._constraint_items(memory_texts or [], "memory", "appearance")
        merged_items = self._merge_items_with_policy(
            fc_items,
            memory_items,
            getattr(policy.merge_policy, "character_constraints", "memory_over_fc"),
            policy.lock_sections,
        )
        return [entry["text"] for entry in merged_items]

    def _merge_struct_list(self, existing, additions) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()

        def _iter_structs(source) -> List[Dict[str, Any]]:
            if isinstance(source, list):
                return [obj for obj in source if isinstance(obj, dict)]
            if isinstance(source, dict):
                return [source]
            return []

        for item in _iter_structs(existing) + _iter_structs(additions):
            signature = self._character_struct_signature(item)
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(item)
        return merged

    def _character_struct_signature(self, struct: Dict[str, Any]) -> Tuple:
        if not isinstance(struct, dict):
            return tuple()
        def _tuple(field):
            val = struct.get(field)
            if isinstance(val, list):
                return tuple(str(x) for x in val)
            if isinstance(val, str):
                return (val,)
            return tuple()
        return (
            str(struct.get('name', '')),
            str(struct.get('display_name', '')),
            str(struct.get('species_or_breed', '')),
            str(struct.get('archetype_or_identity', '')),
            _tuple('signature_outfit_or_props'),
            _tuple('key_traits'),
            str(struct.get('role', '')),
        )

    def _get_workflow_state_obj(self, workflow_state_id: Optional[str] = None):
        cache = self.iteration_context.get('_wf_obj_cache') or {}
        wf_id = workflow_state_id
        if not wf_id:
            try:
                ws = self.iteration_context.get('working_state', {}) or {}
                ctx = ws.get('context', {}) or {}
                wf_id = ctx.get('workflow_state_id') or self.iteration_context.get('workflow_state_id')
            except Exception:
                wf_id = None
        key = wf_id or '__default__'
        if key in cache:
            return cache[key]
        try:
            if wf_id:
                from ..core.workflow_state import workflow_manager
                wf = workflow_manager.get_workflow(wf_id)
            else:
                wf = None
        except Exception:
            wf = None
        cache[key] = wf
        self.iteration_context['_wf_obj_cache'] = cache
        return wf

    def _get_concept_plan(self, wf=None) -> Dict[str, Any]:
        cached = self.iteration_context.get('_concept_plan_cache')
        if cached is not None:
            return cached if isinstance(cached, dict) else {}

        concept_plan: Dict[str, Any] = {}
        try:
            ws = self.iteration_context.get('working_state', {}) or {}
            ctx = ws.get('context', {}) or {}
            cp = ctx.get('concept_plan') or {}
            if isinstance(cp, dict):
                concept_plan = cp
        except Exception:
            concept_plan = {}

        if not concept_plan and wf is not None:
            try:
                cp = getattr(wf, 'concept_plan', {}) or {}
                if isinstance(cp, dict):
                    concept_plan = cp
            except Exception:
                pass

        if not concept_plan:
            try:
                src = self.iteration_context.get('source_input') or {}
                cp = src.get('concept_plan') if isinstance(src, dict) else {}
                if isinstance(cp, dict):
                    concept_plan = cp
            except Exception:
                pass

        if not isinstance(concept_plan, dict):
            concept_plan = {}
        self.iteration_context['_concept_plan_cache'] = concept_plan
        return concept_plan

    def _get_character_definitions(
        self,
        concept_plan: Dict[str, Any],
        workflow_state_id: Optional[str]
    ) -> Dict[str, Dict[str, Any]]:
        cache_all = self.iteration_context.get('_character_def_cache') or {}
        key = workflow_state_id or '__default__'
        if key in cache_all:
            cached = cache_all.get(key)
            return cached if isinstance(cached, dict) else {}

        mapping: Dict[str, Dict[str, Any]] = {}
        try:
            characters = (concept_plan.get('content_elements') or {}).get('characters') or []
            self._ingest_character_entries(mapping, characters)
        except Exception:
            pass

        # 项目级角色手册：先查工作流态再查源输入
        project_context = {}
        try:
            wf_obj = self._get_workflow_state_obj(workflow_state_id)
            if wf_obj is not None:
                project_context = getattr(wf_obj, 'project_context', {}) or {}
        except Exception:
            project_context = {}

        try:
            src_input = dict(self.iteration_context.get('source_input') or {})
            if not project_context:
                project_context = src_input.get('project_context') or {}
            elif src_input.get('project_context'):
                # prefer workflow context but merge source hints
                merged_ctx = dict(src_input.get('project_context') or {})
                merged_ctx.setdefault('character_bible', project_context.get('character_bible'))
                for key, value in project_context.items():
                    if key not in merged_ctx or merged_ctx[key] in (None, {}):
                        merged_ctx[key] = value
                project_context = merged_ctx
        except Exception:
            pass

        try:
            bible = project_context.get('character_bible') if isinstance(project_context, dict) else {}
            self._ingest_character_entries(mapping, bible)
        except Exception:
            pass

        cache_all[key] = mapping
        self.iteration_context['_character_def_cache'] = cache_all
        return mapping

    def _ingest_character_entries(
        self,
        mapping: Dict[str, Dict[str, Any]],
        entries: Any,
    ) -> None:
        if not entries:
            return

        if isinstance(entries, dict):
            iterable = entries.values()
        elif isinstance(entries, list):
            iterable = entries
        else:
            iterable = [entries]

        for entry in iterable:
            if not isinstance(entry, dict):
                continue

            normalized_entry = self._normalise_character_entry(entry)
            if not normalized_entry:
                continue

            alias_set = set()
            for key in ['display_name', 'canonical_name', 'canonical_id', 'name']:
                val = normalized_entry.get(key)
                if isinstance(val, str) and val.strip():
                    alias_set.add(val)
            for alias in normalized_entry.get('aliases') or []:
                if isinstance(alias, str) and alias.strip():
                    alias_set.add(alias)

            for alias in list(alias_set):
                normalized = self._normalize_name(alias)
                if not normalized:
                    continue
                existing = mapping.get(normalized)
                if existing:
                    merged = self._merge_character_definitions(existing, normalized_entry)
                    mapping[normalized] = merged
                else:
                    mapping[normalized] = normalized_entry

    def _normalise_character_entry(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert various character schemas into unified definition structure."""

        if not isinstance(entry, dict):
            return None

        def _as_list(value) -> List[str]:
            if isinstance(value, list):
                return [str(v).strip() for v in value if str(v).strip()]
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            return []

        visual_traits = entry.get('visual_traits') or {}
        style_prefs = entry.get('style_preferences') or {}

        display = str(entry.get('display_name') or entry.get('name') or entry.get('canonical_id') or '').strip()
        canonical = str(entry.get('canonical_id') or entry.get('canonical_name') or display).strip()
        if not (display or canonical):
            return None

        species = (
            entry.get('species_or_breed')
            or visual_traits.get('species')
            or entry.get('species')
            or ''
        )
        archetype = (
            entry.get('archetype_or_identity')
            or entry.get('narrative_role')
            or entry.get('role')
            or ''
        )
        signature = _as_list(entry.get('signature_outfit_or_props'))
        if not signature:
            signature = _as_list(visual_traits.get('signature_outfit_or_props'))
        if not signature:
            signature = _as_list(style_prefs.get('signature_outfit_or_props'))

        traits = _as_list(entry.get('key_traits'))
        if visual_traits.get('key_traits'):
            traits.extend(_as_list(visual_traits.get('key_traits')))
        if not traits:
            traits.extend(_as_list(entry.get('personality_traits')))
        description = entry.get('description') or entry.get('long_description')
        if isinstance(description, str) and description.strip():
            traits.append(description.strip())

        role = entry.get('role') or entry.get('narrative_role') or ''

        normalized = {
            'display_name': display or canonical,
            'canonical_name': canonical or display,
            'canonical_id': entry.get('canonical_id') or canonical or display,
            'aliases': _as_list(entry.get('aliases')),
            'species_or_breed': species,
            'archetype_or_identity': archetype,
            'signature_outfit_or_props': list(dict.fromkeys(signature)),
            'key_traits': list(dict.fromkeys(traits)),
            'role': role,
        }

        if style_prefs:
            normalized.setdefault('style_preferences', style_prefs)
        if visual_traits:
            normalized.setdefault('visual_traits', visual_traits)
        if entry.get('reference_assets'):
            normalized.setdefault('reference_assets', entry.get('reference_assets'))
        return normalized

    def _merge_character_definitions(
        self,
        base: Dict[str, Any],
        override: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = dict(base or {})
        for key in ['display_name', 'canonical_name', 'canonical_id', 'species_or_breed', 'archetype_or_identity', 'role']:
            value = override.get(key)
            if value and not merged.get(key):
                merged[key] = value

        def _merge_list_field(field: str) -> None:
            if field not in merged or not isinstance(merged[field], list):
                merged[field] = []
            if override.get(field):
                merged[field] = list(dict.fromkeys(list(merged[field]) + list(override.get(field) or [])))

        for list_field in ['aliases', 'signature_outfit_or_props', 'key_traits']:
            _merge_list_field(list_field)

        for dict_field in ['visual_traits', 'style_preferences', 'reference_assets']:
            merged.setdefault(dict_field, {})
            if isinstance(override.get(dict_field), dict):
                merged[dict_field].update({k: v for k, v in override[dict_field].items() if v is not None})

        return merged

    def _lookup_character_definition(self, mapping: Dict[str, Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        norm = self._normalize_name(name)
        if norm in mapping:
            return mapping[norm]
        # 尝试宽松匹配
        for key, value in mapping.items():
            if norm in key or key in norm:
                return value
        return None

    def _build_character_struct(
        self,
        definition: Optional[Dict[str, Any]],
        fallback_name: str,
        descriptions: List[str]
    ) -> Optional[Dict[str, Any]]:
        name = fallback_name or ''
        if not definition and not name:
            return None

        def _as_list(value) -> List[str]:
            if isinstance(value, list):
                return [str(v).strip() for v in value if str(v).strip()]
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            return []

        display = name
        species = ''
        archetype = ''
        signature = []
        traits = []
        role = ''

        if isinstance(definition, dict):
            display = definition.get('display_name') or definition.get('canonical_name') or name
            species = definition.get('species_or_breed') or ''
            archetype = definition.get('archetype_or_identity') or ''
            signature = _as_list(definition.get('signature_outfit_or_props'))
            traits = _as_list(definition.get('key_traits'))
            role = definition.get('role') or ''
            visual_identity = _as_list(definition.get('visual_identity'))
            for item in visual_identity:
                if item not in traits:
                    traits.append(item)

        for desc in descriptions or []:
            if desc and desc not in traits:
                traits.append(desc)

        signature = list(dict.fromkeys(signature))
        traits = list(dict.fromkeys(traits))

        defn = definition if isinstance(definition, dict) else {}
        struct = {
            'name': defn.get('canonical_name') or defn.get('name') or display,
            'display_name': display,
            'species_or_breed': species,
            'archetype_or_identity': archetype,
            'signature_outfit_or_props': signature,
            'key_traits': traits,
            'role': role,
        }
        return struct

    def _summarize_character_definition(self, definition: Dict[str, Any]) -> Optional[str]:
        if not isinstance(definition, dict):
            return None
        parts: List[str] = []
        display = definition.get('display_name') or definition.get('canonical_name')
        if display:
            parts.append(str(display))
        species = definition.get('species_or_breed')
        if species:
            parts.append(f"物种：{species}")
        archetype = definition.get('archetype_or_identity')
        if archetype:
            parts.append(f"原型：{archetype}")
        traits = definition.get('key_traits') or []
        if traits:
            parts.append("特征：" + "、".join([str(t) for t in traits if str(t).strip()]))
        props = definition.get('signature_outfit_or_props') or []
        if props:
            parts.append("标志道具：" + "、".join([str(p) for p in props if str(p).strip()]))
        return "；".join(parts) if parts else None

    def _normalize_name(self, name: str) -> str:
        if not isinstance(name, str):
            return ''
        return re.sub(r"\s+", "", name).lower()

    def _looks_like_image(self, url: Optional[str]) -> bool:
        if not isinstance(url, str):
            return False
        lowered = url.split('?', 1)[0].lower()
        return lowered.endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp'))

    def _get_default_negative_constraints(self) -> List[str]:
        cached = self.iteration_context.get('_default_negative_constraints')
        if isinstance(cached, list):
            return list(cached)

        defaults = [
            "不要改变角色的物种或身体材质",
            "不要改变角色的服装、道具或身体比例",
            "不要新增未在设定中出现的身体特征或装饰",
        ]
        self.iteration_context['_default_negative_constraints'] = list(defaults)
        return list(defaults)

    def _scene_depends_on_previous(self, scene_number: int) -> bool:
        try:
            ws = self.iteration_context.get('working_state', {}) or {}
            ctx = ws.get('context', {}) or {}
            scenes = ctx.get('scenes_to_generate') or []
            for entry in scenes:
                if not isinstance(entry, dict):
                    continue
                try:
                    sn_val = int(entry.get('scene_number')) if entry.get('scene_number') is not None else None
                except Exception:
                    sn_val = None
                if sn_val is None or sn_val != int(scene_number):
                    continue
                dep = entry.get('depends_on_scene')
                if dep is None:
                    return False
                try:
                    return int(dep) > 0
                except Exception:
                    return bool(dep)
        except Exception:
            pass
        return False

    def _collect_negative_constraints(
        self,
        char_structs: List[Dict[str, Any]],
        char_texts: List[str],
        concept_plan: Dict[str, Any],
        scene_number: int,
    ) -> List[Dict[str, Any]]:
        constraints: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        def _add(sentence: Optional[str], category: str) -> None:
            if not sentence:
                return
            text = str(sentence).strip()
            if not text:
                return
            if len(text) > 160:
                text = text[:160].rstrip('，；、。,. ') + '...'
            if text in seen:
                return
            constraints.append({
                "text": text,
                "source": "memory",
                "category": category,
                "lock": "soft",
            })
            seen.add(text)

        for base in self._get_default_negative_constraints():
            _add(base, "general")

        subjects: List[str] = []
        for struct in char_structs or []:
            if not isinstance(struct, dict):
                continue
            subject = str(struct.get('display_name') or struct.get('name') or '').strip()
            subject_label = subject or '角色'
            if subject:
                subjects.append(subject)

            species = struct.get('species_or_breed')
            if isinstance(species, str) and species.strip():
                _add(f"保持{subject_label}的物种设定（{species.strip()}），不要改变", "appearance")

            archetype = struct.get('archetype_or_identity') or struct.get('role')
            if isinstance(archetype, str) and archetype.strip():
                _add(f"保持{subject_label}的身份设定（{archetype.strip()}），不要改变角色定位", "identity")

            for trait in struct.get('key_traits') or []:
                trait_txt = str(trait).strip()
                if trait_txt:
                    _add(f"不要改变{subject_label}的特征：{trait_txt}", "appearance")

            props = [str(p).strip() for p in (struct.get('signature_outfit_or_props') or []) if str(p).strip()]
            if props:
                _add(f"保持{subject_label}的标志性道具：{'、'.join(props)}，不要新增或移除", "signature_props")

        for desc in char_texts or []:
            description = str(desc).strip()
            if description:
                _add(f"确保角色外观符合设定：{description}", "appearance")

        if self._scene_depends_on_previous(scene_number):
            _add("与上一场景保持角色造型完全一致，包括头部、服饰与体态细节，避免新增或缺失元素", "continuity")

        if not char_structs and concept_plan:
            snippets = self._extract_character_guideline_snippets(concept_plan, subjects or [], scene_number)
            for snippet in snippets:
                _add(f"遵循角色一致性指引：{snippet}", "appearance")

        _add("不要新增未在角色设定中出现的身体细节或装饰", "appearance")

        return constraints

    def _extract_character_guideline_snippets(
        self,
        concept_plan: Dict[str, Any],
        candidate_names,
        scene_number: int
    ) -> List[str]:
        if not isinstance(concept_plan, dict):
            return []
        guidelines = concept_plan.get('consistency_guidelines') or {}
        if not isinstance(guidelines, dict):
            return []
        char_consistency = guidelines.get('character_consistency') or ''
        if not isinstance(char_consistency, str) or not char_consistency.strip():
            return []

        names: List[str] = []
        if isinstance(candidate_names, list):
            names = [str(n) for n in candidate_names if isinstance(n, str)]
        elif isinstance(candidate_names, str):
            names = [candidate_names]

        if not names and isinstance(scene_number, int):
            try:
                sc_defs = (concept_plan.get('scenes') or []) if isinstance(concept_plan, dict) else []
                for entry in sc_defs:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        sid = int(entry.get('scene_number')) if entry.get('scene_number') is not None else None
                    except Exception:
                        sid = None
                    if sid == scene_number:
                        content_el = entry.get('content_elements') or {}
                        candidates = content_el.get('characters_present') or []
                        names = [str(n) for n in candidates if isinstance(n, str)]
                        break
            except Exception:
                pass

        snippets: List[str] = []
        segments = re.split(r'[；。.!?\n]+', char_consistency)
        normalized_names = [self._normalize_name(n) for n in names if isinstance(n, str)]

        for seg in segments:
            snippet = seg.strip()
            if not snippet:
                continue
            if not normalized_names:
                snippets.append(snippet)
                continue
            norm_snippet = self._normalize_name(snippet)
            for nm in normalized_names:
                if nm and nm in norm_snippet:
                    snippets.append(snippet)
                    break

        if not snippets:
            snippets = [char_consistency.strip()]
        return snippets

    async def _execute_dependency_wait(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        pending_scenes = parameters.get("pending_scenes", [])
        self.logger.info(f"等待依赖：{len(pending_scenes)} 个场景")
        return {"success": True, "action_performed": "dependency_wait", "pending_count": len(pending_scenes), "pending_scenes": pending_scenes}

    async def _execute_task_completion(self, workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        context = workflow_state.get("context", {})
        completed_scenes = workflow_state.get("completed_scenes", {}) or {}
        failed_scenes = workflow_state.get("failed_scenes", []) or []
        self.logger.info(f"视频生成完成：成功={len(completed_scenes)} 失败={len(failed_scenes)}")
        # 在任务完成时（按分层原则）统一将对外产物写入 WF（可配置，默认由 orchestrator 负责写入，故此处默认关闭）
        try:
            from ..core.config import settings as _cfg
            write_wf_on_complete = bool(getattr(_cfg, 'REACT_WRITE_WF_ON_COMPLETE_ONLY', False))
        except Exception:
            write_wf_on_complete = False
        if write_wf_on_complete:
            try:
                wf_id = context.get("workflow_state_id")
                if wf_id:
                    from ..core.workflow_state import workflow_manager
                    wf = workflow_manager.get_workflow(wf_id)
                    # completed_scenes 可能是 dict 或 list，统一遍历
                    items = []
                    if isinstance(completed_scenes, dict):
                        for k, v in completed_scenes.items():
                            if isinstance(v, dict):
                                items.append((int(k), v))
                    elif isinstance(completed_scenes, list):
                        for it in completed_scenes:
                            if isinstance(it, dict) and it.get('scene_number') is not None:
                                try:
                                    items.append((int(it['scene_number']), it))
                                except Exception:
                                    continue
                    for sn, rec in items:
                        vu = rec.get('video_url', '') or ''
                        vp = rec.get('video_path', '') or ''
                        vp_txt = rec.get('prompt_text', '') or ''
                        if vu or vp:
                            wf.update_scene(sn, video_url=vu, video_path=vp, video_prompt=vp_txt)
            except Exception:
                pass
        return {
            "success": True,
            "action_performed": "task_completed",
            "summary": {
                "total_scenes": context.get("total_scenes", 0),
                "generated_successfully": len(completed_scenes),
                "generation_failed": len(failed_scenes),
                "completed_scenes": dict(completed_scenes),
                "failed_scenes": failed_scenes,
            },
        }

    async def _finalize_success_results(self, final_action_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """打包 inner（inner_react_state）中的最终产出，交给 orchestrator 落地到 WF。
        返回字段：final_completed_scenes / final_failed_scenes / react_metadata
        """
        ws = context.get("working_state", {}) or {}
        completed = ws.get("completed_scenes", {}) or {}
        failed = ws.get("failed_scenes", []) or []
        # 规范化：将 dict 映射转为 list
        finals = []
        if isinstance(completed, dict):
            for k, rec in completed.items():
                if not isinstance(rec, dict):
                    continue
                finals.append({
                    "scene_number": int(k) if str(k).isdigit() else rec.get("scene_number"),
                    "video_url": rec.get("video_url"),
                    "video_path": rec.get("video_path") or rec.get("file_path"),
                    "prompt_text": rec.get("prompt_text"),
                    "duration": rec.get("duration"),
                })
        elif isinstance(completed, list):
            for rec in completed:
                if not isinstance(rec, dict):
                    continue
                finals.append({
                    "scene_number": rec.get("scene_number"),
                    "video_url": rec.get("video_url"),
                    "video_path": rec.get("video_path") or rec.get("file_path"),
                    "prompt_text": rec.get("prompt_text"),
                    "duration": rec.get("duration"),
                })
        finals_failed = [
            {"scene_number": r.get("scene_number"), "error": r.get("error")}
            for r in failed if isinstance(r, dict)
        ]
        return {
            **(final_action_result or {}),
            "final_completed_scenes": finals,
            "final_failed_scenes": finals_failed,
            "subtask_state": "complete",
            "loop_end_reason": "natural_complete",
            "react_metadata": {
                "total_iterations": len(context.get("iteration_history", [])),
                "success": True,
                "completion_type": "task_complete",
                "agent": self.agent_name,
            },
        }

    async def _finalize_incomplete_results(self, context: Dict[str, Any], task) -> Dict[str, Any]:
        """未完成路径同样返回规范化的阶段性产出，交给 orchestrator 进行集中落盘。

        设计要点：
        - 不改变“反思裁决”与“是否进入下一步”的权责划分，仅提供事实产物（final_*）。
        - finals 从 inner working_state 聚合，避免读取外部 WF，确保内态为唯一真相源。
        - orchestrator 在步尾统一处理落盘，即使本Agent未全量完成，也能将阶段性视频写入 WF。
        """
        ws = context.get("working_state", {}) or {}
        completed = ws.get("completed_scenes", {}) or {}
        failed = ws.get("failed_scenes", []) or []
        # 规范化：将 dict 映射转为 list
        finals = []
        if isinstance(completed, dict):
            for k, rec in completed.items():
                if not isinstance(rec, dict):
                    continue
                finals.append({
                    "scene_number": int(k) if str(k).isdigit() else rec.get("scene_number"),
                    "video_url": rec.get("video_url"),
                    "video_path": rec.get("video_path") or rec.get("file_path"),
                    "prompt_text": rec.get("prompt_text"),
                    "duration": rec.get("duration"),
                })
        elif isinstance(completed, list):
            for rec in completed:
                if not isinstance(rec, dict):
                    continue
                finals.append({
                    "scene_number": rec.get("scene_number"),
                    "video_url": rec.get("video_url"),
                    "video_path": rec.get("video_path") or rec.get("file_path"),
                    "prompt_text": rec.get("prompt_text"),
                    "duration": rec.get("duration"),
                })
        finals_failed = [
            {"scene_number": r.get("scene_number"), "error": r.get("error")}
            for r in failed if isinstance(r, dict)
        ]

        # 简要摘要（用于外层编排与可观测性）
        ctx = ws.get("context", {}) or {}
        total = int(ctx.get("total_scenes", 0) or 0)
        completed_cnt = len(finals)
        failed_cnt = len(finals_failed)
        # 粗略推导 pending：若有场景清单则据此推导，否则仅基于计数
        try:
            scenes_to_generate = ctx.get("scenes_to_generate") or []
            all_ids = [int(s.get("scene_number")) for s in scenes_to_generate if isinstance(s, dict) and s.get("scene_number") is not None]
            done_ids = [int(x.get("scene_number")) for x in finals if isinstance(x, dict) and x.get("scene_number") is not None]
            pending_ids = [sid for sid in all_ids if sid not in set(done_ids)]
            pending_cnt = len(pending_ids)
        except Exception:
            pending_ids = []
            pending_cnt = max(0, total - completed_cnt - failed_cnt)

        summary = {
            "total_scenes": total,
            "generated_successfully": completed_cnt,
            "generation_failed": failed_cnt,
            "pending": pending_cnt,
            "pending_ids": pending_ids[:8],
        }

        # 推断子任务状态与结束原因
        iters = len(context.get("iteration_history", []))
        try:
            max_iters = int(getattr(self, 'max_iterations', 0) or 0)
        except Exception:
            max_iters = 0
        end_reason = "max_iter_reached" if (max_iters and iters >= max_iters) else "incomplete"
        sub_state = "partial" if (completed_cnt > 0 or failed_cnt > 0) else ("blocked" if pending_cnt > 0 else "partial")

        return {
            "success": False,
            "action_performed": "task_incomplete",
            "summary": summary,
            "final_completed_scenes": finals,
            "final_failed_scenes": finals_failed,
            "subtask_state": sub_state,
            "loop_end_reason": end_reason,
            "react_metadata": {
                "total_iterations": len(context.get("iteration_history", [])),
                "success": False,
                "completion_type": "incomplete_with_partials",
                "agent": self.agent_name,
            },
        }

    # ==== REFLECT ====
    async def _reflect_on_results(
        self,
        action_result: Dict[str, Any],
        current_state: Dict[str, Any],
        task: Task,
        iteration: int,
    ) -> Dict[str, Any]:
        action_performed = action_result.get("action_performed", "")
        if action_performed == "task_completed":
            return {"success": True, "task_complete": True, "should_stop": True, "context_updates": {}, "reflection_summary": "all videos generated"}
        if action_performed == "dependency_wait":
            return {"success": True, "task_complete": False, "should_stop": False, "context_updates": {}, "reflection_summary": f"waiting {action_result.get('pending_count', 0)} scenes"}

        # batch_video_generation path
        generation_results = action_result.get("generation_results") or self.get_last_round_results()

        def domain_merge(workflow_state: Dict[str, Any], delta: Dict[str, Any], gen_results: List[Dict[str, Any]]):
            ws = workflow_state or {}
            context = ws.get("context", {})
            scenes_to_generate: List[Dict[str, Any]] = []
            try:
                from ..core.workflow_state import workflow_manager
                wf_id = context.get("workflow_state_id")
                wf = workflow_manager.get_workflow(wf_id) if wf_id else None
                if wf and getattr(wf, 'scenes', None):
                    for sc in wf.scenes:
                        scenes_to_generate.append({
                            "scene_number": getattr(sc, 'scene_number', None),
                            "title": getattr(sc, 'title', ''),
                            "visual_description": getattr(sc, 'visual_description', ''),
                            "duration": getattr(sc, 'duration', settings.DEFAULT_SCENE_DURATION),
                            "depends_on_scene": getattr(sc, 'depends_on_scene', None),
                        })
            except Exception:
                scenes_to_generate = context.get("scenes_to_generate", []) or []

            completed_map = ws.get("completed_scenes", {}) or {}
            if isinstance(completed_map, list):
                completed_map = {r.get('scene_number'): r for r in completed_map if isinstance(r, dict)}
            failed_list = list(ws.get("failed_scenes", []) or [])

            # artifact_keys removed: rely on presence of video artifacts only for completion
            for r in gen_results or []:
                sn = r.get('scene_number')
                if not r.get('success'):
                    failed_list.append(r)
                else:
                    if sn is not None and (r.get('video_url') or r.get('video_path')):
                        completed_map[sn] = r

            completed_scene_numbers = set(completed_map.keys())
            # 完成判定不以“失败排除”作为依据，而是以“完成数达到目标数”为准
            total_targets = len(scenes_to_generate)
            remaining = [s for s in scenes_to_generate if s.get("scene_number") not in completed_scene_numbers]
            done = (len(completed_scene_numbers) >= total_targets)
            summary = (
                f"processed {len(gen_results)}; newly_completed {delta.get('newly_completed',0)}; "
                f"newly_prepared {delta.get('newly_prepared',0)}; remaining {len(remaining)}"
            )
            return {
                'context_updates': {
                    'completed_scenes': completed_map,
                    'failed_scenes': failed_list,
                },
                'done': done,
                'summary': summary,
                'tracker_keys': set(str(k) for k in completed_scene_numbers),
            }

        # 诊断：反射前打印本轮结果条数与场景号
        try:
            _rs = generation_results or []
            _sids = [r.get('scene_number') for r in _rs if isinstance(r, dict)]
            self.logger.info(f"REFLECT_DIAG: generation_results count={len(_rs)} scenes={_sids}")
        except Exception:
            pass

        # 反思合并诊断：对比本轮前后的完成键集合
        try:
            def _keys_from(cs):
                out = set()
                comp = cs.get('completed_scenes', {}) or {}
                if isinstance(comp, dict):
                    for k, v in comp.items():
                        try:
                            if isinstance(v, dict) and (v.get('video_url') or v.get('video_path')):
                                out.add(int(k))
                        except Exception:
                            continue
                elif isinstance(comp, list):
                    for it in comp:
                        if isinstance(it, dict) and it.get('scene_number') is not None and (it.get('video_url') or it.get('video_path')):
                            out.add(int(it.get('scene_number')))
                return out
            before_keys = _keys_from(current_state or {})
        except Exception:
            before_keys = set()

        reflection = await self.reflect_with_reducer(
            action_result={"generation_results": generation_results},
            current_state=current_state,
            domain_merge_fn=domain_merge,
            keys_tracker_name="_prev_video_keys",
        )

        try:
            executed_calls = action_result.get("executed_calls", []) or []
            prepared: Dict[int, str] = {}
            for call in executed_calls:
                try:
                    if not call.get('success'):
                        continue
                    args = call.get('args') or {}
                    payload = call.get('result') or {}
                    if isinstance(payload, dict) and payload.get('image_url') and not (payload.get('video_url') or payload.get('file_path')):
                        sn = args.get('scene_number') if isinstance(args, dict) else None
                        if sn is not None:
                            prepared[int(sn)] = payload.get('image_url')
                except Exception:
                    continue
            if prepared:
                ws = self.iteration_context.get("working_state", {}) or {}
                existing = {}
                try:
                    existing = dict(ws.get('prepared_last_frames') or {})
                except Exception:
                    existing = {}
                merged = dict(existing)
                merged.update(prepared)
                cu = dict(reflection.get('context_updates', {}) or {})
                cu['prepared_last_frames'] = merged
                reflection['context_updates'] = cu
                # 维护优先执行队列（去重追加）
                try:
                    pr_list = list(ws.get('priority_prepared_ids') or [])
                except Exception:
                    pr_list = []
                for sid in prepared.keys():
                    sni = int(sid)
                    if sni not in pr_list:
                        pr_list.append(sni)
                ws['priority_prepared_ids'] = pr_list
                self.iteration_context['working_state'] = ws
        except Exception:
            pass
        # 分层原则：默认不在中途写入外部 WF，仅在任务完成时统一落地
        try:
            from ..core.config import settings as _cfg
            mid_write = bool(getattr(_cfg, 'REACT_WRITE_WF_ON_COMPLETE_ONLY', True))
        except Exception:
            mid_write = True
        if not mid_write:
            try:
                ws_ctx = self.iteration_context.get("working_state", {}).get("context", {})
                workflow_state_id = ws_ctx.get("workflow_state_id")
                if workflow_state_id and generation_results:
                    from ..core.workflow_state import workflow_manager
                    wf = workflow_manager.get_workflow(workflow_state_id)
                    for r in generation_results:
                        if not isinstance(r, dict) or not r.get('success'):
                            continue
                        sn = r.get('scene_number')
                        if sn is None:
                            continue
                        wf.update_scene(int(sn), video_url=r.get('video_url', ''), video_path=r.get('video_path', ''), video_prompt=r.get('prompt_text', ''))
            except Exception:
                pass
        # 反射后：将本轮摘要追加到 inner_react_state.iteration_history（只写内部状态）
        try:
            ws = self.iteration_context.get("working_state", {}) or {}
            hist = list(ws.get('iteration_history') or [])
            rm = dict(self.iteration_context.get('react_metrics', {}) or {})
            completed_map = ws.get('completed_scenes') or {}
            comp_cnt = len(completed_map) if isinstance(completed_map, (dict, list)) else 0
            entry = {
                'summary': reflection.get('reflection_summary'),
                'metrics': {
                    'planned_calls': rm.get('planned_calls', 0),
                    'act_total': rm.get('act_total', 0),
                    'act_success': rm.get('act_success', 0),
                    'artifacts': rm.get('artifacts', 0),
                    'completed_internal': comp_cnt,
                },
                'scenes_in_round': [r.get('scene_number') for r in (generation_results or []) if isinstance(r, dict)],
            }
            hist.append(entry)
            ws['iteration_history'] = hist
            self.iteration_context['working_state'] = ws
            # 诊断：输出内部完成键集合
            try:
                if isinstance(completed_map, dict):
                    keys = [int(k) for k,v in completed_map.items() if isinstance(v, dict)]
                elif isinstance(completed_map, list):
                    keys = [int(it.get('scene_number')) for it in completed_map if isinstance(it, dict) and it.get('scene_number') is not None]
                else:
                    keys = []
                self.logger.info(f"REFLECT_DIAG: completed_internal_keys={sorted(keys)}")
            except Exception:
                pass
        except Exception:
            pass
        try:
            ws2 = self.iteration_context.get('working_state', {}) or {}
            after_keys = _keys_from(ws2)
            added = sorted(list(after_keys - before_keys))
            self.logger.info(f"REFLECT_MERGE_DIAG(video): before={sorted(list(before_keys))} after={sorted(list(after_keys))} added={added}")
        except Exception:
            pass
        return reflection

    # ==== Adapter for ReActAgent ====
    async def _build_plan_only_messages(self, input_data: Dict[str, Any], current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """构建首轮“计划专用”消息：使用 planning_round0 模板，让模型产出总体规划 JSON。
        仅作为本Agent内部ReAct播种，不产生任何外部副作用，也不写入MAS。
        """
        # 准备模板变量（与 _planning_round0 保持一致）
        ws = self.iteration_context.get("working_state", {}) or {}
        ctx = ws.get("context", {}) or {}
        wf_id = ctx.get("workflow_state_id")
        goal_text = self._get_goal_text(wf_id)
        constraints = self._get_constraints_snapshot()
        scenes = ctx.get("scenes_to_generate", []) or []
        if not scenes:
            # 无可规划对象时退回空消息，允许基座继续
            return []
        variables = {
            "goal_text": goal_text,
            "constraints_json": _json.dumps(constraints, ensure_ascii=False),
            "scenes_json": _json.dumps(scenes, ensure_ascii=False),
        }
        try:
            sys_text = self.prompt_manager.render_template(self.agent_name, "planning_round0", variables, auto_reload=False)
        except Exception as e:
            self.logger.debug(f"首轮规划模板渲染失败（忽略，回退观察模板）：{e}")
            return []
        # 补充最小 user 提示，避免仅 system 导致供应商拒绝
        user_hint = "请严格按上面的系统指令，仅输出一个严格的总体规划 JSON（不要额外文字/不要代码围栏）。"
        return [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": user_hint},
        ]

    async def _on_plan_only_completed(self, plan_round: Dict[str, Any], input_data: Dict[str, Any], current_state: Dict[str, Any]) -> None:
        """在首轮plan-only结束后，解析JSON并播种 agent_overall_plan.plan_digest 到本Agent内部状态。
        不写入MAS，仅更新 iteration_context.working_state。
        """
        try:
            # 提取文本内容（run_fc_round 将底层FC结果放在 fc_plan 字段）
            content = None
            if isinstance(plan_round, dict):
                fc = plan_round.get('fc_plan')
                if isinstance(fc, dict):
                    content = (fc.get('content') or '') or (fc.get('llm_response', {}) or {}).get('content')
                if not content:
                    # 容错：也尝试顶层（若调用方直接传入了文本）
                    content = plan_round.get('content')
            text = (content or '').strip()
            if not text:
                return
            # 允许```json包裹
            if text.startswith("```"):
                try:
                    fence = text.split("\n", 1)[0]
                    if fence.startswith("```json"):
                        text = text[len(fence):].strip()
                    if text.endswith("```"):
                        text = text[:-3].strip()
                except Exception:
                    pass
            data = _json.loads(text)
            if not isinstance(data, dict):
                return
            decision = PlanningDecision(**data)
            # 校验 selected_units 与可执行集合一致性（若有execute意图）
            try:
                decision.validate_against_executable(self._extract_executable_ids(current_state))
            except Exception:
                pass
            # 播种 plan_digest/version 到内部工作状态
            pd = decision.plan_digest
            ver = int(decision.version or 1)
            ws = dict(self.iteration_context.get("working_state", {}) or {})
            ctx = dict(ws.get("context", {}) or {})
            aop = dict(ctx.get("agent_overall_plan", {}) or {})
            aop.update({"plan_digest": pd, "version": ver})
            ctx["agent_overall_plan"] = aop
            ws["context"] = ctx
            self.iteration_context["working_state"] = ws
            try:
                preview = (pd[:80] + '...') if isinstance(pd, str) and len(pd) > 80 else pd
                self.logger.info(f"🧭 PLAN_SEED: plan_digest={preview} version={ver}")
            except Exception:
                pass
        except Exception as e:
            # 非关键：失败不阻塞流程
            self.logger.debug(f"Plan-only播种失败（忽略）：{e}")
    async def _think_and_plan(
        self,
        current_state: Dict[str, Any],
        task: Task,
        execution: AgentExecution,
        iteration: int,
    ) -> Dict[str, Any]:
        # 使用滚动规划：基座在首轮已通过 plan-only + 子类播种产生 plan_digest。
        # 若此时仍缺少 plan_digest，视为流程配置错误，显式报错，避免隐式兜底。
        ws = self.iteration_context.get("working_state", {}) or {}
        ctx = ws.get("context", {}) or {}
        aop = dict(ctx.get("agent_overall_plan", {}) or {})
        has_digest = bool(str(aop.get("plan_digest", "") or "").strip())
        if not has_digest:
            raise AgentError("首轮plan-only未播种plan_digest，无法进行滚动规划")
        decision = await self._planning_roundN(current_state)

        intent = decision.get("intent")
        if intent == "halt":
            return {"action": "complete_task", "parameters": {"final_status": "halt_requested"}}
        if intent != "execute":
            # 其它意图（observe/replan）在当前实现中不执行动作，直接报错以避免不确定兜底
            raise AgentError(f"规划意图不支持执行路径: intent={intent}")

        selected: List[int] = decision.get("selected_units") or []
        # 构造 scenes_batch
        all_scenes = ctx.get("scenes_to_generate", []) or []
        by_id = {int(s.get("scene_number")): s for s in all_scenes if isinstance(s, dict) and s.get("scene_number") is not None}
        scenes_batch = []
        for sid in selected:
            if sid in by_id:
                scenes_batch.append(by_id[sid])
            else:
                raise AgentError(f"selected_units 包含未知场景: {sid}")
        plan = {
            "action": "batch_generate_videos",
            "parameters": {
                "scenes_batch": scenes_batch,
                "video_config": ctx.get("video_config", {}),
                "generation_strategy": "fc_autonomous",
            },
        }
        # 调试：打印本轮计划
        try:
            import json as _json
            from ..core.config import settings as _cfg
            max_len = int(getattr(_cfg, 'CONTENT_PREVIEW_CHARS', 300))
            preview = _json.dumps(plan, ensure_ascii=False)
            if isinstance(preview, str) and len(preview) > max_len:
                preview = preview[:max_len] + '...'
            self.logger.info(f"PLAN_DEBUG: {preview}")
        except Exception:
            pass
        return plan

    # ==== Helpers ====
    def _align_results_with_batch(self, results: List[Dict[str, Any]], scenes_batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对缺失 scene_number 的成功结果，按当前批次顺序补齐。
        已包含 scene_number 的项保持不变。
        """
        if not results or not scenes_batch:
            return results
        out: List[Dict[str, Any]] = []
        batch_ids = [s.get("scene_number") for s in scenes_batch]
        fill_iter = iter([sn for sn in batch_ids if sn is not None])
        for r in results:
            if not isinstance(r, dict):
                out.append(r)
                continue
            sn = r.get('scene_number')
            needs_fill = (sn is None) or (not isinstance(sn, int))
            if needs_fill and r.get('success'):
                try:
                    r = dict(r)
                    r['scene_number'] = next(fill_iter)
                except StopIteration:
                    pass
            out.append(r)
        return out

    async def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """重载基类，统一应用“就绪集合/幂等护栏 + 必要参数注入”。

        - 识别“视频生成类”动作（tool metadata + stage=act）并做幂等护栏（已有视频则跳过）。
        - 对“准备类”动作（scene_continuity_preparation.prepare_scene_input）做幂等护栏（已有连续性帧则跳过真实执行并回显结果）。
        - 对 video_generation.generate_with_continuity 注入 workflow_state_id / emit_last_frame / scene_number / image_url(来自已准备连续性帧) / depends_on_scene。
        - 可选约束：仅允许 current_batch 范围内的生成（默认关闭，配置 REACT_ENFORCE_BATCH_SCOPE）。
        """
        try:
            ws = self.iteration_context.get("working_state", {}) or {}
            cb = ws.get("current_batch", []) or []
            allowed = {int(s.get("scene_number")) for s in cb if isinstance(s, dict) and s.get("scene_number") is not None}
        except Exception:
            allowed = set()

        # 是否强制仅允许 current_batch 调用（默认不强制，避免侵入 LLM 决策）
        enforce_scope = False
        try:
            from ..core.config import settings
            enforce_scope = bool(getattr(settings, 'REACT_ENFORCE_BATCH_SCOPE', False))
        except Exception:
            try:
                import os
                enforce_scope = os.getenv('REACT_ENFORCE_BATCH_SCOPE', 'false').lower() == 'true'
            except Exception:
                enforce_scope = False

        results: List[Dict[str, Any]] = []
        for idx, call in enumerate(tool_calls or []):
            try:
                fn = call.get("function", {}).get("name")
                raw = call.get("function", {}).get("arguments", {})
                import json as _json
                args = _json.loads(raw) if isinstance(raw, str) else (raw or {})
                if hasattr(self, "_fc_function_map") and fn in getattr(self, "_fc_function_map", {}):
                    tool_name, action_name = self._fc_function_map[fn]
                else:
                    if '.' in (fn or ''):
                        parts = fn.split('.', 1)
                    else:
                        parts = fn.split('_', 1)
                    if len(parts) == 2:
                        tool_name, action_name = parts[0], parts[1]
                    else:
                        tool_name, action_name = fn, ''

                # 先对“准备类”动作做幂等跳过：若该场景已存在 prepared_last_frames 则直接回显
                try:
                    if fn == 'scene_continuity_preparation.prepare_scene_input':
                        sn_try = args.get('scene_number') if isinstance(args, dict) else None
                        sn_val = int(sn_try) if (sn_try is not None and str(sn_try).isdigit()) else None
                        ws_prepared = (self.iteration_context.get('working_state') or {}).get('prepared_last_frames') or {}
                        cont_url = ws_prepared.get(sn_val) if (isinstance(ws_prepared, dict) and sn_val is not None) else None
                        if isinstance(cont_url, str) and cont_url:
                            # 日志去噪：同一任务内，同一场景只打印一次
                            try:
                                logged = set(self.iteration_context.get('diag_prepare_skip_scenes') or [])
                                if sn_val not in logged:
                                    self.logger.info(f"IDEMPOTENT_PREPARE_SKIP scene={sn_val} url={cont_url}")
                                    logged.add(sn_val)
                                    self.iteration_context['diag_prepare_skip_scenes'] = list(logged)
                            except Exception:
                                pass
                            results.append({
                                "tool": fn,
                                "args": args,
                                "success": True,
                                "result": {
                                    "success": True,
                                    "scene_number": sn_val,
                                    "image_url": cont_url,
                                    "continuity_used": True,
                                    "processing_type": "continuity_frame_reuse_idempotent"
                                }
                            })
                            continue
                except Exception:
                    pass

                # 统一识别“生成类”动作：capabilities 含 text_to_video/image_to_video 或 tags 含 video-generation，且阶段为 act
                is_video_generation_call = False
                try:
                    tool_obj = self._available_tools.get(tool_name)
                    meta = tool_obj.get_metadata() if tool_obj and hasattr(tool_obj, 'get_metadata') else None
                    caps = set((meta.capabilities or []) if meta else [])
                    tags = set((meta.tags or []) if meta else [])
                    stage = None
                    if tool_obj and hasattr(tool_obj, 'get_action_stage') and callable(getattr(tool_obj, 'get_action_stage')):
                        try:
                            stage = tool_obj.get_action_stage(action_name)
                        except Exception:
                            stage = None
                    is_generation_tool = ("text_to_video" in caps) or ("image_to_video" in caps) or ("video-generation" in tags)
                    is_video_generation_call = bool(is_generation_tool and ((stage or 'act') == 'act'))
                except Exception:
                    is_video_generation_call = False

                if is_video_generation_call:
                    sn = args.get("scene_number")
                    if enforce_scope:
                        if (sn is None) and allowed and len(allowed) == 1:
                            try:
                                args["scene_number"] = list(allowed)[0]
                                sn = args["scene_number"]
                            except Exception:
                                sn = None
                        if sn is None or (allowed and int(sn) not in allowed):
                            try:
                                self.logger.warning(f"Reject out-of-scope generation call: tool={tool_name} action={action_name} scene={sn} not in ready set {sorted(list(allowed))}")
                            except Exception:
                                pass
                            results.append({
                                "tool": fn,
                                "args": args,
                                "success": False,
                                "error": "scene_number not in ready set",
                                "error_type": "constraint_violation",
                            })
                            continue

                    # 幂等护栏：若该场景已存在视频产物，则跳过真实执行，避免重复生成
                    already = False
                    video_url = ""
                    video_path = ""
                    try:
                        # 1) 工作态 completed_scenes
                        ws = self.iteration_context.get("working_state", {}) or {}
                        completed = ws.get("completed_scenes", {}) or {}
                        if isinstance(completed, dict):
                            rec = completed.get(int(sn)) or completed.get(str(sn))
                            if isinstance(rec, dict):
                                video_url = rec.get('video_url', '') or ''
                                video_path = rec.get('video_path', '') or ''
                                already = bool(video_url or video_path)
                        elif isinstance(completed, list):
                            for it in completed:
                                if isinstance(it, dict) and (int(it.get('scene_number', -1)) == int(sn)):
                                    video_url = it.get('video_url', '') or ''
                                    video_path = it.get('video_path', '') or ''
                                    already = bool(video_url or video_path)
                                    break
                        # 2) WorkflowState 再确认
                        if not already:
                            ctx2 = (self.iteration_context.get('working_state') or {}).get('context', {}) or {}
                            wf_id2 = ctx2.get('workflow_state_id')
                            if wf_id2:
                                from ..core.workflow_state import workflow_manager as _wm
                                wf2 = _wm.get_workflow(wf_id2)
                                sc2 = wf2.get_scene(int(sn)) if wf2 else None
                                if sc2:
                                    video_url = getattr(sc2, 'video_url', '') or ''
                                    video_path = getattr(sc2, 'video_path', '') or ''
                                    already = bool(video_url or video_path)
                    except Exception:
                        # 幂等检查异常：记录并继续交给基类执行（不掩盖错误路径）
                        self.logger.debug("IDEMPOTENT_CHECK_FAILED: continue without skip")

                    if already:
                        try:
                            self.logger.info(f"IDEMPOTENT_SKIP: tool={tool_name} action={action_name} scene={sn} already has video artifact, skip generation")
                        except Exception:
                            pass
                        results.append({
                            "tool": fn,
                            "args": args,
                            "success": False,
                            "error": "scene already has video",
                            "error_type": "idempotent_skip",
                            "result": {
                                "scene_number": sn,
                                "video_url": video_url,
                                "video_path": video_path,
                            }
                        })
                        continue

                # video_generation.generate_with_continuity 参数注入（非侵入）：
                try:
                    if fn == 'video_generation.generate_with_continuity':
                        # workflow_state_id / emit_last_frame / scene_number
                        try:
                            ws = self.iteration_context.get("working_state", {}) or {}
                            ctx = ws.get("context", {}) or {}
                            wf_id = ctx.get("workflow_state_id") or self.iteration_context.get("workflow_state_id")
                            if wf_id and not args.get('workflow_state_id'):
                                args['workflow_state_id'] = wf_id
                        except Exception:
                            pass
                        if args.get('emit_last_frame') is None:
                            args['emit_last_frame'] = 'auto'
                        try:
                            if args.get('scene_number') is None and allowed and len(allowed) == 1:
                                args['scene_number'] = list(allowed)[0]
                        except Exception:
                            pass
                        # 注入连续性帧：沿用单图入口，设置 image_url，同时打标 image_from_continuity 便于工具层判定来源
                        try:
                            sn_try = args.get('scene_number')
                            sn_val = int(sn_try) if (sn_try is not None and str(sn_try).isdigit()) else None
                        except Exception:
                            sn_val = None
                        try:
                            ws_prepared = (self.iteration_context.get('working_state') or {}).get('prepared_last_frames') or {}
                            cont_url = ws_prepared.get(sn_val) if (isinstance(ws_prepared, dict) and sn_val is not None) else None
                            if isinstance(cont_url, str) and cont_url:
                                if not args.get('image_url'):
                                    args['image_url'] = cont_url
                                # 增加来源标记（工具层可读取但不改变接口契约）
                                args['image_from_continuity'] = True
                        except Exception:
                            pass
                        # depends_on_scene（来源 scenes_to_generate）
                        try:
                            if args.get('depends_on_scene') is None and sn_val is not None:
                                scenes = ((self.iteration_context.get('working_state') or {}).get('context') or {}).get('scenes_to_generate') or []
                                for sc in scenes:
                                    if isinstance(sc, dict) and sc.get('scene_number') == sn_val:
                                        dep_v = sc.get('depends_on_scene')
                                        if dep_v is not None:
                                            try:
                                                args['depends_on_scene'] = int(dep_v) if str(dep_v).isdigit() else dep_v
                                            except Exception:
                                                args['depends_on_scene'] = dep_v
                                        break
                        except Exception:
                            pass

                        # 移除角色约束的自动注入：保持由 LLM 基于可见事实与工具 schema 自主选择
                        # 说明：角色一致性在 FC 提示中以 facts.characters_map 暴露，且工具 schema 暴露 character_constraints；
                        #      由 LLM 决定是否在调用中传入，避免代理层硬塞参数。

                        # 写回修改后的参数
                        try:
                            if isinstance(raw, str):
                                call['function']['arguments'] = _json.dumps(args, ensure_ascii=False)
                            else:
                                call['function']['arguments'] = args
                        except Exception:
                            pass

                except Exception:
                    # 注入阶段整体失败不应阻断执行，交由基类处理
                    pass

                single = [{"function": {"name": fn, "arguments": args}}]
                subres = await super().execute_tool_calls(single)
                results.extend(subres)
            except Exception as e:
                results.append({
                    "tool": call.get("function", {}).get("name"),
                    "args": call.get("function", {}).get("arguments"),
                    "success": False,
                    "error": str(e),
                    "error_type": "execution_error",
                })
        return results

    async def _prepare_and_store_last_frame(self, wf, scene_number: int, video_url: str):
        """提取当前场景视频尾帧并上传，写入“连续性内存”；若提供 wf 则写入 WF.last_frame_url。
        - 始终以工具方式提帧并上传到OSS，返回公开URL
        - 将URL写入 SceneContinuityMemory（供后续 get_final_frame_from_memory 命中）
        - 可选：若 wf 非空，则同步更新 WF 场景的 last_frame_url（软失败忽略）
        """
        if not video_url:
            return
        try:
            if 'scene_continuity_preparation' not in self._available_tools:
                return
            fallback = ''
            try:
                if wf is not None:
                    sc = wf.get_scene(scene_number)
                    if sc and getattr(sc, 'image_url', ''):
                        fallback = sc.image_url
            except Exception:
                fallback = ''

            res = await self.use_tool(
                tool_name='scene_continuity_preparation',
                action='prepare_scene_input',
                parameters={
                    'scene_number': scene_number,
                    'previous_scene_video_url': video_url,
                    'fallback_image_url': fallback,
                }
            )
            payload = getattr(res, 'result', res)
            if isinstance(payload, dict) and payload.get('success') and payload.get('image_url'):
                url = payload.get('image_url', '')
                # 写入连续性内存（全局）
                try:
                    from ..core.scene_continuity_memory import get_scene_continuity_memory
                    mem = get_scene_continuity_memory()
                    await mem.store_scene_final_frame(scene_number, url)
                except Exception:
                    pass
                # 可选写WF的last_frame_url
                try:
                    if wf is not None and url:
                        wf.update_scene(scene_number, last_frame_url=url)
                except Exception:
                    pass
        except Exception:
            return
