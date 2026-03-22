"""
Base agent class for all video generation agents
"""
import asyncio
import os
import time
import logging
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable, Tuple
import re
from sqlalchemy.orm import Session

from ..models import Task, AgentType, AgentStatus
from ..core.config import settings
from ..events import EventKind
from ..events.publisher import publish_state_event
from ..events.execution import ExecutionState, execution_context_var
from ..events.utils.progress import send_progress_event, update_progress

from .tools.tool_registry import get_tool_registry
from .tools.manager import get_tool_manager
from .tools.agent_tool_allocation import get_agent_tools, validate_agent_tools
from .prompts.template_manager import get_template_manager
from .utils.tool_contracts import extract_contract_slot_writes
from .utils.obs_builder import derive_action_facts
from .utils.memref import walk_memref
from ..services.memory_provider import MemoryServices
from .memory.short_term import (
    MemoryNotInitializedError,
    WorkingMemoryService,
)
from .utils.memory_helpers import agent_scope



class AgentError(Exception):
    """Base exception for agent errors"""
    pass


class AgentTimeoutError(AgentError):
    """Raised when agent execution times out"""
    pass




class BaseAgent(ABC):
    """Base class for all agents in the video generation workflow"""

    def __init__(
        self,
        agent_type: AgentType,
        agent_name: str,
        timeout_seconds: int = 300,
        max_retries: int = 3,
        tools: List[str] = None,
        prompt_templates: List[str] = None,
        llms: Dict[str, Any] = None,
        memory_services: Optional[MemoryServices] = None,
    ):
        self.agent_type = agent_type
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.logger = logging.getLogger(f"agent.{agent_name}")
        # 事件总线：Agent 只发布事件，监听器负责 WS/持久化/轨迹
        
        # Initialize tool registry/manager
        self.tool_registry = get_tool_registry()
        self.tool_manager = get_tool_manager()
        self._available_tools = {}
        # 迭代相关状态（仅在当前运行周期内使用），所有跨回合事实请写入 WorkingMemory
        # WorkingMemory 引用缓存（非状态，仅为减少服务调用开销）
        self._wm_cache = None
        self.workflow_state_id: Optional[str] = None
        self.task_id: Optional[str] = None
        self._task_db_id: Optional[int] = None
        self._max_iterations_hint: int = int(getattr(self, "max_iterations", 0) or 0)
        # 不在 Agent 上保存跨回合状态；仅在同轮内以局部变量传递控制信息
        
        # 工具分配：使用专门的工具列表或手动指定的工具
        if tools is not None:
            # 手动指定工具列表：空列表意味着显式不加载任何工具
            if tools:
                validation = validate_agent_tools(agent_type, tools)
                if not validation["is_valid"]:
                    self.logger.warning(f"Tool validation failed: {validation['recommendations']}")
                    # 使用推荐的工具列表
                    tools = validation["allowed_tools"]
                self._load_tools(tools)
            else:
                self.logger.info(f"🔧 No tools explicitly requested for {agent_name}; FC将以纯文本为主")
        else:
            # 使用Agent类型的专门工具列表
            agent_tools = get_agent_tools(agent_type)
            self._load_tools(agent_tools)
            self.logger.info(f"🔧 Loaded {len(agent_tools)} specialized tools for {agent_type.value}")
            
        self.allocated_tools = list(self._available_tools.keys())
        
        # 记忆管理器 - 🧠 MAS 共享记忆
        if memory_services is None:
            raise AgentError("MemoryServices is required (no global fallback).")
        self._memory_services: MemoryServices = memory_services
        # 长记忆/全局记忆接口（抽象层）
        self._global_memory = memory_services.global_service
        self._long_term_service = memory_services.long_term
        
        # 统一提示词管理器 - 支持YAML配置和模板渲染
        from ..core.prompt_manager import get_prompt_manager
        self.prompt_manager = get_prompt_manager()
        self._prompt_templates = prompt_templates or []
        # 注入的 LLM 实例集合：{default, observe, plan, act}
        self._llms = llms or {}
        
        # FC执行轨迹（仅用于同轮执行轨迹记录，日志/诊断用途，不参与提示注入）
        # 结构：[{"tool": str, "args": dict, "success": bool, "result": Any, "error": str, "ts": float}]
        self._fc_exec_trace: List[Dict[str, Any]] = []
        # 最近一次行为摘要（领域自定义，供 OBS 提示）
        self._last_action_summary: Optional[Dict[str, Any]] = None

        # Agent-specific initialization
        # Inject default thinking mode and token tiers from configuration
        try:
            from ..core.ai_config import get_ai_config
            from ..core.config import settings
            ai_cfg = get_ai_config()
            self.default_thinking_mode = ai_cfg.get_thinking_mode_for_agent(self.agent_name)  # "thinking" | "standard"
            self.max_tokens_standard = settings.LLM_MAX_TOKENS_STANDARD
            self.max_tokens_thinking = settings.LLM_MAX_TOKENS_THINKING
            self.logger.info(
                f"LLM policy for {self.agent_name}: thinking_default={self.default_thinking_mode}, "
                f"tiers={{standard:{self.max_tokens_standard}, thinking:{self.max_tokens_thinking}}}"
            )
        except Exception as e:
            # Fallback defaults if config not available
            self.default_thinking_mode = "standard"
            self.max_tokens_standard = 4096
            self.max_tokens_thinking = 20000
            self.logger.warning(f"Failed to load LLM policy config: {e} (using defaults)")

        self._initialize_agent()

    # --- Iteration control state helpers: removed. Agent保持无状态；仅由 WM 承载事实 ---

    # --- Working Memory helpers（短期记忆服务） ----------------------------

    @property
    def short_term_service(self) -> WorkingMemoryService:
        """Return the injected WorkingMemoryService (fail-fast if not injected)."""
        if not hasattr(self._memory_services, 'short_term') or self._memory_services.short_term is None:
            raise AgentError(
                f"WorkingMemoryService not injected for agent {self.agent_name}. "
                "Ensure MemoryServices includes short_term field."
            )
        return self._memory_services.short_term

    def _cache_iteration_memory(self, wm: Any, workflow_state_id: Optional[str] = None):
        """Cache WorkingMemory handle for quick access (no state beyond reference)."""
        self._wm_cache = wm
        if workflow_state_id:
            self.workflow_state_id = str(workflow_state_id)
        return wm

    @property
    def wm(self):
        """返回当前 workflow/agent 的 WorkingMemory（短期记忆）。要求 orchestrator 预先通过服务创建。"""
        if self._wm_cache is not None:
            return self._wm_cache
        wf_id = self.workflow_state_id
        if not wf_id:
            raise AgentError(
                f"WorkingMemory requested for agent {self.agent_name}, but workflow_state_id is not set."
            )
        scope = agent_scope(wf_id, self.agent_name)
        service = self.short_term_service
        try:
            wm = service.get(str(wf_id), scope)
        except MemoryNotInitializedError as exc:
            raise AgentError(
                f"WorkingMemory not initialised for agent {self.agent_name} (workflow={wf_id}). "
                "Orchestrator must call create_or_get before agent execution."
            ) from exc
        return self._cache_iteration_memory(wm, wf_id)

    # iteration_context 已移除：如需回合内的临时控制信息，请通过局部变量传递

    def memory_write(
        self,
        apply_patch: Callable[[Any], None],
        *,
        expected_version: Optional[int] = None,
        operation: str = "write",
    ) -> None:
        """通过 WorkingMemory 服务应用受控写入（短期记忆）。"""
        wf_id = self.workflow_state_id
        if not wf_id:
            raise AgentError("Cannot write WorkingMemory without workflow_state_id")
        service = self.short_term_service
        service.memory_write(
            workflow_state_id=str(wf_id),
            scope=agent_scope(str(wf_id), self.agent_name),
            apply_patch=apply_patch,
            expected_version=expected_version,
            operation=operation,
        )

    def reset_iteration_memory_cache(self, *, invalidate: bool = False) -> None:
        """清理 WorkingMemory 引用缓存。

        注意：WorkingMemory 的创建/初始化责任在 orchestrator/memory 服务，
        Agent 只应通过 self.wm 访问，不再主动创建或管理生命周期。
        """
        wf_id = self.workflow_state_id
        self._wm_cache = None
        if invalidate and wf_id:
            scope = agent_scope(wf_id, self.agent_name)
            self.short_term_service.reset(scope, wf_id)

    # === 预执行适配层（MemRef 解引用） ===
    def _pre_execute_enrich_args(self, function_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        通用 MemRef 适配层：仅当入参中包含 "$memref" 标记时，基于 WorkingMemory（短期记忆）进行就地替换；
        不做函数名判断，不做默认合并，不覆盖模型已明确给定的普通字段。

        prepared_assets 兼容路径已废弃，source 需显式传入 wm.<key>。
        """
        if not isinstance(args, dict):
            return args

        try:
            return walk_memref(args, self.wm)
        except Exception:
            return args

    def _apply_tool_output_contract(
        self,
        *,
        tool_obj: Any,
        tool_name: Optional[str],
        action_name: Optional[str],
        payload: Dict[str, Any],
        scene_number: Optional[int],
    ) -> None:
        """Write tool outputs to agent-scoped WorkingMemory via tool-declared contracts.

        设计约束：
        - Contract 由工具声明，Agent 侧只做通用适配；不在此处按工具名 if/else 分支。
        - 只写入 Agent-scope WorkingMemory（不写入 MAS/shared 产物槽位）。
        - 写入内容必须可序列化（dict/list/str/number/bool）。

        支持两类 contract：
        1) 推荐：`memory_slots` / `slots`（配合 `extract_contract_slot_writes`）
        2) 兼容：旧的 `writes`（历史遗留，后续可移除）
        """
        if not isinstance(payload, dict):
            return
        if tool_obj is None or not hasattr(tool_obj, "get_output_contract"):
            return

        try:
            contract = tool_obj.get_output_contract(action_name)  # type: ignore[attr-defined]
        except Exception:
            return
        if not isinstance(contract, dict) or not contract:
            return

        # 优先：memory_slots/slots → SlotWrite（统一 contract 入口）
        try:
            slot_writes = extract_contract_slot_writes(payload, contract, default_scene=scene_number)
        except Exception:
            slot_writes = []
        if slot_writes:
            wm = self.wm
            for w in slot_writes:
                if not w.slot or not isinstance(w.slot, str):
                    continue
                if w.scene_number is None:
                    continue
                # slot 作为 WM 顶层键保存（避免把中间准备数据混入 facts）
                try:
                    bucket = wm.get(w.slot, {}) or {}
                    if not isinstance(bucket, dict):
                        bucket = {}
                    bucket[str(int(w.scene_number))] = w.value
                    wm.put(w.slot, bucket)
                except Exception:
                    continue
            return

        # 兼容：旧的 writes 形态
        writes = contract.get("writes")
        if not isinstance(writes, list) or not writes:
            return

        def _get_from_path(obj: Dict[str, Any], path: str) -> Any:
            cur: Any = obj
            for part in (path or "").split("."):
                if not part:
                    continue
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(part)
            return cur

        for w in writes:
            if not isinstance(w, dict):
                continue
            if w.get("scope") != "agent_facts":
                continue
            key = w.get("key")
            mode = w.get("mode")
            from_path = w.get("from")
            if not isinstance(key, str) or not key.strip():
                continue
            if not isinstance(from_path, str) or not from_path.strip():
                continue

            value = _get_from_path(payload, from_path)
            if value is None:
                continue

            if mode == "by_scene":
                if scene_number is None:
                    continue
                try:
                    wm = self.wm
                    facts = wm.get("facts", {}) or {}
                    if not isinstance(facts, dict):
                        facts = {}
                    bucket = facts.get(key, {}) or {}
                    if not isinstance(bucket, dict):
                        bucket = {}
                    bucket[str(int(scene_number))] = value
                    facts[key] = bucket
                    wm.put("facts", facts)
                except Exception:
                    continue
            elif mode == "replace":
                try:
                    wm = self.wm
                    facts = wm.get("facts", {}) or {}
                    if not isinstance(facts, dict):
                        facts = {}
                    facts[key] = value
                    wm.put("facts", facts)
                except Exception:
                    continue
            else:
                continue

    # --- Unified SharedWM artifact writer ---------------------------------
    def write_shared_artifact(
        self,
        *,
        kind: str,
        stage: str,
        payload: Dict[str, Any],
        scene_number: Optional[int] = None,
        tool: Optional[str] = None,
        workflow_state_id: Optional[str] = None,
    ) -> Optional[int]:
        """Write a normalized artifact record to Shared Working Memory.

        This provides a single entry point for agents to register stage outputs
        without duplicating set_fact/register logic across agents.

        Args:
            kind: 'video' | 'image' | 'audio' | 'voice' | 'subtitle' | 'final' | ...
            stage: free-form stage tag, e.g. 'video_only', 'compose', 'voiceover', 'bgm'
            payload: source fields; recognized: file_path/output_path/local_path, video_url/audio_url/image_url/url,
                     duration/duration_sec, prompt_text/prompt, metadata
            scene_number: optional scene id
            tool: optional tool name responsible for the artifact
            workflow_state_id: override task id (defaults to self.workflow_state_id)
        Returns: artifact id (int) if written; otherwise None
        """
        try:
            wf_id = workflow_state_id or self.workflow_state_id
            if not wf_id:
                self.logger.warning(
                    "Artifact write skipped: missing workflow_state_id (kind=%s, stage=%s)",
                    kind,
                    stage,
                )
                return None
            # normalize fields
            fp = (
                (payload.get("file_path") if isinstance(payload, dict) else None)
                or (payload.get("output_path") if isinstance(payload, dict) else None)
                or (payload.get("output_file") if isinstance(payload, dict) else None)
                or (payload.get("local_path") if isinstance(payload, dict) else None)
                or ""
            )
            url = ""
            if isinstance(payload, dict):
                url = payload.get("url") or payload.get("video_url") or payload.get("audio_url") or payload.get("image_url") or ""
            dur = None
            if isinstance(payload, dict):
                dur = payload.get("duration_sec") or payload.get("final_duration") or payload.get("duration") or payload.get("audio_duration") or payload.get("video_duration")
                try:
                    if dur is not None:
                        dur = float(dur)
                except Exception:
                    dur = None
            prompt_text = ""
            if isinstance(payload, dict):
                prompt_text = payload.get("prompt_text") or payload.get("prompt") or ""
            meta = {}
            if isinstance(payload, dict):
                meta = payload.get("metadata") or {}
            rec = {
                "kind": kind,
                "stage": stage,
                "scene_number": scene_number,
                "file_path": fp,
                "url": url,
                "duration_sec": dur,
                "prompt_text": prompt_text,
                "agent": self.agent_name,
                "tool": tool or "",
                "metadata": meta,
            }
            from .utils.memory_helpers import mas_scope

            wm = self.short_term_service.get(str(wf_id), mas_scope(str(wf_id)))
            bucket = wm.get("artifacts", [])
            if not isinstance(bucket, list):
                bucket = []
            bucket.append(rec)
            wm.put("artifacts", bucket)
            return len(bucket)
        except Exception as e:
            self.logger.error("Artifact write failed: %s (kind=%s stage=%s)", e, kind, stage, exc_info=True)
            return None

    @staticmethod
    def _normalize_orchestration_completion_state(value: Any, *, success: bool) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"complete", "completed"}:
            return "completed"
        if raw in {"partial", "blocked", "error", "failed", "max_iter_reached"}:
            return raw
        return "completed" if success else "partial"

    def _build_default_orchestration_report(
        self,
        output_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        success = bool(output_data.get("success", True))
        completed_reason = str(
            output_data.get("completed_reason")
            or output_data.get("loop_end_reason")
            or ""
        ).strip()
        reflection_summary = str(output_data.get("reflection_summary") or "").strip()
        completion_state = self._normalize_orchestration_completion_state(
            output_data.get("subtask_state"),
            success=success,
        )
        reflection: Dict[str, Any] = {
            "completion_state": completion_state,
            "reported_gaps": [completed_reason] if completed_reason and not success else [],
            "reported_hints": [],
        }
        if reflection_summary:
            reflection["summary"] = reflection_summary
        return {
            "status": "completed" if success else "partial",
            "boundary_event": "",
            "gate_triggers": [],
            "artifacts": [],
            "reflection": reflection,
        }

    def _ensure_orchestration_report(self, output_data: Any) -> Any:
        if self.agent_type == AgentType.ORCHESTRATOR or not isinstance(output_data, dict):
            return output_data
        if isinstance(output_data.get("orchestration_report"), dict):
            return output_data
        enriched_output = dict(output_data)
        enriched_output["orchestration_report"] = self._build_default_orchestration_report(
            enriched_output
        )
        return enriched_output
    
    async def execute(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session = None,
        execution_order: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute the agent with the given task and input data
        
        Args:
            task: The task to execute
            input_data: Input data for the agent
            db: Database session
            execution_order: Order of execution in the workflow
            
        Returns:
            Dict containing the agent's output data
        """
        # 每次执行重置 WM 引用缓存，避免跨任务状态污染
        self.reset_iteration_memory_cache()
        workflow_state_id = input_data.get("workflow_state_id")
        if workflow_state_id:
            wf_id_str = str(workflow_state_id)
            self.workflow_state_id = wf_id_str
        else:
            self.workflow_state_id = None
        task_identifier = getattr(task, "task_id", None) or getattr(task, "id", None)
        if task_identifier is not None:
            task_id_str = str(task_identifier)
            self.task_id = task_id_str
        else:
            self.task_id = None
        try:
            self._task_db_id = int(getattr(task, "id", None)) if getattr(task, "id", None) is not None else None
        except Exception:
            self._task_db_id = None

        # Reset FC执行轨迹（避免跨任务泄露）
        try:
            self._fc_exec_trace = []
        except Exception:
            self._fc_exec_trace = []

        # Create execution state (local scope, transient)
        def _to_jsonable(obj):
            # Recursively convert objects to JSON-serializable structures
            from pydantic import BaseModel as _PydanticBaseModel  # type: ignore
            if obj is None:
                return None
            if isinstance(obj, (str, int, float, bool)):
                return obj
            if isinstance(obj, dict):
                return {k: _to_jsonable(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple, set)):
                return [_to_jsonable(v) for v in obj]
            # Pydantic BaseModel (e.g., ToolOutput)
            if isinstance(obj, _PydanticBaseModel):
                try:
                    return _to_jsonable(obj.model_dump())
                except Exception:
                    try:
                        return _to_jsonable(obj.dict())
                    except Exception:
                        return str(obj)
            # Fallback to __dict__ or string
            return getattr(obj, "__dict__", str(obj))

        sanitized_input = _to_jsonable(input_data)
        run_id = f"{self.agent_name}-{int(time.time()*1000)}"
        
        exec_state = ExecutionState(
            id=run_id,
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            execution_order=execution_order,
            input_data=sanitized_input
        )
        
        # 将当前任务挂到实例上，便于进度上报和子类访问
        # 注意：同一实例串行执行多个任务时会被覆盖，这是预期行为
        self._current_task = task
        
        # Set execution context
        token = execution_context_var.set(exec_state)

        try:
            # Start execution (in-memory)
            exec_state.status = "running"
            if self.agent_type == AgentType.ORCHESTRATOR:
                self.logger.info("EXEC_DIAG(orchestrator): before publish_state_event(started)")
            await publish_state_event(
                status="running",
                extra_payload={
                    "input_data": sanitized_input,
                    "timeout_seconds": self.timeout_seconds,
                    "max_retries": self.max_retries,
                },
                task_id=self.task_id,
                task_db_id=self._task_db_id,
                workflow_state_id=self.workflow_state_id,
                agent_type=self.agent_type.value,
                agent_name=self.agent_name,
                execution_order=exec_state.execution_order,
                execution_id=exec_state.id,
            )
            if self.agent_type == AgentType.ORCHESTRATOR:
                self.logger.info("EXEC_DIAG(orchestrator): after publish_state_event(started)")
                self.logger.info("EXEC_DIAG(orchestrator): before send_progress_update(started)")
            await self._send_progress_update("started")
            if self.agent_type == AgentType.ORCHESTRATOR:
                self.logger.info("EXEC_DIAG(orchestrator): after send_progress_update(started)")
            self.logger.info(f"Starting {self.agent_name} for task {task.task_id}")

            # Execute with timeout
            output_data = await asyncio.wait_for(
                self._execute_impl(task, input_data, db),
                timeout=self.timeout_seconds
            )
            output_data = self._ensure_orchestration_report(output_data)
            sanitized_output = _to_jsonable(output_data)

            # Complete execution (in-memory)
            exec_state.finish(status="completed")

            await publish_state_event(
                status="completed",
                extra_payload={
                    "output_data": sanitized_output, 
                    "duration": exec_state.duration,
                    "metrics": {
                        "tokens_used": exec_state.tokens_used,
                        "api_calls": exec_state.api_calls_made
                    }
                },
                task_id=self.task_id,
                task_db_id=self._task_db_id,
                workflow_state_id=self.workflow_state_id,
                agent_type=self.agent_type.value,
                agent_name=self.agent_name,
                execution_order=exec_state.execution_order,
                execution_id=exec_state.id,
            )
            await self._send_progress_update("completed")
            self.logger.info(f"Completed {self.agent_name} for task {task.task_id}")
            return output_data

        except asyncio.TimeoutError:
            error_msg = f"Agent {self.agent_name} timed out after {self.timeout_seconds} seconds"
            exec_state.finish(status="failed", error=error_msg)
            
            await publish_state_event(
                status="failed",
                error=error_msg,
                task_id=self.task_id,
                task_db_id=self._task_db_id,
                workflow_state_id=self.workflow_state_id,
                agent_type=self.agent_type.value,
                agent_name=self.agent_name,
                execution_order=exec_state.execution_order,
                execution_id=exec_state.id,
            )
            await self._send_progress_update("failed")
            self.logger.error(error_msg)
            raise AgentTimeoutError(error_msg)
            
        except Exception as e:
            error_msg = f"Agent {self.agent_name} failed: {str(e)}"
            exec_state.finish(status="failed", error=error_msg)
            
            await publish_state_event(
                status="failed",
                error=error_msg,
                task_id=self.task_id,
                task_db_id=self._task_db_id,
                workflow_state_id=self.workflow_state_id,
                agent_type=self.agent_type.value,
                agent_name=self.agent_name,
                execution_order=exec_state.execution_order,
                execution_id=exec_state.id,
            )
            await self._send_progress_update("failed")
            self.logger.error(error_msg, exc_info=True)
            raise AgentError(error_msg) from e
        finally:
            # Reset execution context
            execution_context_var.reset(token)
            
            # 避免跨任务残留引用
            try:
                del self._current_task
            except Exception:
                pass
            # ExecutionState is local, no need to explicit delete, but good for clarity
            del exec_state

    
    @abstractmethod
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session = None,
    ) -> Dict[str, Any]:
        """
        Internal implementation of agent execution
        
        Args:
            task: The task to execute
            input_data: Input data for the agent
            db: Database session
            
        Returns:
            Dict containing the agent's output data
        """
        pass
    
    async def _send_progress_update(
        self,
        status: str,
    ):
        """发布进度事件（WS 推送等由监听器处理）"""
        exec_state = execution_context_var.get()
        if exec_state:
            await send_progress_event(exec_state, self, status)
        else:
            self.logger.warning("Attempted to send progress update without execution context")
    
    async def _update_progress(
        self,
        percentage: int,
        substep: str = None,
        db: Session = None,
    ):
        """Update execution progress"""
        exec_state = execution_context_var.get()
        if exec_state:
            await update_progress(exec_state, self, percentage, substep)
        else:
            self.logger.warning("Attempted to update progress without execution context")

    # 事件发布通过 events.publisher，Base 不再内置审计逻辑
    
    def _validate_input(self, input_data: Dict[str, Any], required_keys: List[str]):
        """Validate that required input keys are present and non-empty"""
        missing_keys = [key for key in required_keys if key not in input_data]
        if missing_keys:
            raise AgentError(f"Missing required input keys: {missing_keys}")
        
        # 检查关键字段是否为空
        empty_keys = []
        for key in required_keys:
            value = input_data.get(key)
            if key == "user_prompt" and (not value or str(value).strip() == ""):
                empty_keys.append(key)
        
        if empty_keys:
            raise AgentError(f"Required input fields cannot be empty: {empty_keys}. Cannot continue with empty prompt.")
    
    def _get_model_parameters(self) -> Dict[str, Any]:
        """Get model parameters for AI service calls"""
        exec_state = execution_context_var.get()
        if exec_state:
            return exec_state.model_parameters
        return {}

    def _get_execution_id(self) -> Optional[str]:
        """Return current execution id if available."""
        exec_state = execution_context_var.get()
        if exec_state and getattr(exec_state, "id", None):
            return str(exec_state.id)
        return None
    
    def _update_token_usage(self, tokens_used: int):
        """Update token usage for cost tracking (in-memory only)"""
        exec_state = execution_context_var.get()
        if exec_state:
            exec_state.add_token_usage(tokens_used)
        else:
            self.logger.warning("Attempted to update token usage without execution context")
    
    # === Function Call支持 ===
    
    async def llm_function_call(
        self,
        messages: List[Dict[str, Any]],
        context_description: str = "",
        model: str = None,
        temperature: float = 0.2,
        tools_override: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        使用LLM的Function Call能力让AI选择合适的工具和参数
        
        Args:
            messages: 对话消息列表
            context_description: 上下文描述，帮助LLM理解任务
            model: LLM模型名称
            temperature: 生成温度
            
        Returns:
            包含工具调用结果的字典
        """
        try:
            # 构建工具schema（允许调用方在特定回合传入覆盖，例如首轮 plan-only 传空列表）
            if tools_override is not None:
                tools_schema = list(tools_override)
                # 使用统一方法从覆盖schema重建路由映射，并做严格校验
                self._rebuild_fc_map_from_schema(tools_schema, strict=True)
            else:
                tools_schema = self._build_function_call_schema()
            
            if not tools_schema:
                # 无工具可用时，也允许走FC文本路径（tools=[]），由模型直接在content返回
                self.logger.info(f"No tools available for {self.agent_name}; proceeding with text-only FC")
                tools_schema = []
            else:
                # 调试：显示可用的工具函数
                func_names = [t["function"]["name"] for t in tools_schema if t.get("function", {}).get("name")]
                self.logger.info(f"🔧 FC可用函数: {func_names[:3]}{'...' if len(func_names) > 3 else ''} (总数: {len(func_names)})")
            
            # 构建完整消息列表（零侵入：完全透传调用方 messages）
            complete_messages = list(messages or [])

            # 协议约束：当 tools 非空时，不应使用 response_format 强制 JSON。
            # 在部分供应商/模式下，这会抑制 tool_calls 产出，导致 ReAct 空转。
            #
            # 这里不做静默兜底：显式告警并移除 response_format，保证工具规划可用。
            if tools_schema and kwargs.get("response_format") is not None:
                try:
                    self.logger.warning(
                        "llm_function_call: dropping response_format because tools are present (to avoid suppressing tool_calls)"
                    )
                except Exception:
                    pass
                kwargs.pop("response_format", None)
            
            # 注入思维链与token档位（仅在未显式传入时），依据Agent默认策略
            thinking_cfg = kwargs.get("thinking")
            if thinking_cfg is None:
                default_enabled = (self.default_thinking_mode == "thinking")
                kwargs["thinking"] = {"type": "enabled"} if default_enabled else {"type": "disabled"}

            if kwargs.get("max_tokens") is None:
                # 依据最终thinking选择档位
                t_cfg = kwargs.get("thinking")
                t_enabled = False
                if isinstance(t_cfg, dict):
                    t_enabled = (t_cfg.get("type") == "enabled")
                elif isinstance(t_cfg, bool):
                    t_enabled = t_cfg
                kwargs["max_tokens"] = self.max_tokens_thinking if t_enabled else self.max_tokens_standard

            # 调用注入的 LLM（plan/act 优先其后 default）
            # llm_service = self._resolve_llm_for_role('plan')
            llm_service = self.get_llm("plan")

            try:
                llm_response = await llm_service.function_call(
                    messages=complete_messages,
                    tools=tools_schema,
                    tool_choice="auto",
                    model=model,
                    temperature=temperature,
                    **kwargs
                )
            except Exception as e:
                # 当无工具可用且供应商FC失败时，通常降级到普通对话接口，避免上游中断；
                # 但若明显是超时类错误，则直接上抛，让调用方（如ConceptPlanner）执行配置化的备用模型策略。
                if not tools_schema:
                    err_str = str(e).lower()
                    is_timeout_like = (
                        isinstance(e, asyncio.TimeoutError)
                        or "timeout" in err_str
                        or "timed out" in err_str
                        or "request timeout" in err_str
                    )
                    if is_timeout_like:
                        # 交由上层处理（例如根据 ai_config 切换 fallback 模型），避免重复等待同一供应商
                        raise
                    try:
                        self.logger.error(f"Function call failed without tools; falling back to chat_completion: {e}")
                    except Exception:
                        pass
                    # 使用同一服务的 chat_completion 作为降级路径（非超时错误）
                    chat_res = await llm_service.chat_completion(
                        messages=complete_messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=kwargs.get("max_tokens")
                    )
                    # 组装与FC近似的响应结构
                    llm_response = {
                        "content": chat_res.get("content"),
                        "reasoning_content": chat_res.get("reasoning_content"),
                        "model": chat_res.get("model"),
                        "usage": chat_res.get("usage", {}),
                        "finish_reason": chat_res.get("finish_reason"),
                        "provider": chat_res.get("provider"),
                        "has_function_call": False,
                    }
                else:
                    raise
            # 观测：记录finish_reason、tool_calls数量、content长度（中文环境，避免打印长文本）
            try:
                fr = llm_response.get("finish_reason")
                tcs = len(llm_response.get("tool_calls", []) or []) if isinstance(llm_response.get("tool_calls"), list) else 0
                clen = len((llm_response.get("content") or ""))
                model = llm_response.get("model")
                provider = llm_response.get("provider")
                mp = f", model={model}, provider={provider}" if (model or provider) else ""
                self.logger.info(f"FC返回: finish_reason={fr}, tool_calls={tcs}, content_len={clen}{mp}")
            except Exception:
                pass

            # 极简“length截断一次受控重试”：
            # - 仅当 finish_reason=length 且无工具调用且 content 为空时触发
            # - 仅重试一次：放大 max_tokens（x2），封顶按当前思维档位上限（standard/thinking）
            # - 不新增配置项；作为协议层小保险，避免将“被截断”误判为空结果
            # 单轮一次 FC：不做长度放大重试
            
            # 处理Function Call响应（仅返回计划，不执行）
            # 兼容：部分供应商可能返回 tool_calls 但未显式标记 has_function_call
            if llm_response.get("tool_calls"):
                # 调试：打印本轮计划的工具调用名称与参数预览（不执行）
                try:
                    call_summaries = []
                    for tc in llm_response["tool_calls"][:5]:  # 只预览前5个
                        fn = tc.get("function", {}).get("name")
                        raw = tc.get("function", {}).get("arguments")
                        arg_preview = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                        if isinstance(arg_preview, str):
                            # DEBUG 等级下不截断；否则使用配置化的预览长度
                            arg_preview = arg_preview.replace("\n", " ")
                            if not self.logger.isEnabledFor(logging.DEBUG):
                                try:
                                    max_len = int(getattr(settings, 'CONTENT_PREVIEW_CHARS', 300))
                                except Exception:
                                    max_len = 300
                                arg_preview = arg_preview[:max_len]
                        call_summaries.append(f"{fn}({arg_preview})")
                    self.logger.info(f"📝 FC计划: {len(llm_response['tool_calls'])} calls -> " + ", ".join(call_summaries))
                    # 仅日志，不写入 Agent/上下文状态
                except Exception:
                    pass
                return {
                    "success": True,
                    "approach": "function_call_plan",
                    "tool_calls": llm_response["tool_calls"],
                    "llm_response": llm_response
                }
            
            else:
                # 无tool_calls路径：可能直接给出文本，也可能空（需重试/兜底）
                content = (llm_response.get("content") or "").strip()
                if content:
                    # 仅返回确定性摘要，不驱动任何外部执行
                    content_preview = re.sub(r"\s+", " ", content).strip()[: settings.CONTENT_PREVIEW_CHARS]
                    meta = {
                        "finish_reason": llm_response.get("finish_reason"),
                        "content_len": len(content),
                        "content_preview": content_preview,
                    }
                    return {
                        "success": True,
                        "approach": "text_response",
                        "content": content,
                        "meta": meta,
                        "llm_response": llm_response,
                    }
                # 不再在Base层追加二次提示或注入系统信息，直接返回空文本结果
                return {
                    "success": True,
                    "approach": "text_response",
                    "content": "",
                    "meta": {"finish_reason": llm_response.get("finish_reason"), "content_len": 0, "content_preview": ""},
                    "llm_response": llm_response,
                }
        
        except Exception as e:
            # 统一记录一次错误
            try:
                self.logger.error(f"Function call failed: {e}")
            except Exception:
                pass
            # 文本FC（tools=[]）且为“超时类错误”时，上抛给调用方以执行配置化的备用模型策略
            try:
                err_str = str(e).lower()
                is_timeout_like = (
                    isinstance(e, asyncio.TimeoutError)
                    or "timeout" in err_str
                    or "timed out" in err_str
                    or "request timeout" in err_str
                )
                if is_timeout_like:
                    # 若前面构建了 tools_schema 且为空，认为是 text-only FC
                    try:
                        if not tools_schema:
                            raise
                    except NameError:
                        # 未定义 tools_schema 时，不影响默认返回
                        pass
            except Exception:
                # 继续按默认失败返回
                pass
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_function_call_schema(self) -> List[Dict[str, Any]]:
        """
        通过 ToolManager 基于分配与策略构建给 LLM 的函数调用 Schema。
        不在 Agent 运行时手动拼接；由 ToolManager 决定暴露动作集合与 schema，
        此处仅重建一次本地路由作为防御。
        """
        try:
            plan = self.tool_manager.allocate(
                agent_type=self.agent_type,
                requested=self.allocated_tools,
                agent_name=self.agent_name,
            )
            tools_schema = self.tool_manager.build_fc_schema(plan.tools, plan.exposure)
            try:
                self._rebuild_fc_map_from_schema(tools_schema, strict=False)
            except Exception as _e:
                self.logger.debug(f"FC map rebuild (non-strict) skipped: {_e}")
            if not tools_schema:
                self.logger.info("No function-callable tools/actions available for this agent.")
            return tools_schema
        except Exception as e:
            self.logger.warning(f"ToolManager schema build failed: {e}")
            return []

    def _rebuild_fc_map_from_schema(self, tools_schema: List[Dict[str, Any]], strict: bool = False) -> None:
        """
        根据给 LLM 的函数 schema 重建 `_fc_function_map`，保持“规划与执行”一致。
        - 仅解析函数名（tool.action），不引入具体工具实现；通过工具公开的 actions 做存在性校验。
        - strict=True 时，若发现未分配工具或不存在的动作，抛出 AgentError 以便快速诊断。
        """
        self._fc_function_map = {}
        invalids: List[str] = []
        for t in (tools_schema or []):
            try:
                fn = (t or {}).get("function", {}).get("name")
                if not fn or not isinstance(fn, str):
                    continue
                tool_name, action = (fn.split(".", 1) + [None])[:2] if "." in fn else (fn, None)
                # 仅为当前Agent已加载的工具建立映射
                if tool_name not in getattr(self, "_available_tools", {}):
                    invalids.append(f"{fn} (tool not allocated)")
                    continue
                # 若声明了动作，则校验其在工具 actions 列表中
                if action:
                    tool_obj = self._available_tools.get(tool_name)
                    try:
                        actions = tool_obj.get_available_actions() or []
                    except Exception:
                        actions = []
                    if action not in actions:
                        invalids.append(f"{fn} (action not available)")
                        continue
                # 注册映射
                self._fc_function_map[fn] = (tool_name, action)
            except Exception:
                continue
        if strict and invalids:
            raise AgentError(f"Invalid tools_override entries: {', '.join(invalids)}")


    def _load_llms_from_policy(self) -> Dict[str, Any]:
        """
        Lazily construct LLM role handles from the shared llm_policies.yaml config
        when explicit injections are not provided. This keeps agents supplier-agnostic
        and ensures CLI/tests can bootstrap without the orchestrator wiring.
        """
        from pathlib import Path
        try:
            from .utils.llm_policy import LLMPolicyManager
        except Exception as exc:
            raise AgentError(
                f"Unable to import LLMPolicyManager for agent {self.agent_name}: {exc}"
            ) from exc

        policy_path = Path(__file__).resolve().parents[1] / "config" / "llm_policies.yaml"
        if not policy_path.exists():
            raise AgentError(
                f"LLM policy file not found for agent {self.agent_name}: {policy_path}"
            )

        try:
            policy_manager = LLMPolicyManager(str(policy_path))
            llm_handles = policy_manager.build_llms_for_agent(self.agent_name)
        except Exception as exc:
            raise AgentError(
                f"Failed to load LLM policy for agent {self.agent_name}: {exc}"
            ) from exc

        if not llm_handles:
            raise AgentError(
                f"No LLM handles configured for agent {self.agent_name} in {policy_path}"
            )

        try:
            self.logger.info(
                "LLM handles auto-loaded for %s using policy %s",
                self.agent_name,
                policy_path,
            )
        except Exception as e:
            raise AgentError(
                f"Failed to log LLM policy load for agent {self.agent_name},err happend: {e} "
            )

        return llm_handles

    # === LLM依赖注入访问器 ===
    def _resolve_llm_for_role(self, role: str):
        """根据角色解析注入的 LLM 句柄，支持按角色区分 plan/act/default 等。
        若指定角色未注入，则回退到 default 角色。
        若均未注入，则抛出异常。
        """
        try:
            self.logger.debug("LLM_RESOLVE agent=%s role=%s handles=%s", self.agent_name, role, list(self._llms.keys()))
        except Exception:
            pass
        if role in self._llms and self._llms[role] is not None:
            return self._llms[role]
        if 'default' in self._llms and self._llms['default'] is not None:
            return self._llms['default']
        raise AgentError(f"LLM not injected for agent {self.agent_name} (role={role})")

    def get_llm(self, role: str = None):
        """Public accessor for injected llm handles."""
        r = role or 'default'
        self.logger.debug("LLM_GET agent=%s role=%s self._llms=%s", self.agent_name, r, list(self._llms.keys()) if self._llms else None)
        if (not self._llms) or all(handle is None for handle in self._llms.values()):
            self.logger.debug("LLM_GET entered lazy load for agent=%s", self.agent_name)
            self._llms = self._load_llms_from_policy()
        return self._resolve_llm_for_role(r)
    
    async def _execute_function_call(self, function_name: str, function_args: Dict[str, Any]) -> Any:
        """执行LLM选择的工具调用"""
        # 优先使用扁平映射进行稳定路由
        if hasattr(self, "_fc_function_map") and function_name in getattr(self, "_fc_function_map", {}):
            tool_name, action = self._fc_function_map[function_name]
            return await self.use_tool(tool_name, action, function_args)

        # 兼容旧格式：解析“tool_action”风格名称
        parts = function_name.split("_")
        if len(parts) >= 2:
            for i in range(1, len(parts)):
                tool_name = "_".join(parts[:i])
                action = "_".join(parts[i:])
                if tool_name in self.allocated_tools:
                    return await self.use_tool(tool_name, action, function_args)

        # 找不到匹配，给出明确错误
        raise ValueError(
            f"No matching tool for function '{function_name}'. Registered: {list(getattr(self, '_fc_function_map', {}).keys())}"
        )

    async def execute_tool_calls(self, tool_calls: List[Dict[str, Any]], *, collect_facts: bool = False):
        """统一执行一组 tool_calls（与 FC 返回格式兼容）。
        每条元素期望形如 {"function": {"name": str, "arguments": str|dict}}。
        返回：
          - collect_facts=False（默认）：标准结果列表 [{tool, args, result?, success, error?, error_type?}]
          - collect_facts=True：{"executed_calls": [...], "act_summary": {...}, "react_metrics": {...}, "act_log": [...]}（不落入Agent字段）
        """
        try:
            self.logger.info("🤖 选择工具：开始执行规划的工具调用")
        except Exception:
            pass
        results: List[Dict[str, Any]] = []
        actions_this_round: List[Dict[str, Any]] = []
        funcs_used: List[str] = []
        # 本轮规范化结果快照（通用字段，供应商无关）
        last_round_results: List[Dict[str, Any]] = []
        # 本轮度量（不改变行为，仅可观测）
        round_metrics = {
            'total': 0,
            'success': 0,
            'fail': 0,
            'artifacts': 0,
        }
        # 轻量预验证（不改写）
        try:
            fc_schema = self._build_function_call_schema()
            report = self.tool_manager.validate_tool_calls(tool_calls or [], fc_schema or [])
            if report and report.issues:
                for iss in report.issues:
                    self.logger.warning(
                        f"FC validation: idx={iss.call_index} level={iss.level} reason={iss.reason} hint={iss.hint}"
                    )
        except Exception as _ve:
            self.logger.debug(f"FC validation skipped: {_ve}")

        # 构造参数策略上下文
        def _policy_context() -> Dict[str, Any]:
            ctx: Dict[str, Any] = {
                'agent_name': self.agent_name,
                'agent_type': self.agent_type.value,
            }
            # 推断 wf_id：优先 AgentState.context.workflow_state_id
            try:
                if self.workflow_state_id:
                    ctx['wf_id'] = str(self.workflow_state_id)
            except Exception:
                pass
            # 执行ID来自当前执行上下文
            try:
                exec_state = execution_context_var.get()
                if exec_state and exec_state.id:
                    ctx['execution.id'] = exec_state.id
            except Exception:
                pass
            return ctx

        policy_ctx = _policy_context()

        for idx, tool_call in enumerate(tool_calls):
            try:
                fn = tool_call["function"]["name"]
                funcs_used.append(fn)
                raw_args = tool_call["function"].get("arguments", {})
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                # 应用参数策略：仅在缺参+存在模板时补全；越权/缺 required 直接报错
                try:
                    if isinstance(args, dict):
                        args = self.tool_manager.apply_param_policy(fn, args, policy_ctx)
                except Exception as pe:
                    raise ValueError(f"param policy rejected: {pe}")

                # 预执行解析：基于迭代记忆解引用准备资产，补齐业务入参（不覆盖已有字段）
                try:
                    if isinstance(args, dict):
                        args = self._pre_execute_enrich_args(fn, args)
                except Exception:
                    pass

                # 解析 tool 与 action（优先映射，其次点分隔用于日志展示）
                tool_name, action_name = None, None
                try:
                    if hasattr(self, "_fc_function_map") and fn in getattr(self, "_fc_function_map", {}):
                        tool_name, action_name = self._fc_function_map[fn]
                    elif "." in fn:
                        tool_name, action_name = fn.split(".", 1)
                    else:
                        tool_name, action_name = fn, None
                except Exception:
                    tool_name, action_name = fn, None

                tool_obj = None
                try:
                    if tool_name and tool_name in self._available_tools:
                        tool_obj = self._available_tools[tool_name]
                except Exception:
                    tool_obj = None

                scene = args.get("scene_number") if isinstance(args, dict) else None
                try:
                    args_preview = raw_args if isinstance(raw_args, str) else json.dumps(args, ensure_ascii=False)
                    if isinstance(args_preview, str):
                        # DEBUG 等级下不截断；否则使用配置化的预览长度
                        args_preview = args_preview.replace("\n", " ")
                        if not self.logger.isEnabledFor(logging.DEBUG):
                            try:
                                max_len = int(getattr(settings, 'CONTENT_PREVIEW_CHARS', 300))
                            except Exception:
                                max_len = 300
                            args_preview = args_preview[:max_len]
                except Exception:
                    args_preview = "{}"

                # 快速前置校验：函数是否已暴露/可执行（避免进入执行期才报错）
                try:
                    if fn not in getattr(self, "_fc_function_map", {}):
                        # 允许以“tool.action”形式直达（不做下划线拆分以保持中立）
                        if "." in fn:
                            _tn, _an = fn.split(".", 1)
                            valid_tool = _tn in self._available_tools
                            valid_action = False
                            if valid_tool:
                                try:
                                    valid_action = _an in (self._available_tools[_tn].get_available_actions() or [])
                                except Exception:
                                    valid_action = False
                            if not (valid_tool and valid_action):
                                results.append({
                                    "tool": fn,
                                    "args": args,
                                    "success": False,
                                    "error": "function not exposed or action unavailable",
                                    "error_type": "invalid_tool_call",
                                })
                                # 记录到度量
                                round_metrics['total'] += 1
                                round_metrics['fail'] += 1
                                continue
                        else:
                            # 既非映射也非 tool.action，直接判定为无效
                            results.append({
                                "tool": fn,
                                "args": args,
                                "success": False,
                                "error": "unknown function format (expected tool.action)",
                                "error_type": "invalid_tool_call",
                            })
                            round_metrics['total'] += 1
                            round_metrics['fail'] += 1
                            continue
                except Exception:
                    # 校验失败不阻断，交给执行期处理
                    pass

                # 去阶段化：不再读取/使用 plan/act 阶段语义

                call_id = f"{int(time.time()*1000)}-{idx}"
                try:
                    self.logger.info(
                        f"TOOL_START call_id={call_id} fn={fn} tool={tool_name} action={action_name} scene={scene} args={args_preview}"
                    )
                except Exception:
                    pass

                _call_ts = time.time()
                tool_result = await self._execute_function_call(fn, args)
                payload = tool_result.result if hasattr(tool_result, 'result') else tool_result
                _dur = time.time() - _call_ts
                # 兼容 ToolOutput / dict
                is_success = True
                error_text = None
                error_type = None
                if hasattr(tool_result, 'success'):
                    is_success = bool(getattr(tool_result, 'success'))
                    if not is_success:
                        error_text = getattr(tool_result, 'error', None)
                        meta = getattr(tool_result, 'metadata', {}) or {}
                        error_type = meta.get('error_type')
                # 分段度量统计
                round_metrics['total'] += 1
                # 阶段（已在执行前判定），此处沿用
                scene_number = None
                try:
                    if isinstance(args, dict) and args.get("scene_number") is not None:
                        scene_number = int(args.get("scene_number")) if str(args.get("scene_number")).isdigit() else args.get("scene_number")
                except Exception:
                    scene_number = args.get("scene_number") if isinstance(args, dict) else None

                record = {"tool": fn, "args": args, "success": is_success, "scene_number": scene_number}
                meta_payload = {}
                if hasattr(tool_result, 'metadata'):
                    try:
                        meta_payload = dict(getattr(tool_result, 'metadata') or {})
                    except Exception:
                        meta_payload = {}
                if meta_payload:
                    record["metadata"] = meta_payload
                if is_success:
                    record["result"] = tool_result
                    results.append(record)
                    round_metrics['success'] += 1
                else:
                    record["error"] = error_text or "tool execution failed"
                    record["error_type"] = error_type
                    if meta_payload:
                        # 兼容上层读取结构化错误详情
                        if "error_details_struct" in meta_payload:
                            record["error_details"] = meta_payload.get("error_details_struct")
                        elif "error_details" in meta_payload:
                            record["error_details"] = meta_payload.get("error_details")
                    results.append(record)
                    round_metrics['fail'] += 1
                # 写入FC执行轨迹（用于后续FC上下文注入）
                try:
                    from time import time as _now
                    trace_item = {
                        "tool": fn,
                        "args": args,
                        "success": is_success,
                        "result": tool_result if is_success else None,
                        "error": error_text,
                        "error_type": error_type,
                        "ts": _now(),
                    }
                    self._fc_exec_trace.append(trace_item)
                except Exception:
                    pass
                # 结束日志 + 可选自动持久化产物
                try:
                    artifact = None
                    payload = tool_result.result if hasattr(tool_result, 'result') else tool_result
                    if isinstance(payload, dict):
                        # 优先使用本地持久化路径作为“产物”可观测标识（不在此处做自动持久化，以免偏离 FC 规划）
                        artifact = payload.get('file_path') or payload.get('image_url') or payload.get('video_url') or payload.get('audio_url')
                        if payload.get('file_path') or artifact:
                            round_metrics['artifacts'] += 1
                    # 规范化结果快照（供应商无关字段）
                    try:
                        snap = self.tool_manager.normalize_artifact(tool_result, args if isinstance(args, dict) else {})
                        # 附加执行期信息（非供应商字段）
                        if isinstance(snap, dict):
                            snap.setdefault('success', is_success)
                            snap.setdefault('duration_sec', round(_dur, 2))
                            # 简易度量：若存在任何可用产物指示，计入 artifacts
                            if snap.get('file_path') or snap.get('image_url') or snap.get('video_url') or snap.get('audio_url'):
                                round_metrics['artifacts'] += 1
                            last_round_results.append(snap)
                    except Exception as ne:
                        self.logger.debug(f"artifact normalization skipped: {ne}")
                    self.logger.info(
                        f"TOOL_END call_id={call_id} fn={fn} tool={tool_name} action={action_name} scene={scene} success={is_success} dur={_dur:.2f}s"
                        + (f" artifact={artifact}" if artifact else "")
                        + (f" error={error_text}" if (not is_success and error_text) else "")
                    )
                except Exception:
                    pass

                # === 执行摘要（中立），用于下一轮 OBS 的可消费事实 ===
                try:
                    # 2) 基本布尔信号
                    def _has_any_artifact(p: Any) -> bool:
                        if not isinstance(p, dict):
                            return False
                        return bool(p.get('file_path') or p.get('image_url') or p.get('video_url') or p.get('audio_url'))
                    def _has_text(p: Any) -> bool:
                        if not isinstance(p, dict):
                            return False
                        for k in ('prompt_text', 'text', 'description', 'content'):
                            v = p.get(k)
                            if isinstance(v, str) and v.strip():
                                return True
                        return False
                    has_artifact = _has_any_artifact(payload)
                    text_present = _has_text(payload)
                    # 3) 负载顶层键（白名单交集，不暴露内容）
                    payload_keys: List[str] = []
                    if isinstance(payload, dict):
                        _whitelist = {
                            'assets', 'style', 'characters', 'environment', 'continuity',
                            'scene_references', 'motion_guidance', 'diagnostics'
                        }
                        payload_keys = [k for k in payload.keys() if k in _whitelist]
                    # 4) scene 编号（已在上面解析为 scene 变量）
                    scene_out = None
                    try:
                        scene_out = int(scene) if scene is not None else None
                    except Exception:
                        scene_out = scene
                    # 5) tokens/时长（可选）
                    tks = None
                    try:
                        tks = getattr(tool_result, 'tokens_used') if hasattr(tool_result, 'tokens_used') else None
                    except Exception:
                        tks = None
                    # 6) 错误信息（限长）
                    err_out = None
                    if not is_success and error_text:
                        try:
                            err_out = (error_text or '')
                            max_len = 200
                            if isinstance(err_out, str) and len(err_out) > max_len:
                                err_out = err_out[:max_len]
                        except Exception:
                            err_out = None
                    actions_this_round.append({
                        'tool': fn,
                        'scene_number': scene_out,
                        'success': bool(is_success),
                        'has_artifact': bool(has_artifact),
                        'text_present': bool(text_present),
                        'payload_keys': payload_keys,
                        'error_type': error_type if (not is_success) else None,
                        'error': err_out,
                        'duration_sec': round(_dur, 2) if isinstance(_dur, (int, float)) else None,
                        'tokens_used': int(tks) if isinstance(tks, (int, float)) else None,
                    })
                except Exception:
                    # 摘要生成不应影响主流程
                    pass

                if is_success and isinstance(payload, dict):
                    try:
                        self._apply_tool_output_contract(
                            tool_obj=tool_obj,
                            tool_name=tool_name,
                            action_name=action_name,
                            payload=payload,
                            scene_number=scene_out,
                        )
                    except Exception:
                        pass

            except Exception as e:
                try:
                    _dur = time.time() - _call_ts if '_call_ts' in locals() else 0.0
                    self.logger.error(
                        f"TOOL_END call_id={call_id} fn={fn} tool={tool_name} action={action_name} scene={scene} success=false dur={_dur:.2f}s error={str(e)}"
                    )
                except Exception:
                    self.logger.error(f"Tool execution failed: {e}")
                results.append({"tool": tool_call.get("function", {}).get("name"), "args": tool_call.get("function", {}).get("arguments"), "error": str(e), "success": False})
        # 写入 WorkingMemory 的最近产物索引（如可用），以便跨回合/跨Agent消费
        try:
            wm = self.wm
            if wm is not None:
                snaps = list(last_round_results or [])
                for snap in snaps:
                    if not isinstance(snap, dict):
                        continue
                    # 推断 kind
                    kind = None
                    fp = (snap.get('file_path') or '').lower()
                    def _has_ext(p: str, exts: list[str]):
                        return any(p.endswith(ext) for ext in exts)
                    if snap.get('video_url') or _has_ext(fp, ['.mp4', '.mov', '.mkv']):
                        kind = 'video'
                    elif snap.get('audio_url') or _has_ext(fp, ['.wav', '.mp3', '.aac', '.m4a', '.flac']):
                        kind = 'audio'
                    elif snap.get('image_url') or _has_ext(fp, ['.jpg', '.jpeg', '.png', '.webp']):
                        kind = 'image'
                    if not kind:
                        continue
                    scene_num = None
                    try:
                        if snap.get('scene_number') is not None:
                            scene_num = int(snap.get('scene_number'))
                    except Exception:
                        scene_num = snap.get('scene_number')
                    url = snap.get('video_url') or snap.get('audio_url') or snap.get('image_url') or ''
                    wm.add_iteration_artifact(
                        kind=kind,
                        scene_number=scene_num,
                        file_path=snap.get('file_path') or '',
                        url=url,
                        duration=snap.get('duration_sec'),
                        prompt_text=snap.get('prompt_text') or '',
                        stage=snap.get('stage'),
                    )
        except Exception:
            pass

        if collect_facts:
            try:
                act_summary, metrics, act_log = derive_action_facts(
                    planned_calls=tool_calls,
                    executed_calls=results,
                    round_metrics=round_metrics,
                    actions=actions_this_round,
                )
            except Exception:
                act_summary, metrics, act_log = {}, {}, []
            return {
                "executed_calls": results,
                "act_summary": act_summary,
                "react_metrics": metrics,
                "act_log": act_log,
            }
        return results
    
    def get_tool_names(self) -> List[str]:
        """获取当前Agent加载的工具名称列表"""
        return list(self._available_tools.keys())
    
    def get_tool_capabilities_summary(self) -> str:
        """获取工具能力摘要，供LLM理解"""
        capabilities = []
        
        for tool_name in self.allocated_tools:
            tool = self._available_tools.get(tool_name)
            if tool:
                metadata = tool.get_metadata()
                actions = tool.get_available_actions()
                capabilities.append(f"- {tool_name}: {metadata.description} (actions: {', '.join(actions)})")
        
        return "\n".join(capabilities) if capabilities else "No tools available"
    
    # 迭代摘要不在 Agent 内缓存；由调用方在同轮内通过局部变量传递

    # --- No-op action summary accessors (stateless) -------------------------
    def set_last_action_summary(self, summary: Optional[Dict[str, Any]]) -> None:
        """Compatibility stub: do not persist per-agent state."""
        try:
            if isinstance(summary, dict):
                # 审计日志用途（不写入 Agent 状态）
                self.logger.info("ACT_SUMMARY %s", json.dumps(summary, ensure_ascii=False))
        except Exception:
            pass

    def get_last_action_summary(self) -> Optional[Dict[str, Any]]:
        """Compatibility stub: always return None to keep agent stateless."""
        return None
    
    
    def get_system_instructions(self) -> Dict[str, Any]:
        """获取Agent的系统指令"""
        return self.prompt_manager.get_system_instruction(self.agent_name)
    
    async def _handle_retry(
        self,
        task: Task,
        error: Exception,
        db: Session = None
    ) -> bool:
        """Handle retry logic for failed executions (default: no retry)."""
        return False
    
    def _initialize_agent(self):
        """Agent-specific initialization - override in subclasses"""
        pass
    
    def _load_tools(self, tool_names: List[str]):
        """Load specified tools from registry"""
        load_errors: List[str] = []
        schema_warnings: List[str] = []
        for tool_name in tool_names:
            try:
                tool = self.tool_registry.get_tool(tool_name)
                self._available_tools[tool_name] = tool
                # 轻量校验：至少存在一个可用的action schema
                try:
                    actions = tool.get_available_actions() or []
                    has_schema = False
                    for act in actions:
                        sch = tool.get_action_schema(act) or {}
                        if isinstance(sch, dict) and sch:
                            has_schema = True
                            break
                    if not has_schema:
                        schema_warnings.append(tool_name)
                except Exception as se:
                    schema_warnings.append(f"{tool_name} (schema error: {se}")
                self.logger.info(f"Loaded tool: {tool_name}")
            except Exception as e:
                err = f"{tool_name}: {e}"
                self.logger.error(f"Failed to load tool {err}")
                load_errors.append(err)

        # Fail fast: 任何分配但未成功加载的工具直接报错，保障可验证性
        if load_errors:
            raise AgentError(
                f"Tool allocation failed for {self.agent_name}: {', '.join(load_errors)}"
            )
        # 非致命：若工具缺少可用schema，记录警告，FC时将无法暴露该工具动作
        if schema_warnings:
            self.logger.warning(
                f"Tools missing valid action schema (will not be exposed to FC): {', '.join(schema_warnings)}"
            )
    
    async def use_tool(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any],
        timeout: int = None
    ) -> Any:
        """Use a tool (stateless execution)"""
        if tool_name not in self._available_tools:
            raise AgentError(f"Tool {tool_name} not available for agent {self.agent_name}")
        
        tool = self._available_tools[tool_name]
        
        try:
            # Execute tool
            from .tools.base_tool import ToolInput
            # 构造统一的工具上下文，支持子类按需扩展
            context = self._build_tool_context(tool_name=tool_name, action=action, parameters=parameters)
            # action 允许为 None（无动作工具），约定下发 "__call__" 作为工具级调用占位符
            tool_input = ToolInput(action=(action if action is not None else "__call__"), parameters=parameters, context=context, timeout=timeout)
            result = await tool.execute(tool_input)

            # Log based on success
            try:
                if hasattr(result, 'success') and not result.success:
                    self.logger.warning(
                        f"🔧 Tool {tool_name}:{action} returned failure: {getattr(result, 'error', 'unknown error')}"
                    )
                else:
                    self.logger.info(f"🔧 Tool {tool_name}:{action} executed successfully")
            except Exception:
                # Fallback log if structure unexpected
                self.logger.info(f"🔧 Tool {tool_name}:{action} executed (log parsing skipped)")

            return result

        except Exception as e:
            self.logger.error(f"Tool execution failed for {tool_name}.{action}: {e}")
            raise AgentError(f"Tool execution failed: {str(e)}")
    

    def _build_tool_context(self, tool_name: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """构建工具执行上下文（子类可覆盖扩展）。"""
        ctx = {
            "agent_tool_timeout": None,
            "agent_timeout_seconds": self.timeout_seconds,
        }
        wf_id = self.workflow_state_id
        if wf_id is None:
            raise AgentError(
                f"workflow_state_id missing in context for tool={tool_name}.{action}"
            )
        ctx["workflow_state_id"] = str(wf_id)
        return ctx

    # 🚀 Phase 1.3 - 工具系统解耦：统一AI服务接口
    async def generate_text(
        self,
        prompt: str,
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        response_format: Dict[str, Any] = None,
        tool_name: str = "text_generation_tool"
    ) -> Dict[str, Any]:
        """
        统一的文本生成接口 - 通过工具系统调用AI服务
        替代直接使用AIClient的调用方式
        """
        parameters = {
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format
        }
        # 移除None值
        parameters = {k: v for k, v in parameters.items() if v is not None}
        
        result = await self.use_tool(tool_name, "generate_text", parameters)
        if result.success:
            return result.result
        raise AgentError(f"文本生成失败: {result.error}")
    
    # 直连AI回退已禁用：一切文本生成需通过工具/服务接口执行
    
    def register_default_tools(self):
        """注册默认工具集"""
        default_tools = [
            "text_generation_tool",
            "ai_service_tool"
        ]
        
        for tool_name in default_tools:
            if tool_name not in self._available_tools:
                try:
                    tool = self.tool_registry.get_tool(tool_name)
                    self._available_tools[tool_name] = tool
                    self.logger.info(f"🔧 已注册默认工具: {tool_name}")
                except Exception as e:
                    self.logger.warning(f"⚠️ 默认工具注册失败 {tool_name}: {e}")
    
    async def ensure_ai_tools_available(self):
        """确保AI工具可用"""
        ai_tools = ["text_generation_tool", "ai_service_tool"]
        
        for tool_name in ai_tools:
            if tool_name not in self._available_tools:
                self.register_default_tools()
                break
    
    def render_prompt(
        self, 
        template_name: str, 
        **variables
    ) -> str:
        """
        渲染Agent专用提示词模板 - 使用新的统一提示词管理系统
        
        Args:
            template_name: 模板名称
            **variables: 模板变量
            
        Returns:
            渲染后的提示词文本
        """
        try:
            return self.prompt_manager.render_template(
                config_name=self.agent_name,
                template_name=template_name,
                variables=variables,
                auto_reload=False  # 生产环境关闭自动重载
            )
        except Exception as e:
            self.logger.error(f"Prompt rendering failed for {template_name}: {e}")
            raise AgentError(f"Prompt rendering failed: {str(e)}")
    
    async def store_memory(
        self,
        content: Any,
        tags: List[str] = None,
        importance: str = "medium",
        metadata: Dict[str, Any] = None
    ) -> str:
        """Store information in agent memory"""
        from .memory.long_term.stores import MemoryImportance, MemoryType
        
        importance_map = {
            "minimal": MemoryImportance.MINIMAL,
            "low": MemoryImportance.LOW,
            "medium": MemoryImportance.MEDIUM,
            "high": MemoryImportance.HIGH,
            "critical": MemoryImportance.CRITICAL
        }
        
        if self._long_term_service is None:
            return "memory_disabled"
        
        memory_id = await self._long_term_service.store_memory(
            content=content,
            memory_type=MemoryType.SHORT_TERM,
            importance=importance_map.get(importance, MemoryImportance.MEDIUM),
            tags=tags or [],
            agent_id=self.agent_name,
            metadata=metadata or {}
        )
        
        return memory_id
    
    async def retrieve_memories(
        self,
        query: str = None,
        tags: List[str] = None,
        limit: int = 10
    ) -> List[Any]:
        """Retrieve relevant memories"""
        if self._long_term_service is None:
            return []
        
        memories = await self._long_term_service.search_memories(
            query=query,
            tags=tags,
            agent_id=self.agent_name,
            limit=limit,
            task_id=self.workflow_state_id,
        )
        
        return [memory.content for memory in memories]
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names"""
        return list(self._available_tools.keys())
    
    def get_tool_capabilities(self, tool_name: str) -> List[str]:
        """Get capabilities of a specific tool"""
        if tool_name not in self._available_tools:
            return []
        
        tool = self._available_tools[tool_name]
        return tool.get_available_actions()
    
    def get_prompt_templates(self) -> List[str]:
        """Get list of available prompt templates"""
        return self._prompt_templates
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics"""
        if self._long_term_service is None:
            return {"status": "disabled"}
        
        return await self._long_term_service.get_memory_stats()
    
    # 🚀 MAS记忆共享机制 - Phase 1.2新增
    async def store_creative_guidance(
        self, 
        workflow_id: str, 
        concept_plan: Dict[str, Any]
    ) -> bool:
        """存储创意指导供其他Agent使用"""
        return await self._global_memory.store_creative_guidance(
            workflow_id, concept_plan, self.agent_name
        )
    
    async def retrieve_creative_guidance(
        self, 
        workflow_id: str, 
        scene_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """检索创意指导信息"""
        return await self._global_memory.retrieve_creative_guidance(
            workflow_id, scene_number, self.agent_name
        )
    
    async def store_scene_references(
        self, 
        workflow_id: str, 
        scene_number: int, 
        scene_references: Dict[str, Any]
    ) -> bool:
        """存储场景参考数据供其他Agent使用"""
        return await self._global_memory.store_scene_references(
            workflow_id, scene_number, scene_references, self.agent_name
        )
    
    async def retrieve_scene_references(
        self, 
        workflow_id: str, 
        scene_number: int
    ) -> Dict[str, Any]:
        """检索场景参考数据"""
        return await self._global_memory.retrieve_scene_references(
            workflow_id, scene_number, self.agent_name
        )
    
    async def _cleanup_resources(self):
        """Cleanup agent resources"""
        try:
            # Cleanup tools
            for tool in self._available_tools.values():
                if hasattr(tool, 'cleanup'):
                    await tool.cleanup()
                    
        except Exception as e:
            self.logger.warning(f"Error during resource cleanup: {e}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._cleanup_resources()
