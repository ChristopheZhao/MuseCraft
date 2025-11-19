"""
Base Tool Class - Foundation for all agent tools
"""

import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Callable
from enum import Enum
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

# Optional settings import (avoid hard dependency during import time)
try:
    from ...core.config import settings  # type: ignore
except Exception:  # pragma: no cover - fallback for lint contexts
    settings = None  # type: ignore


def _get_settings_tool_timeout(tool_name: str) -> Optional[int]:
    """Return settings-level default timeout for a specific tool name, if any."""
    if settings is None:
        return None
    try:
        key = f"{tool_name.upper()}_TIMEOUT"
        value = getattr(settings, key)
        return int(value) if isinstance(value, (int, float)) and value > 0 else None
    except Exception:
        return None


def _resolve_timeout(
    tool_name: str,
    explicit_timeout: Optional[int],
    tool_config: Optional[Dict[str, Any]],
    context: Optional[Dict[str, Any]],
) -> int:
    """Compute timeout with a clear, minimal priority chain."""
    tool_config = tool_config or {}
    context = context or {}

    # 1) Explicit per-call
    if isinstance(explicit_timeout, (int, float)) and explicit_timeout > 0:
        resolved = int(explicit_timeout)
    else:
        # 2) Agent-level tool timeout (from context)
        agent_tool_timeout = context.get("agent_tool_timeout")
        if isinstance(agent_tool_timeout, (int, float)) and agent_tool_timeout > 0:
            resolved = int(agent_tool_timeout)
        else:
            # 3) Tool config default (accept both default_timeout and timeout)
            cfg_timeout = tool_config.get("default_timeout")
            if not (isinstance(cfg_timeout, (int, float)) and cfg_timeout > 0):
                cfg_timeout = tool_config.get("timeout")
            if isinstance(cfg_timeout, (int, float)) and cfg_timeout > 0:
                resolved = int(cfg_timeout)
            else:
                # 4) Settings per-tool
                settings_tool = _get_settings_tool_timeout(tool_name)
                if isinstance(settings_tool, int) and settings_tool > 0:
                    resolved = settings_tool
                else:
                    # 5) Global default
                    default_global = 120
                    if settings is not None:
                        try:
                            default_global = int(getattr(settings, "DEFAULT_TOOL_TIMEOUT", 120))
                        except Exception:
                            default_global = 120
                    resolved = default_global

    # Clamp by overall agent timeout if provided
    agent_timeout_total = context.get("agent_timeout_seconds")
    if isinstance(agent_timeout_total, (int, float)) and agent_timeout_total > 0:
        safety_margin = 2  # avoid hitting agent timeout exactly
        max_allowed = max(1, int(agent_timeout_total) - safety_margin)
        if resolved > max_allowed:
            resolved = max_allowed

    return resolved


class ToolType(Enum):
    """Tool type enumeration"""
    AI_SERVICE = "ai_service"
    MEDIA_PROCESSING = "media_processing"
    FILE_MANAGEMENT = "file_management"
    STORAGE = "storage"  # 添加存储类型
    COMMUNICATION = "communication"
    DATA_PROCESSING = "data_processing"
    UTILITY = "utility"
    ANALYSIS = "analysis"  # 添加分析类型


class ToolStatus(Enum):
    """Tool execution status"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class ToolMetadata:
    """Tool metadata information"""
    name: str
    version: str
    description: str
    tool_type: ToolType
    author: str = "system"
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)


class ToolInput(BaseModel):
    """Base tool input schema"""
    action: str = Field(..., description="Action to perform")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Execution context")
    timeout: Optional[int] = Field(default=None, description="Execution timeout in seconds")


class ToolOutput(BaseModel):
    """Base tool output schema"""
    success: bool = Field(..., description="Whether execution was successful")
    result: Optional[Any] = Field(default=None, description="Execution result")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    execution_time: float = Field(..., description="Execution time in seconds")
    tokens_used: Optional[int] = Field(default=None, description="Tokens used (for AI tools)")
    cost: Optional[float] = Field(default=None, description="Execution cost")


class ToolError(Exception):
    """Base tool error"""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        error_code: str | None = None,
        details: Dict[str, Any] | None = None,
    ):
        self.tool_name = tool_name
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class ToolTimeoutError(ToolError):
    """Tool execution timeout error"""
    pass


class ToolValidationError(ToolError):
    """Tool input validation error"""
    pass


class BaseTool(ABC):
    """
    Base class for all agent tools
    
    Tools encapsulate specific functionality that agents can use
    to perform actions in the world or process information.
    """
    
    def __init__(
        self,
        metadata: ToolMetadata,
        config: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.metadata = metadata
        self.config = config or {}
        self.logger = logger or logging.getLogger(f"tool.{metadata.name}")
        
        # Tool state
        self.status = ToolStatus.IDLE
        self.execution_count = 0
        self.total_execution_time = 0.0
        self.last_execution_time = 0.0
        self.error_count = 0
        
        # Hooks for extensibility
        self._pre_execution_hooks: List[Callable] = []
        self._post_execution_hooks: List[Callable] = []
        
        # Initialize tool
        self._initialize()
    
    @abstractmethod
    def _initialize(self):
        """Initialize tool-specific resources"""
        pass
    
    @abstractmethod
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """
        Internal implementation of tool execution
        
        Args:
            tool_input: Validated tool input
            
        Returns:
            Tool execution result
        """
        pass
    
    @abstractmethod
    def get_available_actions(self) -> List[str]:
        """
        Get list of available actions this tool can perform
        
        Returns:
            List of action names
        """
        pass

    
    @abstractmethod
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """
        Get input schema for a specific action
        
        Args:
            action: Action name
            
        Returns:
            JSON schema for the action parameters
        """
        pass

    # === FC 可见性（可选覆盖）===
    def get_fc_visibility(self) -> Dict[str, Any]:
        """
        返回该工具的默认 Function Call 可见性配置（可由具体工具覆盖）。

        返回结构示例：
        {"expose": True/False, "allowed_actions": ["action_a", "action_b"]}

        说明：
        - 默认不暴露，防止工具被 LLM 误用；建议具体业务工具显式覆盖。
        - BaseAgent 会将该默认配置与 fc_policies.yaml 进行合并（策略优先）。
        """
        return {"expose": False, "allowed_actions": []}

    # === 动作语义（可选覆盖）===
    def get_action_stage(self, action: str) -> str:
        """
        返回动作所属阶段，用于 ReAct 的阶段性最小暴露控制：
        - "plan": 规划类（如提示词生成、参数筹备）
        - "act": 执行类（如真实生成、下载、处理）
        默认视为 "act"。
        """
        return "act"
    
    async def execute(self, tool_input: Union[ToolInput, Dict[str, Any]]) -> ToolOutput:
        """
        Execute the tool with given input
        
        Args:
            tool_input: Tool input data
            
        Returns:
            Tool execution output
        """
        start_time = time.time()
        
        try:
            # Convert dict to ToolInput if needed
            if isinstance(tool_input, dict):
                tool_input = ToolInput(**tool_input)
            
            # Validate input
            self._validate_input(tool_input)
            
            # Update status
            self.status = ToolStatus.RUNNING
            self.execution_count += 1
            
            self.logger.info(f"Executing {self.metadata.name}:{tool_input.action}")
            
            # Execute pre-hooks
            await self._execute_hooks(self._pre_execution_hooks, tool_input)
            
            # Execute tool with timeout using minimal inline resolver
            timeout = _resolve_timeout(
                tool_name=self.metadata.name,
                explicit_timeout=tool_input.timeout,
                tool_config=self.config,
                context=tool_input.context or {},
            )
            
            result = await asyncio.wait_for(
                self._execute_impl(tool_input),
                timeout=timeout
            )

            business_payload = result
            if isinstance(result, dict) and "success" in result:
                business_success = bool(result.get("success"))
                business_payload = dict(result)
                business_payload.pop("success", None)
                if not business_success:
                    error_msg = business_payload.pop("error", None) or "Business logic reported failure"
                    raise ToolError(error_msg, error_code="business_failure")

            # Calculate execution time
            execution_time = time.time() - start_time
            self.last_execution_time = execution_time
            self.total_execution_time += execution_time

            # Create successful output
            output = ToolOutput(
                success=True,
                result=business_payload,
                execution_time=execution_time,
                metadata={
                    "tool_name": self.metadata.name,
                    "tool_version": self.metadata.version,
                    "action": tool_input.action,
                    "execution_count": self.execution_count
                }
            )
            
            # Update status
            self.status = ToolStatus.COMPLETED
            
            # Execute post-hooks
            await self._execute_hooks(self._post_execution_hooks, tool_input, output)
            
            self.logger.info(f"Completed {self.metadata.name}:{tool_input.action} in {execution_time:.2f}s")
            
            return output
            
        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            self.status = ToolStatus.TIMEOUT
            self.error_count += 1
            
            error_msg = f"Tool {self.metadata.name}:{tool_input.action} timed out after {timeout}s"
            self.logger.error(error_msg)
            
            return ToolOutput(
                success=False,
                error=error_msg,
                execution_time=execution_time,
                metadata={"tool_name": self.metadata.name, "error_type": "timeout"}
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.status = ToolStatus.FAILED
            self.error_count += 1
            
            error_msg = f"Tool {self.metadata.name}:{tool_input.action} failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            
            # 若为自定义 ToolError，优先使用其 error_code 作为 error_type，便于Agent侧精细判断
            error_type = type(e).__name__
            try:
                from .base_tool import ToolError as _TE  # self import safe
                if isinstance(e, _TE) and getattr(e, 'error_code', None):
                    error_type = getattr(e, 'error_code')
            except Exception:
                pass

            error_details_struct: Dict[str, Any] | None = None
            if isinstance(e, ToolError):
                try:
                    error_details_struct = getattr(e, "details", None)
                except Exception:
                    error_details_struct = None

            return ToolOutput(
                success=False,
                error=error_msg,
                execution_time=execution_time,
                metadata={
                    "tool_name": self.metadata.name,
                    "error_type": error_type,
                    "error_details": str(e),
                    "error_details_struct": error_details_struct or {},
                }
            )
    
    def _validate_input(self, tool_input: ToolInput):
        """Validate tool input"""
        if not tool_input.action:
            raise ToolValidationError("Action is required", self.metadata.name)
        
        available_actions = self.get_available_actions()
        if tool_input.action not in available_actions:
            raise ToolValidationError(
                f"Unknown action '{tool_input.action}'. Available: {available_actions}",
                self.metadata.name
            )
        
        # Validate action-specific parameters
        self._validate_action_parameters(tool_input.action, tool_input.parameters)
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """Validate action-specific parameters (override in subclasses)"""
        pass
    
    async def _execute_hooks(self, hooks: List[Callable], *args, **kwargs):
        """Execute hooks"""
        for hook in hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(*args, **kwargs)
                else:
                    hook(*args, **kwargs)
            except Exception as e:
                self.logger.warning(f"Hook execution failed: {e}")
    
    def add_pre_execution_hook(self, hook: Callable):
        """Add pre-execution hook"""
        self._pre_execution_hooks.append(hook)
    
    def add_post_execution_hook(self, hook: Callable):
        """Add post-execution hook"""
        self._post_execution_hooks.append(hook)
    
    def get_status(self) -> Dict[str, Any]:
        """Get tool status information"""
        return {
            "name": self.metadata.name,
            "version": self.metadata.version,
            "status": self.status.value,
            "execution_count": self.execution_count,
            "error_count": self.error_count,
            "total_execution_time": self.total_execution_time,
            "last_execution_time": self.last_execution_time,
            "average_execution_time": (
                self.total_execution_time / self.execution_count 
                if self.execution_count > 0 else 0
            ),
            "success_rate": (
                (self.execution_count - self.error_count) / self.execution_count
                if self.execution_count > 0 else 0
            )
        }
    
    def get_metadata(self) -> ToolMetadata:
        """Get tool metadata"""
        return self.metadata
    
    def get_config(self) -> Dict[str, Any]:
        """Get tool configuration"""
        return self.config.copy()
    
    def update_config(self, new_config: Dict[str, Any]):
        """Update tool configuration"""
        self.config.update(new_config)
    
    def reset_statistics(self):
        """Reset tool execution statistics"""
        self.execution_count = 0
        self.total_execution_time = 0.0
        self.last_execution_time = 0.0
        self.error_count = 0
    
    def __str__(self) -> str:
        return f"{self.metadata.name} v{self.metadata.version} ({self.metadata.tool_type.value})"
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.metadata.name}>"


class AsyncTool(BaseTool):
    """Base class for asynchronous tools"""
    
    def get_output_contract(self, action: str) -> Dict[str, Any]:
        """Describe structured output fields for downstream adapters (override per tool/action)."""
        return {}

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """Default async implementation - override in subclasses"""
        raise NotImplementedError("Async tools must implement _execute_impl")


class SyncTool(BaseTool):
    """Base class for synchronous tools"""
    
    def _execute_sync(self, tool_input: ToolInput) -> Any:
        """Synchronous execution implementation"""
        raise NotImplementedError("Sync tools must implement _execute_sync")
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """Wrap sync execution in async"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._execute_sync, tool_input
        )


class CompositeTool(BaseTool):
    """Tool that combines multiple sub-tools"""
    
    def __init__(self, metadata: ToolMetadata, sub_tools: List[BaseTool], **kwargs):
        self.sub_tools = {tool.metadata.name: tool for tool in sub_tools}
        super().__init__(metadata, **kwargs)
    
    def _initialize(self):
        """Initialize composite tool"""
        self.logger.info(f"Initialized composite tool with {len(self.sub_tools)} sub-tools")
    
    def get_available_actions(self) -> List[str]:
        """Get all actions from sub-tools"""
        actions = []
        for tool in self.sub_tools.values():
            for action in tool.get_available_actions():
                actions.append(f"{tool.metadata.name}.{action}")
        return actions
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """Get action schema from appropriate sub-tool"""
        if "." not in action:
            raise ToolValidationError(f"Composite tool actions must include tool name: {action}")
        
        tool_name, sub_action = action.split(".", 1)
        if tool_name not in self.sub_tools:
            raise ToolValidationError(f"Unknown sub-tool: {tool_name}")
        
        return self.sub_tools[tool_name].get_action_schema(sub_action)
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """Execute action on appropriate sub-tool"""
        action = tool_input.action
        if "." not in action:
            raise ToolValidationError(f"Composite tool actions must include tool name: {action}")
        
        tool_name, sub_action = action.split(".", 1)
        if tool_name not in self.sub_tools:
            raise ToolValidationError(f"Unknown sub-tool: {tool_name}")
        
        # Create sub-tool input
        sub_input = ToolInput(
            action=sub_action,
            parameters=tool_input.parameters,
            context=tool_input.context,
            timeout=tool_input.timeout
        )
        
        # Execute sub-tool
        result = await self.sub_tools[tool_name].execute(sub_input)
        
        # Return the result from sub-tool
        return result.result if result.success else result
