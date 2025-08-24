"""
Multi-Agent Coordinator - 多智能体协调器
负责协调多个Agent的执行、通信和协作
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional, Union, Set, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
from sqlalchemy.orm import Session

from ..base import BaseAgent, AgentError
from ...models import Task, AgentExecution, TaskStatus, AgentType
from ...services.ai_client import AIClient
from ...core.workflow_state import WorkflowState


class MessageType(Enum):
    """Agent间消息类型"""
    REQUEST = "request"                    # 请求消息
    RESPONSE = "response"                 # 响应消息
    BROADCAST = "broadcast"               # 广播消息
    COORDINATION = "coordination"         # 协调消息
    STATUS_UPDATE = "status_update"       # 状态更新
    ERROR_NOTIFICATION = "error_notification"  # 错误通知
    RESOURCE_REQUEST = "resource_request" # 资源请求
    HANDOFF = "handoff"                   # 任务交接


class CoordinationPattern(Enum):
    """协调模式"""
    SEQUENTIAL = "sequential"             # 顺序执行
    PARALLEL = "parallel"                # 并行执行
    PIPELINE = "pipeline"                # 流水线
    COLLABORATIVE = "collaborative"       # 协作模式
    COMPETITIVE = "competitive"           # 竞争模式
    HIERARCHICAL = "hierarchical"         # 层次化
    PEER_TO_PEER = "peer_to_peer"        # 对等模式


@dataclass
class AgentMessage:
    """Agent间消息"""
    id: str
    type: MessageType
    sender: str
    receiver: Optional[str] = None  # None表示广播
    content: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = 1  # 1=高, 2=中, 3=低
    requires_response: bool = False
    timeout: Optional[timedelta] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoordinationState:
    """协调状态"""
    current_phase: str
    active_agents: Set[str]
    blocked_agents: Set[str]
    completed_agents: Set[str]
    dependencies: Dict[str, List[str]]
    resource_allocations: Dict[str, Dict[str, Any]]
    quality_metrics: Dict[str, float]
    performance_stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentCapability:
    """Agent能力描述"""
    agent_type: AgentType
    capabilities: List[str]
    quality_score: float
    performance_history: List[float]
    resource_requirements: Dict[str, Any]
    estimated_duration: float
    cost_estimate: float


class MessageBus:
    """消息总线 - 负责Agent间消息传递"""
    
    def __init__(self):
        self.subscribers: Dict[str, List[callable]] = defaultdict(list)
        self.message_queue: deque[AgentMessage] = deque()
        self.message_history: List[AgentMessage] = []
        self.pending_responses: Dict[str, AgentMessage] = {}
        self.logger = logging.getLogger("message_bus")
    
    async def publish(self, message: AgentMessage):
        """发布消息"""
        self.message_queue.append(message)
        self.message_history.append(message)
        
        # 通知订阅者
        if message.receiver:
            # 点对点消息
            if message.receiver in self.subscribers:
                for callback in self.subscribers[message.receiver]:
                    try:
                        await callback(message)
                    except Exception as e:
                        self.logger.error(f"Message callback failed: {e}")
        else:
            # 广播消息
            for agent_id, callbacks in self.subscribers.items():
                if agent_id != message.sender:
                    for callback in callbacks:
                        try:
                            await callback(message)
                        except Exception as e:
                            self.logger.error(f"Broadcast callback failed: {e}")
        
        # 处理超时
        if message.timeout:
            asyncio.create_task(self._handle_message_timeout(message))
    
    def subscribe(self, agent_id: str, callback: callable):
        """订阅消息"""
        self.subscribers[agent_id].append(callback)
    
    def unsubscribe(self, agent_id: str, callback: callable):
        """取消订阅"""
        if agent_id in self.subscribers:
            self.subscribers[agent_id].remove(callback)
    
    async def _handle_message_timeout(self, message: AgentMessage):
        """处理消息超时"""
        if message.timeout:
            await asyncio.sleep(message.timeout.total_seconds())
            
            if message.id in self.pending_responses:
                del self.pending_responses[message.id]
                self.logger.warning(f"Message {message.id} timed out")


class AgentCoordinator(BaseAgent):
    """
    Agent协调器 - 核心协调组件
    
    职责：
    1. Agent生命周期管理
    2. 任务分配和调度
    3. 消息路由和通信
    4. 依赖关系管理
    5. 资源分配和优化
    6. 冲突解决和异常处理
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="agent_coordinator",
            timeout_seconds=3600,
            tools=["workflow_analyzer", "resource_manager", "quality_monitor"]
        )
        
        # 消息总线
        self.message_bus = MessageBus()
        
        # Agent注册表
        self.registered_agents: Dict[str, AgentCapability] = {}
        self.active_agents: Dict[str, BaseAgent] = {}
        
        # 协调状态
        self.coordination_state = CoordinationState(
            current_phase="initialization",
            active_agents=set(),
            blocked_agents=set(),
            completed_agents=set(),
            dependencies={},
            resource_allocations={},
            quality_metrics={}
        )
        
        # 性能监控
        self.performance_tracker = {
            "message_throughput": 0,
            "average_response_time": 0.0,
            "coordination_efficiency": 0.0,
            "resource_utilization": 0.0
        }
        
        self.ai_client = AIClient()
        
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """执行协调流程"""
        
        self.logger.info(f"Starting agent coordination for task {task.task_id}")
        start_time = time.time()
        
        try:
            # 1. 初始化协调环境
            await self._initialize_coordination_environment(task, input_data)
            
            # 2. 分析任务并创建执行计划
            execution_plan = await self._create_execution_plan(task, input_data)
            
            # 3. 注册和初始化Agent
            await self._register_and_initialize_agents(execution_plan)
            
            # 4. 执行协调工作流
            results = await self._execute_coordinated_workflow(
                execution_plan, task, db
            )
            
            # 5. 协调清理和报告生成
            final_report = await self._finalize_coordination(
                results, time.time() - start_time
            )
            
            return final_report
            
        except Exception as e:
            await self._handle_coordination_error(e, task, db)
            raise
    
    async def _initialize_coordination_environment(
        self,
        task: Task,
        input_data: Dict[str, Any]
    ):
        """初始化协调环境"""
        
        self.coordination_state.current_phase = "initialization"
        
        # 设置消息总线订阅
        self.message_bus.subscribe(
            self.agent_name,
            self._handle_coordination_message
        )
        
        # 初始化性能监控
        self.performance_tracker = {
            "start_time": time.time(),
            "message_count": 0,
            "coordination_events": [],
            "resource_usage": {}
        }
    
    async def _create_execution_plan(
        self,
        task: Task,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建执行计划"""
        
        # 分析任务复杂度和需求
        complexity_analysis = await self._analyze_task_complexity(input_data)
        
        # 选择协调模式
        coordination_pattern = await self._select_coordination_pattern(
            complexity_analysis, input_data
        )
        
        # 确定Agent序列和依赖关系
        agent_sequence, dependencies = await self._plan_agent_dependencies(
            coordination_pattern, complexity_analysis
        )
        
        # 资源分配规划
        resource_plan = await self._plan_resource_allocation(
            agent_sequence, dependencies
        )
        
        return {
            "coordination_pattern": coordination_pattern,
            "agent_sequence": agent_sequence,
            "dependencies": dependencies,
            "resource_plan": resource_plan,
            "complexity_analysis": complexity_analysis,
            "estimated_duration": self._estimate_total_duration(agent_sequence),
            "quality_targets": await self._set_quality_targets(complexity_analysis)
        }
    
    async def _register_and_initialize_agents(
        self,
        execution_plan: Dict[str, Any]
    ):
        """注册和初始化Agent"""
        
        agent_sequence = execution_plan["agent_sequence"]
        
        for agent_config in agent_sequence:
            agent_type = agent_config["type"]
            agent_id = agent_config["id"]
            
            # 创建Agent实例
            agent = await self._create_agent_instance(agent_type, agent_config)
            
            # 注册Agent
            capability = AgentCapability(
                agent_type=agent_type,
                capabilities=agent_config.get("capabilities", []),
                quality_score=agent_config.get("quality_score", 7.0),
                performance_history=agent_config.get("performance_history", []),
                resource_requirements=agent_config.get("resources", {}),
                estimated_duration=agent_config.get("estimated_duration", 300),
                cost_estimate=agent_config.get("cost_estimate", 0.0)
            )
            
            self.registered_agents[agent_id] = capability
            self.active_agents[agent_id] = agent
            
            # 订阅Agent消息
            self.message_bus.subscribe(agent_id, agent._handle_message)
            
            self.logger.info(f"Registered agent: {agent_id} ({agent_type.value})")
    
    async def _execute_coordinated_workflow(
        self,
        execution_plan: Dict[str, Any],
        task: Task,
        db: Session
    ) -> Dict[str, Any]:
        """执行协调工作流"""
        
        coordination_pattern = execution_plan["coordination_pattern"]
        
        if coordination_pattern == CoordinationPattern.SEQUENTIAL:
            return await self._execute_sequential_workflow(execution_plan, task, db)
        elif coordination_pattern == CoordinationPattern.PARALLEL:
            return await self._execute_parallel_workflow(execution_plan, task, db)
        elif coordination_pattern == CoordinationPattern.PIPELINE:
            return await self._execute_pipeline_workflow(execution_plan, task, db)
        elif coordination_pattern == CoordinationPattern.COLLABORATIVE:
            return await self._execute_collaborative_workflow(execution_plan, task, db)
        else:
            return await self._execute_adaptive_workflow(execution_plan, task, db)
    
    async def _execute_sequential_workflow(
        self,
        execution_plan: Dict[str, Any],
        task: Task,
        db: Session
    ) -> Dict[str, Any]:
        """执行顺序工作流"""
        
        agent_sequence = execution_plan["agent_sequence"]
        results = {}
        current_data = task.input_data or {}
        
        for i, agent_config in enumerate(agent_sequence):
            agent_id = agent_config["id"]
            agent = self.active_agents[agent_id]
            
            self.coordination_state.current_phase = f"executing_{agent_id}"
            self.coordination_state.active_agents.add(agent_id)
            
            try:
                # 发送任务开始通知
                await self._send_coordination_message(
                    MessageType.COORDINATION,
                    agent_id,
                    {
                        "action": "start_execution",
                        "input_data": current_data,
                        "sequence_position": i,
                        "dependencies_satisfied": True
                    }
                )
                
                # 执行Agent
                agent_result = await agent.execute(task, current_data, db, i)
                results[agent_id] = agent_result
                
                # 更新数据流
                current_data.update(agent_result)
                
                # 更新协调状态
                self.coordination_state.active_agents.remove(agent_id)
                self.coordination_state.completed_agents.add(agent_id)
                
                # 发送完成通知
                await self._send_coordination_message(
                    MessageType.STATUS_UPDATE,
                    None,  # 广播
                    {
                        "agent": agent_id,
                        "status": "completed",
                        "result_summary": self._summarize_result(agent_result)
                    }
                )
                
            except Exception as e:
                await self._handle_agent_error(agent_id, e, task)
                raise
        
        return {
            "execution_pattern": "sequential",
            "agent_results": results,
            "final_output": current_data,
            "coordination_stats": self._get_coordination_stats()
        }
    
    async def _execute_parallel_workflow(
        self,
        execution_plan: Dict[str, Any],
        task: Task,
        db: Session
    ) -> Dict[str, Any]:
        """执行并行工作流"""
        
        agent_sequence = execution_plan["agent_sequence"]
        dependencies = execution_plan["dependencies"]
        
        # 创建并行执行组
        parallel_groups = self._create_parallel_groups(agent_sequence, dependencies)
        results = {}
        current_data = task.input_data or {}
        
        for group_index, agent_group in enumerate(parallel_groups):
            self.coordination_state.current_phase = f"parallel_group_{group_index}"
            
            # 并行执行当前组的Agent
            group_tasks = []
            for agent_config in agent_group:
                agent_id = agent_config["id"]
                agent = self.active_agents[agent_id]
                
                self.coordination_state.active_agents.add(agent_id)
                
                # 创建并行任务
                task_coroutine = self._execute_agent_with_coordination(
                    agent, agent_id, task, current_data, db, group_index
                )
                group_tasks.append(task_coroutine)
            
            # 等待并行组完成
            group_results = await asyncio.gather(*group_tasks, return_exceptions=True)
            
            # 处理结果和异常
            for i, result in enumerate(group_results):
                agent_id = agent_group[i]["id"]
                
                if isinstance(result, Exception):
                    await self._handle_agent_error(agent_id, result, task)
                    raise result
                else:
                    results[agent_id] = result
                    current_data.update(result)
                    
                    self.coordination_state.active_agents.remove(agent_id)
                    self.coordination_state.completed_agents.add(agent_id)
        
        return {
            "execution_pattern": "parallel",
            "agent_results": results,
            "final_output": current_data,
            "parallel_groups": len(parallel_groups),
            "coordination_stats": self._get_coordination_stats()
        }
    
    async def _execute_collaborative_workflow(
        self,
        execution_plan: Dict[str, Any],
        task: Task,
        db: Session
    ) -> Dict[str, Any]:
        """执行协作工作流"""
        
        agent_sequence = execution_plan["agent_sequence"]
        collaboration_sessions = []
        results = {}
        
        # 创建协作会话
        for collaboration_config in execution_plan.get("collaborations", []):
            session = await self._create_collaboration_session(collaboration_config)
            collaboration_sessions.append(session)
        
        # 执行协作流程
        for session in collaboration_sessions:
            session_result = await self._execute_collaboration_session(
                session, task, db
            )
            results[f"collaboration_{session['id']}"] = session_result
        
        return {
            "execution_pattern": "collaborative",
            "collaboration_results": results,
            "sessions_count": len(collaboration_sessions),
            "coordination_stats": self._get_coordination_stats()
        }
    
    async def _send_coordination_message(
        self,
        message_type: MessageType,
        receiver: Optional[str],
        content: Dict[str, Any],
        priority: int = 1
    ):
        """发送协调消息"""
        
        message = AgentMessage(
            id=f"coord_{int(time.time() * 1000)}",
            type=message_type,
            sender=self.agent_name,
            receiver=receiver,
            content=content,
            priority=priority,
            metadata={"coordination": True}
        )
        
        await self.message_bus.publish(message)
        self.performance_tracker["message_count"] += 1
    
    async def _handle_coordination_message(self, message: AgentMessage):
        """处理协调消息"""
        
        if message.type == MessageType.STATUS_UPDATE:
            await self._process_status_update(message)
        elif message.type == MessageType.ERROR_NOTIFICATION:
            await self._process_error_notification(message)
        elif message.type == MessageType.RESOURCE_REQUEST:
            await self._process_resource_request(message)
        elif message.type == MessageType.HANDOFF:
            await self._process_handoff_message(message)
    
    def _get_coordination_stats(self) -> Dict[str, Any]:
        """获取协调统计信息"""
        
        current_time = time.time()
        start_time = self.performance_tracker.get("start_time", current_time)
        duration = current_time - start_time
        
        return {
            "total_duration": duration,
            "message_count": self.performance_tracker["message_count"],
            "message_throughput": self.performance_tracker["message_count"] / max(duration, 1),
            "active_agents": len(self.coordination_state.active_agents),
            "completed_agents": len(self.coordination_state.completed_agents),
            "coordination_efficiency": len(self.coordination_state.completed_agents) / 
                                     max(len(self.registered_agents), 1),
            "current_phase": self.coordination_state.current_phase
        }
    
    # 实用方法
    async def _analyze_task_complexity(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析任务复杂度"""
        # 这里可以使用AI来分析任务复杂度
        # 简化实现
        return {
            "complexity_level": "medium",
            "estimated_agents_needed": 6,
            "parallel_potential": 0.6,
            "collaboration_benefit": 0.4
        }
    
    async def _select_coordination_pattern(
        self,
        complexity_analysis: Dict[str, Any],
        input_data: Dict[str, Any]
    ) -> CoordinationPattern:
        """选择协调模式"""
        
        complexity = complexity_analysis.get("complexity_level", "medium")
        parallel_potential = complexity_analysis.get("parallel_potential", 0.0)
        
        if parallel_potential > 0.7:
            return CoordinationPattern.PARALLEL
        elif complexity == "high":
            return CoordinationPattern.COLLABORATIVE
        else:
            return CoordinationPattern.SEQUENTIAL
    
    def _create_parallel_groups(
        self,
        agent_sequence: List[Dict],
        dependencies: Dict[str, List[str]]
    ) -> List[List[Dict]]:
        """创建并行执行组"""
        # 简化实现 - 基于依赖关系创建并行组
        groups = []
        remaining_agents = agent_sequence.copy()
        
        while remaining_agents:
            current_group = []
            agents_to_remove = []
            
            for agent_config in remaining_agents:
                agent_id = agent_config["id"]
                agent_dependencies = dependencies.get(agent_id, [])
                
                # 检查依赖是否满足
                dependencies_satisfied = all(
                    dep in [completed_agent for group in groups for completed_agent in group]
                    for dep in agent_dependencies
                )
                
                if dependencies_satisfied:
                    current_group.append(agent_config)
                    agents_to_remove.append(agent_config)
            
            if current_group:
                groups.append(current_group)
                for agent_config in agents_to_remove:
                    remaining_agents.remove(agent_config)
            else:
                # 避免死锁 - 添加剩余的Agent到最后一组
                groups.append(remaining_agents)
                break
        
        return groups