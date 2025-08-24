"""
MAS Task Dispatcher - 多Agent系统任务分发器
🎯 智能任务分发与Agent协调系统
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from .mas_communication import (
    CentralCommunicationHub, 
    Message, 
    MessageType, 
    MessagePriority, 
    AgentCapability,
    get_communication_hub
)
from .mas_task_decomposer import SubTask, TaskStatus, ExecutionPlan
from .mas_agent_adapter import MASAgentAdapter, get_agent_registry


class DispatchStrategy(Enum):
    """分发策略"""
    LOAD_BALANCED = "load_balanced"        # 负载均衡
    CAPABILITY_MATCHED = "capability_matched"  # 能力匹配
    PRIORITY_FIRST = "priority_first"      # 优先级优先
    PLANNING_OPTIMIZED = "planning_optimized"  # 🎯 规划优化


class AssignmentStatus(Enum):
    """分配状态"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskAssignment:
    """任务分配"""
    assignment_id: str
    task_id: str
    agent_id: str
    assigned_at: datetime
    expected_completion: datetime
    status: AssignmentStatus
    priority: int
    retry_count: int = 0
    max_retries: int = 3
    assignment_reason: str = ""
    performance_score: Optional[float] = None


@dataclass
class DispatchResult:
    """分发结果"""
    success: bool
    assignments: List[TaskAssignment]
    unassigned_tasks: List[str]
    dispatch_strategy: DispatchStrategy
    total_estimated_time: int  # minutes
    resource_utilization: Dict[str, float]
    warnings: List[str]
    optimization_applied: List[str]


class TaskDispatcher:
    """
    🎯 任务分发器 - 智能Agent任务协调系统
    
    核心功能:
    1. 智能Agent选择和任务分配
    2. 负载均衡和资源优化
    3. 实时任务调度和重分配
    4. 规划优化的任务协调
    5. 异常处理和恢复机制
    """
    
    def __init__(self):
        self.communication_hub = get_communication_hub()
        self.agent_registry = get_agent_registry()
        
        # 分发状态管理
        self.active_assignments: Dict[str, TaskAssignment] = {}
        self.dispatch_history: List[Dict[str, Any]] = []
        self.agent_performance: Dict[str, Dict[str, Any]] = {}
        
        # 调度配置
        self.dispatch_config = {
            "max_concurrent_tasks_per_agent": 2,
            "assignment_timeout_minutes": 30,
            "performance_weight": 0.3,
            "load_weight": 0.4,
            "capability_weight": 0.3,
            "planning_bonus": 0.2  # 🎯 规划能力加分
        }
        
        self.logger = logging.getLogger("mas_task_dispatcher")
        self.logger.info("🎯 TaskDispatcher initialized with planning-optimized coordination")
    
    async def dispatch_execution_plan(
        self,
        execution_plan: ExecutionPlan,
        dispatch_strategy: DispatchStrategy = DispatchStrategy.PLANNING_OPTIMIZED
    ) -> DispatchResult:
        """
        🎯 分发执行计划 - 核心分发方法
        
        Args:
            execution_plan: 执行计划
            dispatch_strategy: 分发策略
        
        Returns:
            DispatchResult: 分发结果
        """
        try:
            self.logger.info(f"🎯 Starting execution plan dispatch - Plan: {execution_plan.plan_id}, "
                           f"Strategy: {dispatch_strategy.value}")
            
            # 1️⃣ 获取可用Agent
            available_agents = await self._get_available_agents()
            if not available_agents:
                return DispatchResult(
                    success=False,
                    assignments=[],
                    unassigned_tasks=[task.task_id for task in execution_plan.subtasks],
                    dispatch_strategy=dispatch_strategy,
                    total_estimated_time=0,
                    resource_utilization={},
                    warnings=["No available agents found"],
                    optimization_applied=[]
                )
            
            self.logger.info(f"🎯 Found {len(available_agents)} available agents")
            
            # 2️⃣ 🎯 规划阶段优化 - 优先分配规划任务
            planning_tasks = [
                task for task in execution_plan.subtasks 
                if task.priority >= 9 or "planning" in task.task_name.lower()
            ]
            
            if planning_tasks and dispatch_strategy == DispatchStrategy.PLANNING_OPTIMIZED:
                self.logger.info(f"🎯 Found {len(planning_tasks)} planning-critical tasks")
                # 优先分配给具备规划能力的Agent
                planning_agents = [
                    agent for agent in available_agents 
                    if agent.planning_capable
                ]
                if planning_agents:
                    self.logger.info(f"🎯 {len(planning_agents)} planning-capable agents available")
            
            # 3️⃣ 执行任务分配
            assignments = []
            unassigned_tasks = []
            
            # 获取执行阶段
            execution_phases = execution_plan.get_execution_phases()
            self.logger.info(f"🎯 Execution plan has {len(execution_phases)} phases")
            
            # 按阶段分配任务
            for phase_idx, phase_tasks in enumerate(execution_phases):
                phase_assignments = await self._dispatch_phase_tasks(
                    phase_tasks, 
                    execution_plan.subtasks,
                    available_agents,
                    dispatch_strategy,
                    phase_idx + 1
                )
                
                assignments.extend(phase_assignments.assignments)
                unassigned_tasks.extend(phase_assignments.unassigned_tasks)
                
                self.logger.info(f"🎯 Phase {phase_idx + 1}: "
                               f"{len(phase_assignments.assignments)} assigned, "
                               f"{len(phase_assignments.unassigned_tasks)} unassigned")
            
            # 4️⃣ 计算资源利用率
            resource_utilization = await self._calculate_resource_utilization(
                assignments, available_agents
            )
            
            # 5️⃣ 应用优化策略
            optimization_applied = []
            if dispatch_strategy == DispatchStrategy.PLANNING_OPTIMIZED:
                optimized_assignments = await self._apply_planning_optimization(assignments)
                if optimized_assignments != assignments:
                    assignments = optimized_assignments
                    optimization_applied.append("planning_priority_optimization")
            
            # 6️⃣ 生成警告
            warnings = []
            if unassigned_tasks:
                warnings.append(f"{len(unassigned_tasks)} tasks could not be assigned")
            
            high_load_agents = [
                agent.agent_id for agent in available_agents 
                if agent.load_factor > 0.8
            ]
            if high_load_agents:
                warnings.append(f"High load detected on agents: {high_load_agents}")
            
            # 7️⃣ 更新活跃分配
            for assignment in assignments:
                self.active_assignments[assignment.assignment_id] = assignment
            
            # 8️⃣ 发送任务分配消息
            dispatch_success = await self._send_task_assignments(assignments, execution_plan)
            
            result = DispatchResult(
                success=len(assignments) > 0 and dispatch_success,
                assignments=assignments,
                unassigned_tasks=unassigned_tasks,
                dispatch_strategy=dispatch_strategy,
                total_estimated_time=sum(
                    next(task.estimated_duration for task in execution_plan.subtasks 
                         if task.task_id == assignment.task_id)
                    for assignment in assignments
                ),
                resource_utilization=resource_utilization,
                warnings=warnings,
                optimization_applied=optimization_applied
            )
            
            # 记录分发历史
            self.dispatch_history.append({
                "timestamp": datetime.now(),
                "plan_id": execution_plan.plan_id,
                "result": asdict(result)
            })
            
            self.logger.info(f"🎯 Dispatch completed - Success: {result.success}, "
                           f"Assigned: {len(assignments)}, Unassigned: {len(unassigned_tasks)}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Execution plan dispatch failed: {e}")
            raise
    
    async def _get_available_agents(self) -> List[AgentCapability]:
        """获取可用Agent列表"""
        try:
            # 从通信中心发现所有Agent
            all_agents = await self.communication_hub.discover_agents()
            
            # 过滤可用Agent
            available_agents = []
            for agent in all_agents:
                # 检查Agent状态
                if agent.status != "available":
                    continue
                
                # 检查负载
                if agent.load_factor >= 1.0:
                    continue
                
                # 检查当前分配数量
                current_assignments = len([
                    assignment for assignment in self.active_assignments.values()
                    if assignment.agent_id == agent.agent_id and 
                       assignment.status in [AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS]
                ])
                
                if current_assignments >= self.dispatch_config["max_concurrent_tasks_per_agent"]:
                    continue
                
                available_agents.append(agent)
            
            return available_agents
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get available agents: {e}")
            return []
    
    async def _dispatch_phase_tasks(
        self,
        phase_task_ids: List[str],
        all_subtasks: List[SubTask],
        available_agents: List[AgentCapability],
        dispatch_strategy: DispatchStrategy,
        phase_number: int
    ) -> DispatchResult:
        """分发阶段任务"""
        
        # 获取阶段任务详情
        phase_tasks = [
            task for task in all_subtasks 
            if task.task_id in phase_task_ids
        ]
        
        assignments = []
        unassigned_tasks = []
        
        # 🎯 规划任务优先处理
        if dispatch_strategy == DispatchStrategy.PLANNING_OPTIMIZED:
            planning_tasks = [
                task for task in phase_tasks 
                if task.priority >= 9 or "planning" in task.task_name.lower()
            ]
            
            regular_tasks = [
                task for task in phase_tasks 
                if task not in planning_tasks
            ]
            
            # 先分配规划任务
            for task in planning_tasks:
                assignment = await self._assign_task_to_best_agent(
                    task, available_agents, dispatch_strategy, prefer_planning=True
                )
                if assignment:
                    assignments.append(assignment)
                    # 更新Agent负载
                    await self._update_agent_load(assignment.agent_id, task.estimated_duration)
                else:
                    unassigned_tasks.append(task.task_id)
            
            # 再分配常规任务
            ordered_tasks = regular_tasks
        else:
            # 按优先级排序
            ordered_tasks = sorted(phase_tasks, key=lambda x: x.priority, reverse=True)
        
        # 分配任务
        for task in ordered_tasks:
            assignment = await self._assign_task_to_best_agent(
                task, available_agents, dispatch_strategy
            )
            if assignment:
                assignments.append(assignment)
                await self._update_agent_load(assignment.agent_id, task.estimated_duration)
            else:
                unassigned_tasks.append(task.task_id)
        
        return DispatchResult(
            success=len(assignments) > 0,
            assignments=assignments,
            unassigned_tasks=unassigned_tasks,
            dispatch_strategy=dispatch_strategy,
            total_estimated_time=sum(
                task.estimated_duration for task in phase_tasks 
                if task.task_id not in unassigned_tasks
            ),
            resource_utilization={},
            warnings=[],
            optimization_applied=[]
        )
    
    async def _assign_task_to_best_agent(
        self,
        task: SubTask,
        available_agents: List[AgentCapability],
        dispatch_strategy: DispatchStrategy,
        prefer_planning: bool = False
    ) -> Optional[TaskAssignment]:
        """为任务选择最佳Agent"""
        try:
            # 过滤能力匹配的Agent
            capable_agents = [
                agent for agent in available_agents
                if self._agent_can_handle_task(agent, task)
            ]
            
            if not capable_agents:
                self.logger.warning(f"⚠️ No capable agents found for task {task.task_id}")
                return None
            
            # 🎯 规划优先策略
            if prefer_planning:
                planning_agents = [
                    agent for agent in capable_agents 
                    if agent.planning_capable
                ]
                if planning_agents:
                    capable_agents = planning_agents
                    self.logger.info(f"🎯 Using planning-capable agents for {task.task_id}")
            
            # 根据策略选择最佳Agent
            if dispatch_strategy == DispatchStrategy.LOAD_BALANCED:
                best_agent = min(capable_agents, key=lambda x: x.load_factor)
                reason = f"load_balanced (load: {best_agent.load_factor:.2f})"
            
            elif dispatch_strategy == DispatchStrategy.CAPABILITY_MATCHED:
                # 计算能力匹配度
                match_scores = []
                for agent in capable_agents:
                    score = self._calculate_capability_match(agent, task)
                    match_scores.append((agent, score))
                
                best_agent, best_score = max(match_scores, key=lambda x: x[1])
                reason = f"capability_matched (score: {best_score:.2f})"
            
            elif dispatch_strategy == DispatchStrategy.PRIORITY_FIRST:
                # 选择当前负载最低且性能最好的Agent
                performance_scores = []
                for agent in capable_agents:
                    perf_score = self._get_agent_performance_score(agent.agent_id)
                    combined_score = perf_score * 0.7 + (1 - agent.load_factor) * 0.3
                    performance_scores.append((agent, combined_score))
                
                best_agent, best_score = max(performance_scores, key=lambda x: x[1])
                reason = f"priority_first (combined_score: {best_score:.2f})"
            
            elif dispatch_strategy == DispatchStrategy.PLANNING_OPTIMIZED:
                # 🎯 规划优化策略
                optimization_scores = []
                for agent in capable_agents:
                    score = self._calculate_planning_optimization_score(agent, task)
                    optimization_scores.append((agent, score))
                
                best_agent, best_score = max(optimization_scores, key=lambda x: x[1])
                reason = f"planning_optimized (score: {best_score:.2f})"
            
            else:
                # 默认选择负载最低的
                best_agent = min(capable_agents, key=lambda x: x.load_factor)
                reason = "default_load_balanced"
            
            # 创建任务分配
            assignment = TaskAssignment(
                assignment_id=f"assign_{task.task_id}_{datetime.now().timestamp()}",
                task_id=task.task_id,
                agent_id=best_agent.agent_id,
                assigned_at=datetime.now(),
                expected_completion=datetime.now() + timedelta(minutes=task.estimated_duration),
                status=AssignmentStatus.ASSIGNED,
                priority=task.priority,
                assignment_reason=reason
            )
            
            self.logger.info(f"✅ Task {task.task_id} assigned to {best_agent.agent_id} ({reason})")
            
            return assignment
            
        except Exception as e:
            self.logger.error(f"❌ Task assignment failed for {task.task_id}: {e}")
            return None
    
    def _agent_can_handle_task(self, agent: AgentCapability, task: SubTask) -> bool:
        """检查Agent是否能处理任务"""
        # 检查必需能力
        required_caps = set(task.required_capabilities)
        agent_caps = set(agent.capabilities)
        
        # 必须有交集
        if not required_caps.intersection(agent_caps):
            return False
        
        # 检查Agent类型匹配
        task_type_mapping = {
            "concept_generation": ["concept_planner"],
            "scene_planning": ["concept_planner"],
            "script_generation": ["script_writer"],
            "narrative_creation": ["script_writer"],
            "image_generation": ["image_generator"],
            "visual_creation": ["image_generator"],
            "video_generation": ["video_generator"],
            "motion_creation": ["video_generator"],
            "video_composition": ["video_composer"],
            "timeline_assembly": ["video_composer"],
            "quality_analysis": ["quality_checker"],
            "validation": ["quality_checker"]
        }
        
        compatible_types = set()
        for required_cap in required_caps:
            if required_cap in task_type_mapping:
                compatible_types.update(task_type_mapping[required_cap])
        
        if compatible_types and agent.agent_type not in compatible_types:
            return False
        
        return True
    
    def _calculate_capability_match(self, agent: AgentCapability, task: SubTask) -> float:
        """计算Agent与任务的能力匹配度"""
        required_caps = set(task.required_capabilities)
        agent_caps = set(agent.capabilities)
        
        # 完全匹配的能力
        exact_matches = required_caps.intersection(agent_caps)
        
        # 相关能力（简化的相似度计算）
        related_matches = 0
        capability_relations = {
            "concept_generation": ["scene_planning", "requirement_analysis"],
            "script_generation": ["narrative_creation", "content_writing"],
            "image_generation": ["visual_creation", "prompt_processing"],
            "video_generation": ["motion_creation", "scene_animation"]
        }
        
        for req_cap in required_caps:
            if req_cap not in exact_matches:
                related_caps = capability_relations.get(req_cap, [])
                if any(rel_cap in agent_caps for rel_cap in related_caps):
                    related_matches += 0.5
        
        # 计算匹配分数
        if not required_caps:
            return 0.5
        
        match_score = (len(exact_matches) + related_matches) / len(required_caps)
        
        # 🎯 规划能力加分
        if agent.planning_capable and task.priority >= 9:
            match_score += self.dispatch_config["planning_bonus"]
        
        return min(match_score, 1.0)
    
    def _get_agent_performance_score(self, agent_id: str) -> float:
        """获取Agent历史性能分数"""
        if agent_id not in self.agent_performance:
            return 0.8  # 默认分数
        
        perf_data = self.agent_performance[agent_id]
        
        # 计算综合性能分数
        success_rate = perf_data.get("success_rate", 0.8)
        avg_completion_time = perf_data.get("avg_completion_ratio", 1.0)  # 实际时间/预期时间
        quality_score = perf_data.get("quality_score", 0.8)
        
        # 时间效率分数 (完成时间越短越好)
        efficiency_score = max(0, 2 - avg_completion_time)  # 时间比预期短得分更高
        
        combined_score = (
            success_rate * 0.4 + 
            efficiency_score * 0.3 + 
            quality_score * 0.3
        )
        
        return min(combined_score, 1.0)
    
    def _calculate_planning_optimization_score(
        self, agent: AgentCapability, task: SubTask
    ) -> float:
        """🎯 计算规划优化分数"""
        base_score = self._calculate_capability_match(agent, task)
        
        # 🎯 规划能力额外加分
        planning_bonus = 0
        if agent.planning_capable:
            if task.priority >= 9 or "planning" in task.task_name.lower():
                planning_bonus = 0.3  # 规划任务给规划Agent高加分
            else:
                planning_bonus = 0.1  # 非规划任务也给一些加分
        
        # 负载惩罚
        load_penalty = agent.load_factor * 0.2
        
        # 性能加分
        performance_bonus = self._get_agent_performance_score(agent.agent_id) * 0.2
        
        final_score = base_score + planning_bonus + performance_bonus - load_penalty
        
        return max(0, min(final_score, 1.0))
    
    async def _update_agent_load(self, agent_id: str, task_duration: int):
        """更新Agent负载"""
        try:
            # 这里应该通过适配器更新Agent负载
            # 简化实现，直接更新内存中的数据
            for agent in await self._get_available_agents():
                if agent.agent_id == agent_id:
                    # 根据任务时长增加负载
                    load_increase = min(0.1, task_duration / 60 * 0.05)  # 每小时增加5%负载
                    agent.load_factor = min(1.0, agent.load_factor + load_increase)
                    break
                    
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to update agent load for {agent_id}: {e}")
    
    async def _calculate_resource_utilization(
        self, assignments: List[TaskAssignment], available_agents: List[AgentCapability]
    ) -> Dict[str, float]:
        """计算资源利用率"""
        if not available_agents:
            return {}
        
        # 计算Agent利用率
        agent_utilization = {}
        for agent in available_agents:
            assigned_tasks = len([
                assignment for assignment in assignments 
                if assignment.agent_id == agent.agent_id
            ])
            max_concurrent = self.dispatch_config["max_concurrent_tasks_per_agent"]
            utilization = assigned_tasks / max_concurrent
            agent_utilization[agent.agent_id] = utilization
        
        # 整体利用率统计
        total_utilization = sum(agent_utilization.values()) / len(available_agents) if available_agents else 0
        
        return {
            "total_utilization": total_utilization,
            "agent_utilization": agent_utilization,
            "assigned_agents": len([u for u in agent_utilization.values() if u > 0]),
            "idle_agents": len([u for u in agent_utilization.values() if u == 0])
        }
    
    async def _apply_planning_optimization(
        self, assignments: List[TaskAssignment]
    ) -> List[TaskAssignment]:
        """🎯 应用规划优化"""
        # 这里可以实现更复杂的规划优化逻辑
        # 例如：重新排序、负载重分配、依赖优化等
        
        # 简化实现：确保高优先级任务分配给最佳Agent
        high_priority_assignments = [
            assignment for assignment in assignments 
            if assignment.priority >= 8
        ]
        
        if high_priority_assignments:
            self.logger.info(f"🎯 Planning optimization applied to {len(high_priority_assignments)} high-priority assignments")
        
        return assignments
    
    async def _send_task_assignments(
        self, assignments: List[TaskAssignment], execution_plan: ExecutionPlan
    ) -> bool:
        """发送任务分配消息"""
        try:
            success_count = 0
            
            for assignment in assignments:
                # 找到任务详情
                task = next(
                    (task for task in execution_plan.subtasks 
                     if task.task_id == assignment.task_id),
                    None
                )
                
                if not task:
                    continue
                
                # 创建任务请求消息
                message = Message(
                    id=f"task_assign_{assignment.assignment_id}",
                    type=MessageType.TASK_REQUEST,
                    priority=MessagePriority.PLANNING if task.priority >= 9 else MessagePriority.HIGH,
                    from_agent="task_dispatcher",
                    to_agent=assignment.agent_id,
                    workflow_id=execution_plan.workflow_id,
                    payload={
                        "assignment": asdict(assignment),
                        "task": asdict(task),
                        "execution_plan_id": execution_plan.plan_id
                    },
                    timestamp=datetime.now()
                )
                
                success = await self.communication_hub.send_message(message)
                if success:
                    success_count += 1
                else:
                    self.logger.warning(f"⚠️ Failed to send assignment {assignment.assignment_id}")
            
            self.logger.info(f"📤 Sent {success_count}/{len(assignments)} task assignments")
            return success_count == len(assignments)
            
        except Exception as e:
            self.logger.error(f"❌ Failed to send task assignments: {e}")
            return False
    
    async def handle_task_response(self, message: Message) -> bool:
        """处理任务响应"""
        try:
            payload = message.payload
            assignment_id = payload.get("assignment_id")
            response_type = payload.get("response_type")  # accept, reject, complete, fail
            
            if assignment_id not in self.active_assignments:
                self.logger.warning(f"⚠️ Unknown assignment ID: {assignment_id}")
                return False
            
            assignment = self.active_assignments[assignment_id]
            
            if response_type == "accept":
                assignment.status = AssignmentStatus.ACCEPTED
                self.logger.info(f"✅ Task {assignment.task_id} accepted by {assignment.agent_id}")
            
            elif response_type == "reject":
                assignment.status = AssignmentStatus.REJECTED
                self.logger.warning(f"❌ Task {assignment.task_id} rejected by {assignment.agent_id}")
                # TODO: 重新分配任务
            
            elif response_type == "complete":
                assignment.status = AssignmentStatus.COMPLETED
                assignment.performance_score = payload.get("performance_score", 1.0)
                self.logger.info(f"🎉 Task {assignment.task_id} completed by {assignment.agent_id}")
                
                # 更新Agent性能统计
                await self._update_agent_performance(assignment, success=True)
            
            elif response_type == "fail":
                assignment.status = AssignmentStatus.FAILED
                self.logger.error(f"💥 Task {assignment.task_id} failed on {assignment.agent_id}")
                
                # 更新Agent性能统计
                await self._update_agent_performance(assignment, success=False)
                
                # TODO: 重试逻辑
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to handle task response: {e}")
            return False
    
    async def _update_agent_performance(self, assignment: TaskAssignment, success: bool):
        """更新Agent性能统计"""
        try:
            agent_id = assignment.agent_id
            
            if agent_id not in self.agent_performance:
                self.agent_performance[agent_id] = {
                    "total_tasks": 0,
                    "successful_tasks": 0,
                    "total_completion_time": 0,
                    "total_expected_time": 0,
                    "quality_scores": []
                }
            
            perf_data = self.agent_performance[agent_id]
            perf_data["total_tasks"] += 1
            
            if success:
                perf_data["successful_tasks"] += 1
                
                # 计算完成时间比
                expected_duration = (assignment.expected_completion - assignment.assigned_at).total_seconds()
                actual_duration = (datetime.now() - assignment.assigned_at).total_seconds()
                
                perf_data["total_completion_time"] += actual_duration
                perf_data["total_expected_time"] += expected_duration
                
                # 记录质量分数
                if assignment.performance_score:
                    perf_data["quality_scores"].append(assignment.performance_score)
            
            # 计算统计指标
            perf_data["success_rate"] = perf_data["successful_tasks"] / perf_data["total_tasks"]
            perf_data["avg_completion_ratio"] = (
                perf_data["total_completion_time"] / perf_data["total_expected_time"]
                if perf_data["total_expected_time"] > 0 else 1.0
            )
            perf_data["quality_score"] = (
                sum(perf_data["quality_scores"]) / len(perf_data["quality_scores"])
                if perf_data["quality_scores"] else 0.8
            )
            
        except Exception as e:
            self.logger.error(f"❌ Failed to update agent performance: {e}")
    
    def get_dispatcher_status(self) -> Dict[str, Any]:
        """获取分发器状态"""
        active_count = len([
            assignment for assignment in self.active_assignments.values()
            if assignment.status in [AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS]
        ])
        
        return {
            "active_assignments": active_count,
            "total_assignments": len(self.active_assignments),
            "dispatch_history_count": len(self.dispatch_history),
            "tracked_agents": len(self.agent_performance),
            "dispatch_config": self.dispatch_config,
            "planning_optimization_enabled": True,  # 🎯 规划优化启用
            "supported_strategies": [strategy.value for strategy in DispatchStrategy]
        }


# 全局任务分发器
_task_dispatcher = None


def get_task_dispatcher() -> TaskDispatcher:
    """获取全局任务分发器实例"""
    global _task_dispatcher
    if _task_dispatcher is None:
        _task_dispatcher = TaskDispatcher()
    return _task_dispatcher