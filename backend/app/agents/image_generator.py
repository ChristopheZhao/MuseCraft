"""
Image Generator ReAct Agent - 正确的批量处理迭代逻辑
"""
import asyncio
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .react_agent import ReActAgent, AgentError
from .tools.base_tool import ToolError
from ..models import Task, AgentExecution, AgentType
from ..core.config import settings


class ImageGeneratorAgent(ReActAgent):
    """
    Image Generator ReAct Agent - 批量场景处理的智能图像生成

    正确的ReAct迭代逻辑：
    1. OBSERVE: 观察所有场景状态，识别需要生成的场景
    2. THINK: 分析批量处理策略和优先级
    3. PLAN: 为待生成场景规划当轮批次与策略
    4. ACT: 单轮一次FC，由LLM自主编排多条工具调用（先产提示/再生成，或直接生成）
    5. REFLECT: 检查完成度，决定是否需要下轮迭代
    """
    
    def __init__(self, llms=None):
        super().__init__(
            agent_type=AgentType.IMAGE_GENERATOR,
            agent_name="image_generator",
            max_iterations=settings.IMAGE_GENERATOR_MAX_ITERATIONS,
            timeout_seconds=600,
            llms=llms
        )

    # 覆盖基类的上下文注入：在本Agent的 FC 回合不再自动注入进度/短scratchpad，减少对 planning_roundN 契约的干扰
    def build_react_context_messages(self) -> List[Dict[str, Any]]:
        return []
    
    async def _plan_execution(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        workflow_state: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """ReAct规划：分析所有场景的图像生成需求"""
        
        self._validate_input(input_data, ["concept_plan", "workflow_state_id"])
        
        concept_plan = input_data["concept_plan"]
        workflow_state_id = input_data["workflow_state_id"]
        
        # 获取所有场景数据
        from ..core.workflow_state import workflow_manager
        workflow_state_obj = workflow_manager.get_workflow(workflow_state_id)
        scenes_data = workflow_state_obj.scenes if workflow_state_obj else []
        
        # 分析哪些场景需要生成图像
        scenes_to_generate = []
        scenes_to_skip = []
        
        # 准备概念层 per-scene 角色出现映射（作为固定记忆，不做文本匹配）
        concept_scene_map = {}
        try:
            cp = concept_plan or {}
            for s in (cp.get('scenes') or []):
                try:
                    sn = int(s.get('scene_number')) if s.get('scene_number') is not None else None
                except Exception:
                    sn = None
                if sn is None:
                    continue
                present = (((s.get('content_elements') or {}).get('characters_present')) or [])
                concept_scene_map[sn] = present
        except Exception:
            concept_scene_map = {}

        for scene in scenes_data:
            image_strategy = getattr(scene, 'image_generation_strategy', 'new')
            if image_strategy == 'new':
                present = getattr(scene, 'characters_present', []) or concept_scene_map.get(getattr(scene, 'scene_number', None)) or []
                descs = getattr(scene, 'character_descriptions', []) or []
                scenes_to_generate.append({
                    "scene_number": scene.scene_number,
                    "title": getattr(scene, 'title', ''),
                    "visual_description": getattr(scene, 'visual_description', ''),
                    "duration": getattr(scene, 'duration', 0),
                    "characters_present": present,
                    "character_descriptions": descs,
                })
            else:
                scenes_to_skip.append({
                    "scene_number": scene.scene_number,
                    "reason": getattr(scene, 'continuity_reason', ''),
                    "reuse_from": getattr(scene, 'depends_on_scene', None)
                })
        
        # 构建任务上下文
        task_context = {
            "task_type": "batch_image_generation",
            "total_scenes": len(scenes_data),
            "scenes_to_generate": scenes_to_generate,
            "scenes_to_skip": scenes_to_skip,
            "concept_plan": concept_plan,
            "workflow_state_id": workflow_state_id,
            "intelligent_style": concept_plan.get("intelligent_style_design", {})
        }
        
        plan = f"""批量图像生成任务规划：
需要生成图像的场景: {len(scenes_to_generate)} 个
跳过生成的场景: {len(scenes_to_skip)} 个

目标：为所有需要生成的场景批量创建高质量图像
策略：智能批量处理，优化提示词，并发执行"""
        
        return {
            "plan": plan,
            "context": task_context,
            "completed_scenes": [],
            "failed_scenes": [],
            # inner_react_state 扩展：结果台账与迭代历史（跨轮累积，任务级保留）
            "results_ledger": [],
            "iteration_history": []
        }

    async def _init_working_state_from_workflow(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """从 workflow_state_id 初始化 working_state，并写入 iteration_context。"""
        workflow_state_id = input_data.get("workflow_state_id")
        if not workflow_state_id:
            return {}
        from ..core.workflow_state import workflow_manager
        ws_obj = workflow_manager.get_workflow(workflow_state_id)
        if not ws_obj:
            return {}

        concept_plan = getattr(ws_obj, 'concept_plan', {})
        scenes_data = getattr(ws_obj, 'scenes', [])

        scenes_to_generate = []
        # 概念层 per-scene 角色出现（固定记忆）
        concept_scene_map = {}
        try:
            cp = concept_plan or {}
            for s in (cp.get('scenes') or []):
                try:
                    sn = int(s.get('scene_number')) if s.get('scene_number') is not None else None
                except Exception:
                    sn = None
                if sn is None:
                    continue
                present = (((s.get('content_elements') or {}).get('characters_present')) or [])
                concept_scene_map[sn] = present
        except Exception:
            concept_scene_map = {}
        scenes_to_skip = []
        for scene in scenes_data:
            if getattr(scene, 'image_generation_strategy', 'new') == 'new':
                present = getattr(scene, 'characters_present', []) or concept_scene_map.get(getattr(scene, 'scene_number', None)) or []
                descs = getattr(scene, 'character_descriptions', []) or []
                scenes_to_generate.append({
                    "scene_number": scene.scene_number,
                    "title": getattr(scene, 'title', ''),
                    "visual_description": getattr(scene, 'visual_description', ''),
                    "duration": getattr(scene, 'duration', 0),
                    "characters_present": present,
                    "character_descriptions": descs,
                })
            else:
                scenes_to_skip.append({
                    "scene_number": scene.scene_number,
                    "reason": getattr(scene, 'continuity_reason', ''),
                    "reuse_from": getattr(scene, 'depends_on_scene', None)
                })

        # 可选：从记忆/上下文汇聚器读取概念与脚本参考（解耦，缺失时降级）
        concept_summary: Dict[str, Any] = {}
        scene_refs: Dict[int, Dict[str, Any]] = {}
        try:
            wf_id = workflow_state_id
            try:
                cg = await self.retrieve_creative_guidance(workflow_id=wf_id)
                if isinstance(cg, dict) and cg.get('overall_guidance'):
                    concept_summary = cg.get('overall_guidance') or {}
            except Exception:
                concept_summary = {}
            for sc in scenes_data:
                sn = getattr(sc, 'scene_number', None)
                if sn is None:
                    continue
                try:
                    refs = await self.retrieve_scene_references(workflow_id=wf_id, scene_number=int(sn))
                    if isinstance(refs, dict) and refs:
                        scene_refs[int(sn)] = refs
                except Exception:
                    continue
        except Exception:
            concept_summary = {}
            scene_refs = {}

        working_state = {
            "context": {
                "task_type": "batch_image_generation",
                "total_scenes": len(scenes_data),
                "scenes_to_generate": scenes_to_generate,
                "scenes_to_skip": scenes_to_skip,
                "concept_plan": concept_plan,
                "workflow_state_id": workflow_state_id,
                "intelligent_style": concept_plan.get("intelligent_style_design", {}),
                "concept_summary": concept_summary,
                "scene_references": scene_refs
            },
            "completed_scenes": [],
            "failed_scenes": [],
            "results_ledger": [],
            "iteration_history": []
        }
        self.iteration_context["working_state"] = working_state
        return working_state

    def get_observation_schema(self) -> Dict[str, Any]:
        """覆盖基座的通用Schema：
        - scene_number 收紧为整数或仅由数字组成的字符串，避免空串/非数字进入。
        仅用于LLM结构化观测提示与本地校验提示，不改变ReActAgent的运行逻辑。
        """
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "object",
                    "properties": {
                        "total": {"type": "integer"},
                        "ready": {"type": "integer"},
                        "pending": {"type": "integer"},
                        "completed": {"type": "integer"},
                        "failed": {"type": "integer"}
                    },
                    "required": ["total", "ready", "pending", "completed", "failed"]
                },
                "scenes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "scene_number": {
                                "oneOf": [
                                    {"type": "integer"},
                                    {"type": "string", "pattern": "^[0-9]+$"}
                                ]
                            },
                            "status": {"type": "string", "enum": ["ready", "pending", "completed", "failed"]},
                            "missing": {"type": "array", "items": {"type": "string"}},
                            "depends_on_scene": {"type": ["integer", "string", "null"]},
                            "rationale": {"type": "string"}
                        },
                        "required": ["scene_number", "status"]
                    }
                },
                "notes": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["summary", "scenes"]
        }

    async def _observe_current_state(
        self,
        input_data: Dict[str, Any],
        context: Dict[str, Any],
        iteration: int
    ) -> Dict[str, Any]:
        """OBSERVE: 使用内部工作状态推导当前可执行集合"""
        # 初始化或获取工作状态（与Video生成保持一致的结构）
        working_state = self.iteration_context.get("working_state")
        if working_state is None:
            working_state = await self._init_working_state_from_workflow(input_data)
            if not working_state:
                return {"error": "No workflow state available", "scenes_to_generate": [], "completed_scenes": []}

        # 合并上一轮反思写回的标准化事实（react_state）到本地工作状态
        try:
            ws = dict(self.iteration_context.get("working_state", {}) or {})
            ws = self.merge_react_state_into(ws)
            self.iteration_context["working_state"] = ws
            working_state = ws
        except Exception:
            pass

        # 优先使用 LLM 结构化观察（基座通用路径）
        try:
            facts = self.build_observation_facts(input_data)
            schema = self.get_observation_schema()
            messages = self.build_observation_messages(facts)
            obs = await self.llm_structured_observation(messages, schema)
            if isinstance(obs, dict) and obs.get("summary") and obs.get("scenes"):
                sm = obs.get("summary") or {}
                # 兼容/归一化：用 scenes[].status 统计 pending，以防LLM填充不一致
                try:
                    # 将 ready 视为“可执行的待处理”，与 pending 一起计入待办
                    pending_ids_raw = [
                        it.get('scene_number')
                        for it in (obs.get('scenes') or [])
                        if (isinstance(it, dict) and (it.get('status') in ("pending", "ready")))
                    ]
                except Exception:
                    pending_ids_raw = []
                # 仅用于日志观测：ready 集合（不参与 pending 统计）
                try:
                    ready_ids = [
                        it.get('scene_number')
                        for it in (obs.get('scenes') or [])
                        if (isinstance(it, dict) and it.get('status') == "ready")
                    ]
                except Exception:
                    ready_ids = []
                try:
                    completed_ids = [
                        it.get('scene_number')
                        for it in (obs.get('scenes') or [])
                        if (isinstance(it, dict) and it.get('status') == "completed")
                    ]
                except Exception:
                    completed_ids = []
                # 构建 pending_scenes 供后续阶段使用
                try:
                    ctx = self.iteration_context.get("working_state", {}).get("context", {})
                    scenes_catalog = {int(s.get('scene_number')): s for s in (ctx.get("scenes_to_generate", []) or [])}
                except Exception:
                    scenes_catalog = {}
                # 过滤无效ID与已完成/失败ID，避免重复执行
                try:
                    ws_local = dict(self.iteration_context.get("working_state", {}) or {})
                    comp_list = ws_local.get('completed_scenes') or []
                    if isinstance(comp_list, dict):
                        completed_set = {int(k) for k in comp_list.keys() if str(k).isdigit()}
                    else:
                        completed_set = {int(x.get('scene_number')) for x in comp_list if isinstance(x, dict) and str(x.get('scene_number')).isdigit()}
                    fail_list = ws_local.get('failed_scenes') or []
                    failed_set = {int(x.get('scene_number')) for x in fail_list if isinstance(x, dict) and str(x.get('scene_number')).isdigit()}
                except Exception:
                    completed_set, failed_set = set(), set()

                pending_ids_sanitized: list[int] = []
                for sid in pending_ids_raw:
                    try:
                        sid_int = int(sid)
                    except Exception:
                        # 跳过空/非法 scene 标识，避免构造幽灵任务
                        continue
                    if sid_int in completed_set or sid_int in failed_set:
                        # LLM 观测可能误判；以本地事实为准，从待办中剔除
                        continue
                    pending_ids_sanitized.append(sid_int)

                pending_scenes: list[dict] = []
                for sid_int in pending_ids_sanitized:
                    rec = scenes_catalog.get(sid_int)
                    if rec:
                        pending_scenes.append(rec)
                    else:
                        pending_scenes.append({"scene_number": sid_int})
                # 输出观测日志（以包含 ready 的“可执行待办”计数为准）
                try:
                    self.logger.info(
                        f"OBS_STATE: ready={len(ready_ids) or int(sm.get('ready',0))} pending={len(pending_ids_sanitized)} "
                        f"completed={int(sm.get('completed',0))} failed={int(sm.get('failed',0))}"
                    )
                    if ready_ids:
                        self.logger.info(f"OBS_STATE: ready_ids={ready_ids}")
                    if pending_ids_sanitized:
                        self.logger.info(f"OBS_STATE: pending_ids={pending_ids_sanitized}")
                except Exception:
                    pass
                # 写出一致的任务状态
                obs_out = dict(obs)
                obs_out["pending_scenes"] = pending_scenes
                # 统一：pending 计数包含 ready+pending
                obs_out.setdefault('summary', {})['pending'] = len(pending_ids_sanitized)
                obs_out["task_status"] = "completed" if len(pending_ids_sanitized) == 0 else "in_progress"
                return obs_out
        except Exception as e:
            self.logger.warning(f"结构化观察失败，使用本地兜底：{e}")

        # 兜底：最小启发式（不中断流程）
        ctx = working_state.get("context", {})
        scenes_to_generate = ctx.get("scenes_to_generate", [])
        completed_scenes = working_state.get("completed_scenes", [])
        failed_scenes = working_state.get("failed_scenes", [])
        completed_scene_numbers = {s.get("scene_number") for s in completed_scenes}
        failed_scene_numbers = {s.get("scene_number") for s in failed_scenes}
        pending_scenes = [
            s for s in scenes_to_generate
            if s["scene_number"] not in completed_scene_numbers
            and s["scene_number"] not in failed_scene_numbers
        ]
        observation = {
            "summary": {
                "total": len(scenes_to_generate),
                "ready": len((working_state.get("available_prompts", {}) or {})),
                "pending": len(pending_scenes),
                "completed": len(completed_scenes),
                "failed": len(failed_scenes)
            },
            "scenes": [
                {"scene_number": s.get("scene_number"), "status": "pending", "missing": ["plan_or_exec"]}
                for s in pending_scenes
            ],
            "notes": ["fallback_observation"],
            # 兼容旧下游使用
            "pending_scenes": pending_scenes,
            "task_status": "completed" if len(pending_scenes) == 0 else "in_progress",
        }
        try:
            sm = observation.get("summary", {})
            self.logger.info(
                f"OBS_STATE: ready={int(sm.get('ready',0))} pending={int(sm.get('pending',0))} "
                f"completed={int(sm.get('completed',0))} failed={int(sm.get('failed',0))}"
            )
        except Exception:
            pass
        return observation
    
    # 兼容旧代码的重复定义已移除，避免对 WorkflowState 误用 dict.get
    
    async def _think_and_reason(
        self, 
        observation: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """THINK: 使用总体规划的滚动结果驱动行动意图（复用 ReActAgent 通用循环）。"""
        pending_scenes = observation.get("pending_scenes", [])
        task_status = observation.get("task_status", "in_progress")
        if task_status == "completed" and not pending_scenes:
            try:
                completed_cnt = int(observation.get('completed_count'))
            except Exception:
                completed_cnt = int((observation.get('summary', {}) or {}).get('completed', 0) or 0)
            return {"strategy": "complete_task", "reasoning": f"所有场景已处理完成，成功 {completed_cnt} 个", "action_needed": False}
        if not pending_scenes:
            return {"strategy": "complete_task", "reasoning": "没有待处理场景", "action_needed": False}
        # 其余细节在 _think_and_plan 中通过 _planning_roundN 获取 selected_units 决策
        return {"strategy": "rolling_plan", "action_needed": True}
    
    async def _plan_next_action(
        self, 
        reasoning: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """PLAN: 使用滚动规划结果构造批次计划（selected_units → scenes_batch）。"""
        if not reasoning.get("action_needed", False):
            return {"action": "complete_task", "parameters": {"final_status": reasoning.get("strategy", "completed")}}
        # 通过滚动规划拉取决策
        decision = await self._planning_roundN(workflow_state)
        intent = decision.get("intent")
        if intent == "halt":
            return {"action": "complete_task", "parameters": {"final_status": "halt_requested"}}
        if intent != "execute":
            # 其它意图（observe/replan）当前实现不执行动作，避免不确定兜底
            raise AgentError(f"规划意图不支持执行路径: intent={intent}")
        selected = decision.get("selected_units") or []
        # 场景映射
        ctx = (self.iteration_context.get("working_state", {}) or {}).get("context", {}) or {}
        all_scenes = ctx.get("scenes_to_generate", []) or []
        by_id = {int(s.get("scene_number")): s for s in all_scenes if isinstance(s, dict) and s.get("scene_number") is not None}
        scenes_batch = []
        for sid in selected:
            if sid in by_id:
                scenes_batch.append(by_id[sid])
            else:
                raise AgentError(f"selected_units 包含未知场景: {sid}")
        style_guidance = ctx.get("intelligent_style", {}) or {}
        self.logger.info(f"📋 PLAN: 批量生成 {len(scenes_batch)} 个场景的图像")
        return {
            "action": "batch_generate_images",
            "parameters": {
                "scenes_batch": scenes_batch,
                "style_guidance": style_guidance,
                "generation_strategy": "rolling_fc"
            }
        }
    
    async def _execute_action(
        self, 
        action_plan: Dict[str, Any], 
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session,
        iteration: int
    ) -> Dict[str, Any]:
        """ACT: 执行批量图像生成"""
        
        action = action_plan["action"]
        parameters = action_plan["parameters"]
        
        # 获取内部工作状态
        workflow_state = self.iteration_context.get("working_state")
        if not workflow_state:
            return {"success": False, "error": "No working state available"}
        
        if action == "batch_generate_images":
            # 仅构造消息，执行统一走基座 run_fc_round（保持 FC 自主编排）
            scenes_batch = parameters.get("scenes_batch", [])
            style_guidance = parameters.get("style_guidance", {})
            messages = self.build_fc_messages_for_batch(scenes_batch, style_guidance)
            round_outcome = await self.run_fc_round(
                messages=messages,
                context_description="批量调用图像生成工具",
                temperature=0.2,
            )
            # 诊断：统计 planned vs executed
            try:
                fc_plan = round_outcome.get('fc_plan') if isinstance(round_outcome, dict) else None
                planned_calls = 0
                if isinstance(fc_plan, dict):
                    planned_calls = len(fc_plan.get('tool_calls') or [])
                executed_calls = list(round_outcome.get('executed_calls') or [])
            except Exception:
                planned_calls = 0
                executed_calls = []
            # 解析 planning_roundN 文本中的 PlanningDecision（若有），用于维护全局计划摘要
            try:
                fc = round_outcome.get('fc_plan') if isinstance(round_outcome, dict) else None
                lr = (fc or {}).get('llm_response') if isinstance(fc, dict) else None
                content = None
                if isinstance(lr, dict):
                    content = lr.get('content')
                if not content:
                    content = (fc or {}).get('content') if isinstance(fc, dict) else None
                text = (content or '').strip()
                if text.startswith("```"):
                    first = text.split('\n', 1)[0]
                    if first.startswith("```json"):
                        text = text[len(first):].strip()
                    if text.endswith("```"):
                        text = text[:-3].strip()
                if text:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        pd = str(data.get('plan_digest') or '').strip()
                        ver = int(data.get('version') or 0)
                        if pd:
                            ws = dict(self.iteration_context.get("working_state", {}) or {})
                            ctx = dict(ws.get("context", {}) or {})
                            aop = dict(ctx.get("agent_overall_plan", {}) or {})
                            aop.update({"plan_digest": pd})
                            if ver:
                                aop["version"] = ver
                            ctx["agent_overall_plan"] = aop
                            ws["context"] = ctx
                            self.iteration_context["working_state"] = ws
                            try:
                                pv = (pd[:80] + '...') if isinstance(pd, str) and len(pd) > 80 else pd
                                self.logger.info(f"🧭 PLAN_UPDATE_OK: plan_digest={pv} version={ver or aop.get('version')} (from FC content)")
                            except Exception:
                                pass
            except Exception:
                pass
            results = round_outcome.get("results") or []
            # 统一以 executed_calls 解析为准，避免部分供应商只保留最后一次调用结果的情况
            try:
                parsed = await self._postprocess_executed_results(executed_calls or [])
                if parsed:
                    # 合并去重：以 scene_number 为键，优先采用包含 image_url/file_path 的项
                    by_id = {}
                    for r in (results or []):
                        sn = r.get('scene_number') if isinstance(r, dict) else None
                        if sn is not None:
                            by_id[int(sn)] = r
                    for r in parsed:
                        sn = r.get('scene_number')
                        if sn is None:
                            continue
                        prev = by_id.get(int(sn))
                        def _score(x):
                            if not isinstance(x, dict):
                                return 0
                            return int(bool(x.get('image_url'))) + int(bool(x.get('image_path') or x.get('file_path')))
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
                    self.logger.info(f"ACT_DIAG(image): planned={planned_calls} executed={len(executed_calls)} parsed={len(parsed or [])} merged={len(results or [])} exec_scenes={exec_scenes} parsed_scenes={parsed_scenes} merged_scenes={merged_scenes}")
                except Exception:
                    pass
            except Exception:
                if not results:
                    results = []
            # 将本轮结果写回迭代上下文，便于后续观察与事实注入（避免复用上一轮快照造成重复动作）
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
                        'image_url': r.get('image_url'),
                        'file_path': r.get('image_path') or r.get('file_path'),
                        'prompt_text': r.get('prompt_text'),
                        'ts': ts,
                        'agent': 'image_generator'
                    }
                    ledger.append(entry)
                ws['results_ledger'] = ledger
                self.iteration_context['working_state'] = ws
            except Exception:
                pass
            return {
                "action_performed": "batch_image_generation",
                "batch_size": len(scenes_batch),
                "generation_results": results,
                "executed_calls": executed_calls,
                "llm_react_contract": round_outcome.get("contract"),
            }
        elif action == "complete_task":
            return await self._execute_task_completion(workflow_state)
        else:
            raise AgentError(f"Unknown action: {action}")

    # === ReAct 首轮/滚动规划接入（与 video_generator 对齐）===
    async def _build_plan_only_messages(self, input_data: Dict[str, Any], current_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """首轮计划专用消息：渲染 planning_round0，产出总体规划 JSON（不执行外部操作）。"""
        # 基于现有 working_state 初始化上下文
        ws = self.iteration_context.get("working_state", {}) or {}
        ctx = ws.get("context", {}) or {}
        # 尝试填充 scenes_to_generate
        if not ctx.get("scenes_to_generate"):
            ws = await self._init_working_state_from_workflow(input_data)
            ctx = ws.get("context", {}) if isinstance(ws, dict) else {}
        scenes = ctx.get("scenes_to_generate", []) or []
        if not scenes:
            return []
        # 构造模板变量
        from ..core.workflow_state import workflow_manager
        wf_id = ctx.get("workflow_state_id")
        goal_text = f"为 {len(scenes)} 个场景生成新图像，保持风格一致并服务下游视频合成。工作流ID={wf_id}"
        constraints = {
            "style": (ctx.get("intelligent_style") or {}).get("style_name") or "",
            "size_options": ["1024x1024", "1024x1792", "1792x1024"],
        }
        variables = {
            "goal_text": goal_text,
            "constraints_json": json.dumps(constraints, ensure_ascii=False),
            "scenes_json": json.dumps(scenes, ensure_ascii=False),
        }
        try:
            sys_text = self.prompt_manager.render_template("agents/image_generator", "planning_round0", variables, auto_reload=False)
        except Exception:
            return []
        # Zhipu 要求至少包含一条 user 消息；首轮 plan-only 也需满足消息结构
        user_hint = (
            "请严格按上面的系统指令，仅输出一个严格的总体规划 JSON（不要额外文字/不要代码围栏）。"
        )
        return [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": user_hint},
        ]

    async def _on_plan_only_completed(self, plan_round: Dict[str, Any], input_data: Dict[str, Any], current_state: Dict[str, Any]) -> None:
        """首轮plan-only返回后播种 agent_overall_plan.plan_digest/version（仅本Agent内部）。"""
        try:
            fc = plan_round.get('fc_plan') if isinstance(plan_round, dict) else None
            lr = (fc or {}).get('llm_response') if isinstance(fc, dict) else None
            content = None
            if isinstance(lr, dict):
                content = lr.get('content')
            if not content:
                content = plan_round.get('content') if isinstance(plan_round, dict) else None
            text = (content or '').strip()
            if not text:
                return
            if text.startswith("```"):
                try:
                    first = text.split('\n', 1)[0]
                    if first.startswith("```json"):
                        text = text[len(first):].strip()
                    if text.endswith("```"):
                        text = text[:-3].strip()
                except Exception:
                    pass
            data = json.loads(text)
            if not isinstance(data, dict):
                return
            pd = str(data.get('plan_digest') or '').strip()
            ver = int(data.get('version') or 1)
            if not pd:
                return
            ws = dict(self.iteration_context.get("working_state", {}) or {})
            ctx = dict(ws.get("context", {}) or {})
            aop = dict(ctx.get("agent_overall_plan", {}) or {})
            aop.update({"plan_digest": pd, "version": ver})
            ctx["agent_overall_plan"] = aop
            ws["context"] = ctx
            self.iteration_context["working_state"] = ws
            try:
                pv = (pd[:80] + '...') if isinstance(pd, str) and len(pd) > 80 else pd
                self.logger.info(f"🧭 PLAN_SEED: plan_digest={pv} version={ver}")
            except Exception:
                pass
        except Exception:
            pass

    async def _planning_roundN(self, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """滚动规划：基于已播种的 plan_digest 选择下一批待执行的场景集合。"""
        ws = self.iteration_context.get("working_state", {}) or {}
        ctx = ws.get("context", {}) or {}
        aop = ctx.get("agent_overall_plan", {}) or {}
        plan_digest = str(aop.get("plan_digest") or '').strip()
        if not plan_digest:
            raise AgentError("首轮plan-only未播种plan_digest，无法进行滚动规划")
        # 计划纲要（截断预览）
        try:
            steps = aop.get("steps") or aop.get("stages") or []
            plan_outline = json.dumps(steps[:6], ensure_ascii=False)
        except Exception:
            plan_outline = "[]"
        progress_summary = self.build_progress_summary() or ""
        scratchpad = self.build_scratchpad(k=2) or ""
        observation_json = json.dumps(current_state, ensure_ascii=False)
        variables = {
            "plan_digest": plan_digest,
            "plan_outline": plan_outline,
            "progress_summary": progress_summary,
            "scratchpad": scratchpad,
            "observation_json": observation_json,
        }
        sys_text = self.prompt_manager.render_template("agents/image_generator", "planning_roundN", variables, auto_reload=False)
        messages = [{"role": "system", "content": sys_text}]
        # Zhipu chat_completion 要求至少包含一条 user 消息；仅 system 会触发 400 (messages 参数非法)
        # 这里补充最小 user 指令，保持 Prompt Neutrality（不出现工具/参数名），仅强调“只输出JSON”。
        try:
            user_hint = "请严格按上面的系统指令，仅输出一个JSON对象（不要额外文字、不要代码围栏）。"
            messages.append({"role": "user", "content": user_hint})
        except Exception:
            pass
        # 使用结构化观察通道获取 JSON
        schema = {
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
        data = await self.llm_structured_observation(messages, schema)
        if not isinstance(data, dict):
            raise AgentError("滚动图像规划未返回有效JSON")
        return data
    
    def build_fc_messages_for_batch(
        self,
        scenes_batch: List[Dict[str, Any]],
        style_guidance: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """构造基于 planning_roundN 模板的FC消息（滚动规划 + 执行合一）。"""
        # 读取已播种计划摘要、进度、观察
        ws = self.iteration_context.get("working_state", {}) or {}
        ctx = ws.get("context", {}) or {}
        aop = ctx.get("agent_overall_plan", {}) or {}
        plan_digest = str(aop.get("plan_digest") or '').strip()
        try:
            steps = aop.get("steps") or aop.get("stages") or []
            plan_outline = json.dumps(steps[:6], ensure_ascii=False)
        except Exception:
            plan_outline = "[]"
        progress_summary = self.build_progress_summary() or ""
        scratchpad = self.build_scratchpad(k=2) or ""
        observation = self.iteration_context.get("last_observation") or {}
        if not observation:
            # 兜底：从 working_state 推导最小观察
            observation = {"summary": {}, "scenes": [], "pending_scenes": scenes_batch}
        # 将全局风格指导与角色事实并入观测，作为FC的“中立事实”输入
        try:
            obs_aug = dict(observation)
            ctx = (self.iteration_context.get("working_state", {}) or {}).get("context", {}) or {}
            # 风格指导：来自 intelligent_style（概念决策），作为高层抽象存在
            obs_aug["style_guidance"] = style_guidance or ctx.get("intelligent_style", {}) or {}
            # 角色事实：从 scenes_to_generate / WF.scene / concept_plan 提取
            char_map = {}
            try:
                scenes_cat = {int(s.get('scene_number')): s for s in (ctx.get('scenes_to_generate') or []) if isinstance(s, dict) and s.get('scene_number') is not None}
            except Exception:
                scenes_cat = {}
            # WF 优先
            try:
                wf_id = ctx.get('workflow_state_id')
                if wf_id:
                    from ..core.workflow_state import workflow_manager
                    wf = workflow_manager.get_workflow(wf_id)
                else:
                    wf = None
            except Exception:
                wf = None
            batch_ids = [s.get('scene_number') for s in (scenes_batch or []) if isinstance(s, dict)]
            for sid in batch_ids:
                try:
                    sn = int(sid) if sid is not None else None
                except Exception:
                    sn = None
                if sn is None:
                    continue
                names = []
                descs = []
                if wf:
                    try:
                        sc = wf.get_scene(sn)
                        if sc:
                            n = list(getattr(sc, 'characters_present', []) or [])
                            d = list(getattr(sc, 'character_descriptions', []) or [])
                            if n:
                                names = [str(x) for x in n if str(x).strip()]
                            if d:
                                descs = [str(x) for x in d if str(x).strip()]
                    except Exception:
                        pass
                if (not names) and scenes_cat.get(sn):
                    try:
                        n = list(scenes_cat[sn].get('characters_present') or [])
                        if n:
                            names = [str(x) for x in n if str(x).strip()]
                        d = list(scenes_cat[sn].get('character_descriptions') or [])
                        if d:
                            descs = [str(x) for x in d if str(x).strip()]
                    except Exception:
                        pass
                if not names:
                    try:
                        cp = ctx.get('concept_plan') or {}
                        for sdef in (cp.get('scenes') or []):
                            sid2 = int(sdef.get('scene_number')) if sdef.get('scene_number') is not None else None
                            if sid2 == sn:
                                nn = (((sdef.get('content_elements') or {}).get('characters_present')) or [])
                                if nn:
                                    names = [str(x) for x in nn if str(x).strip()]
                                break
                    except Exception:
                        pass
                if names or descs:
                    char_map[sn] = {"names": names, "descriptions": descs}
            obs_aug["characters_map"] = char_map
            observation_json = json.dumps(obs_aug, ensure_ascii=False)
        except Exception:
            observation_json = json.dumps(observation, ensure_ascii=False)
        # 适度诊断：DEBUG 级别输出可见的风格/角色事实摘要（不打印大对象）
        try:
            import logging as _lg
            if self.logger.isEnabledFor(_lg.DEBUG):
                try:
                    obs_preview = json.loads(observation_json)
                except Exception:
                    obs_preview = {}
                ch_map = obs_preview.get('characters_map') or {}
                ch_cnt = len(ch_map) if isinstance(ch_map, dict) else 0
                has_style = bool(obs_preview.get('style_guidance'))
                self.logger.debug(
                    f"FC_FACTS(image): style={'yes' if has_style else 'no'}, roles_scenes={ch_cnt}"
                )
        except Exception:
            pass

        variables = {
            "plan_digest": plan_digest,
            "plan_outline": plan_outline,
            "progress_summary": progress_summary,
            "scratchpad": scratchpad,
            "observation_json": observation_json,
        }
        try:
            sys_text = self.prompt_manager.render_template("agents/image_generator", "planning_roundN", variables, auto_reload=False)
        except Exception:
            sys_text = None

        messages: List[Dict[str, Any]] = []
        if sys_text:
            messages.append({"role": "system", "content": sys_text})
        # Zhipu 需要至少一条 user 消息；保持中立，不出现工具/参数名
        messages.append({
            "role": "user",
            "content": "请基于上述信息进行本轮决策：当 intent 为 execute 时，必须在同一响应中通过函数调用执行所选对象；文本部分仅输出一个严格的 PlanningDecision JSON（不要其他文字/围栏）。"
        })
        return messages
    
    async def _postprocess_executed_results(self, executed_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """标准化采集：返回 image_url 或 file_path 的调用均视为图像产物。

        - 兼容 ToolOutput：若 payload 为对象则取其 result 字段
        - 统一 scene_number 类型为 int（能转则转）
        """
        results: List[Dict[str, Any]] = []
        for call in executed_calls or []:
            try:
                if not call.get("success"):
                    continue
                args = call.get("args") or {}
                payload = call.get("result") or {}
                # 兼容 ToolOutput
                try:
                    if hasattr(payload, 'result'):
                        payload = getattr(payload, 'result')
                except Exception:
                    pass
                if isinstance(payload, dict) and (payload.get("image_url") or payload.get("file_path") or payload.get("image_path")):
                    scene_num = args.get("scene_number") or payload.get("scene_number")
                    try:
                        if scene_num is not None:
                            scene_num = int(scene_num)
                    except Exception:
                        pass
                    results.append({
                        "success": True,
                        "scene_number": scene_num,
                        "image_url": payload.get("image_url", ""),
                        "image_path": payload.get("file_path") or payload.get("image_path") or "",
                        "prompt_text": args.get("prompt") or payload.get("prompt_text") or payload.get("prompt") or "",
                    })
            except Exception:
                continue
        return results
    
    # 手动兜底路径已移除：严格走 Function Call 自主规划
    
    # （已移除 _store_generated_image，交由基座自动持久化处理）
    
    async def _execute_task_completion(self, workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务完成：汇总所有结果"""
        
        context = workflow_state.get("context", {})
        completed_scenes = workflow_state.get("completed_scenes", [])
        failed_scenes = workflow_state.get("failed_scenes", [])
        scenes_to_skip = context.get("scenes_to_skip", [])
        
        self.logger.info(f"✅ 图像生成任务完成")
        self.logger.info(f"   - 成功生成: {len(completed_scenes)} 个场景")
        self.logger.info(f"   - 生成失败: {len(failed_scenes)} 个场景") 
        self.logger.info(f"   - 跳过生成: {len(scenes_to_skip)} 个场景")
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
                    items = []
                    if isinstance(completed_scenes, list):
                        for it in completed_scenes:
                            if isinstance(it, dict) and it.get('scene_number') is not None:
                                try:
                                    items.append((int(it['scene_number']), it))
                                except Exception:
                                    continue
                    for sn, rec in items:
                        iu = rec.get('image_url', '') or ''
                        ip = rec.get('image_path', '') or ''
                        pt = rec.get('prompt_text', '') or ''
                        if iu or ip:
                            wf.update_scene(sn, image_url=iu, image_path=ip, image_prompt=pt)
            except Exception:
                pass
        
        return {
            "success": True,
            "action_performed": "task_completed",
            "summary": {
                "total_scenes": context.get("total_scenes", 0),
                "generated_successfully": len(completed_scenes),
                "generation_failed": len(failed_scenes),
                "skipped_scenes": len(scenes_to_skip),
                "completed_scenes": completed_scenes,
                "failed_scenes": failed_scenes
            }
        }

    async def _finalize_success_results(self, final_action_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """打包 inner（inner_react_state）中的最终产出，交给 orchestrator 落地到 WF。
        返回字段：final_completed_scenes / final_failed_scenes / react_metadata
        """
        ws = context.get("working_state", {}) or {}
        completed = ws.get("completed_scenes", []) or []
        failed = ws.get("failed_scenes", []) or []
        # 规范化：仅保留必要字段
        def _norm(rec):
            if not isinstance(rec, dict):
                return {}
            return {
                "scene_number": rec.get("scene_number"),
                "image_url": rec.get("image_url"),
                "image_path": rec.get("image_path") or rec.get("file_path"),
                "prompt_text": rec.get("prompt_text"),
            }
        finals = [_norm(r) for r in completed if isinstance(r, dict)]
        finals_failed = [
            {"scene_number": r.get("scene_number"), "error": r.get("error")}
            for r in failed if isinstance(r, dict)
        ]
        return {
            **(final_action_result or {}),
            "final_completed_scenes": finals,
            "final_failed_scenes": finals_failed,
            "react_metadata": {
                "total_iterations": len(context.get("iteration_history", [])),
                "success": True,
                "completion_type": "task_complete",
                "agent": self.agent_name,
            },
        }
    
    async def _reflect_on_results(
        self, 
        action_result: Dict[str, Any], 
        current_state: Dict[str, Any],
        task: Task,
        iteration: int
    ) -> Dict[str, Any]:
        """REFLECT: 反思批量执行结果（薄层）：调用基座通用反思助手并执行领域合并。"""
        action_performed = action_result.get("action_performed", "")
        if action_performed == "task_completed":
            return {
                "success": True,
                "task_complete": True,
                "should_stop": True,
                "context_updates": {},
                "reflection_summary": "所有图像生成任务已完成"
            }

        def domain_merge(workflow_state: Dict[str, Any], delta: Dict[str, Any], generation_results: List[Dict[str, Any]]):
            ws = workflow_state or {}
            context = ws.get("context", {})
            scenes_to_generate = context.get("scenes_to_generate", [])

            # 合并 available_prompts
            avail_prompts = dict(ws.get("available_prompts", {}))
            for k, v in (delta.get('prepared_prompts') or {}).items():
                avail_prompts[str(k)] = v

            # 去重合并完成/失败：以 scene_number 为键构建映射，优先保留含产物的记录
            prev_completed = ws.get("completed_scenes", []) or []
            completed_map: Dict[int, Dict[str, Any]] = {}
            if isinstance(prev_completed, dict):
                # 兼容：若此前为映射，直接拷贝
                for k, v in prev_completed.items():
                    try:
                        completed_map[int(k)] = v
                    except Exception:
                        continue
            else:
                for it in prev_completed:
                    if not isinstance(it, dict):
                        continue
                    sn = it.get('scene_number')
                    try:
                        sn_int = int(sn) if sn is not None else None
                    except Exception:
                        sn_int = None
                    if sn_int is None:
                        continue
                    existing = completed_map.get(sn_int)
                    if existing is None:
                        completed_map[sn_int] = it
                    else:
                        # 若新旧都存在，保留包含本地路径/URL的较优者
                        def _score(x: Dict[str, Any]) -> int:
                            return int(bool(x.get('image_url'))) + int(bool(x.get('image_path') or x.get('file_path')))
                        if _score(it) >= _score(existing):
                            completed_map[sn_int] = it

            failed_scenes = list(ws.get("failed_scenes", []) or [])
            artifact_keys = set(delta.get('artifact_scenes') or set())

            for r in generation_results or []:
                if not r.get('success'):
                    failed_scenes.append(r)
                    continue
                sn = r.get('scene_number')
                try:
                    sn_int = int(sn) if sn is not None else None
                except Exception:
                    sn_int = None
                if sn_int is None:
                    continue
                # 以产物证据或增量标记为准
                has_artifact = bool(r.get('image_url') or r.get('image_path') or r.get('file_path'))
                in_delta = (str(sn_int) in artifact_keys) or (sn_int in artifact_keys)
                if has_artifact or in_delta:
                    prev = completed_map.get(sn_int)
                    if prev is None:
                        completed_map[sn_int] = r
                    else:
                        # 保留包含产物的更优记录
                        def _score(x: Dict[str, Any]) -> int:
                            return int(bool(x.get('image_url'))) + int(bool(x.get('image_path') or x.get('file_path')))
                        if _score(r) >= _score(prev):
                            completed_map[sn_int] = r

            completed_list = list(completed_map.values())
            completed_scene_numbers = set(completed_map.keys())
            failed_scene_numbers = {s.get("scene_number") for s in failed_scenes if isinstance(s, dict)}
            remaining_scenes = [
                s for s in scenes_to_generate
                if s.get("scene_number") not in completed_scene_numbers
                and s.get("scene_number") not in failed_scene_numbers
            ]

            done = len(remaining_scenes) == 0
            summary = (
                f"处理 {len(generation_results or [])} 个；新增执行 {delta.get('newly_completed',0)}；"
                f"新增前置 {delta.get('newly_prepared',0)}；剩余 {len(remaining_scenes)}"
            )
            return {
                'context_updates': {
                    'completed_scenes': completed_list,
                    'failed_scenes': failed_scenes,
                    'available_prompts': avail_prompts,
                },
                'done': done,
                'summary': summary,
                'tracker_keys': set(avail_prompts.keys()),
            }

        reflection = await self.reflect_with_reducer(
            action_result=action_result,
            current_state=current_state,
            domain_merge_fn=domain_merge,
            keys_tracker_name="_prev_ap_keys",
        )
        # 反思合并诊断：对比本轮前后的完成键集合
        try:
            # before keys from current_state
            def _keys_from(cs):
                out = []
                try:
                    comp = cs.get('completed_scenes', []) or []
                    for it in comp:
                        if isinstance(it, dict) and it.get('scene_number') is not None:
                            out.append(int(it.get('scene_number')))
                except Exception:
                    pass
                return set(out)
            before_keys = _keys_from(current_state)
            ws2 = self.iteration_context.get('working_state', {}) or {}
            after_keys = _keys_from(ws2)
            added = sorted(list(after_keys - before_keys))
            self.logger.info(f"REFLECT_MERGE_DIAG(image): before={sorted(list(before_keys))} after={sorted(list(after_keys))} added={added}")
        except Exception:
            pass
        # 反射后：将本轮摘要追加到 inner_react_state.iteration_history（只写内部状态）
        try:
            ws = self.iteration_context.get("working_state", {}) or {}
            hist = list(ws.get('iteration_history') or [])
            rm = dict(self.iteration_context.get('react_metrics', {}) or {})
            completed_list = ws.get('completed_scenes') or []
            comp_cnt = len(completed_list) if isinstance(completed_list, list) else 0
            gen_results = action_result.get("generation_results") or self.get_last_round_results()
            entry = {
                'summary': reflection.get('reflection_summary'),
                'metrics': {
                    'planned_calls': rm.get('planned_calls', 0),
                    'act_total': rm.get('act_total', 0),
                    'act_success': rm.get('act_success', 0),
                    'artifacts': rm.get('artifacts', 0),
                    'completed_internal': comp_cnt,
                },
                'scenes_in_round': [r.get('scene_number') for r in (gen_results or []) if isinstance(r, dict)],
            }
            hist.append(entry)
            ws['iteration_history'] = hist
            self.iteration_context['working_state'] = ws
            # 诊断：输出内部完成键集合
            try:
                keys = sorted({
                    int(it.get('scene_number'))
                    for it in (completed_list or [])
                    if isinstance(it, dict) and it.get('scene_number') is not None and str(it.get('scene_number')).isdigit()
                })
                self.logger.info(f"REFLECT_DIAG: completed_internal_keys={keys}")
            except Exception:
                pass
        except Exception:
            pass
        # 分层原则：默认不在中途写入外部 WF，仅在任务完成时统一落地（见 _execute_task_completion）
        return reflection

    # ReActAgent兼容性方法
    async def _think_and_plan(
        self, 
        current_state: Dict[str, Any], 
        task: Task, 
        execution: AgentExecution,
        iteration: int
    ) -> Dict[str, Any]:
        """ReActAgent要求的统一思考和规划方法（兼容性实现）"""
        # 合并式路径：除首轮plan-only外，后续直接在一次FC中完成“滚动规划 + 执行”。
        # 保存最近观察，供 planning_roundN 模板使用
        try:
            self.iteration_context["last_observation"] = current_state
        except Exception:
            pass
        working_state = self.iteration_context.get("working_state", {})
        reasoning = await self._think_and_reason(current_state, working_state)
        if not reasoning.get("action_needed", False):
            return {"action": "complete_task", "parameters": {"final_status": reasoning.get("strategy", "completed")}}
        # 直接使用观察阶段提供的 pending_scenes 作为候选集合，具体选择由 LLM 在 FC 中自主决定
        candidate_scenes = current_state.get("pending_scenes") or []
        if not candidate_scenes:
            return {"action": "complete_task", "parameters": {"final_status": "no_candidates"}}
        ctx = (self.iteration_context.get("working_state", {}) or {}).get("context", {}) or {}
        style_guidance = ctx.get("intelligent_style", {}) or {}
        return {
            "action": "batch_generate_images",
            "parameters": {
                "scenes_batch": candidate_scenes,
                "style_guidance": style_guidance,
                "generation_strategy": "combined_plan_act"
            }
        }

    async def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """在执行前施加统一的幂等护栏：
        - 对识别为“图像生成类”的 act 调用，若该 scene 已有图像产物，则返回 idempotent_skip，避免重复生成。
        - 其他调用不干预。
        不使用具体供应商/动作名判断，依据工具 metadata.capabilities/tags 与 get_action_stage("act") 识别。
        """
        # 收集已完成图像的 scene 标识
        try:
            ws = self.iteration_context.get("working_state", {}) or {}
            completed = ws.get("completed_scenes", []) or []
            completed_ids = set()
            for it in completed:
                if not isinstance(it, dict):
                    continue
                sn = it.get('scene_number')
                if sn is None:
                    continue
                iu = it.get('image_url') or it.get('image_path')
                if iu:
                    try:
                        completed_ids.add(int(sn))
                    except Exception:
                        continue
        except Exception:
            completed_ids = set()

        results: List[Dict[str, Any]] = []
        for idx, call in enumerate(tool_calls or []):
            try:
                fn = call.get("function", {}).get("name")
                raw = call.get("function", {}).get("arguments", {})
                import json as _json
                args = _json.loads(raw) if isinstance(raw, str) else (raw or {})

                # 解析工具/动作（兼容映射与“tool.action”/“tool_action”两种）
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

                # 判断是否为图像生成类 act 调用
                is_image_generation_call = False
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
                    is_generation_tool = ("图像生成" in caps) or ("图像生成" in tags) or ("image" in ''.join(tags).lower())
                    is_image_generation_call = bool(is_generation_tool and ((stage or 'act') == 'act'))
                except Exception:
                    is_image_generation_call = False

                # 幂等：已存在图像产物则跳过
                if is_image_generation_call:
                    sn = args.get("scene_number")
                    try:
                        sn_int = int(sn) if sn is not None else None
                    except Exception:
                        sn_int = None
                    if sn_int is not None and (sn_int in completed_ids):
                        results.append({
                            "tool": fn,
                            "args": args,
                            "success": False,
                            "error": "scene already has image",
                            "error_type": "idempotent_skip",
                            "result": {
                                "scene_number": sn_int
                            }
                        })
                        continue

                # 正常执行单条
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
