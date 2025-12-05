"""
MAS Orchestrator - 多Agent系统协调器
🎯 智能规划导向的多Agent协调核心
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from sqlalchemy.orm import Session

from .mas_communication import (
    CentralCommunicationHub,
    Message,
    MessageType,
    MessagePriority,
    get_communication_hub
)
from .mas_agent_adapter import MASAgentAdapter, get_agent_registry
from .mas_task_decomposer import TaskDecomposer, ExecutionPlan, SubTask, TaskStatus
from .mas_task_dispatcher import TaskDispatcher, DispatchStrategy, get_task_dispatcher
from ..models import Task, AgentType


class OrchestratorMode(Enum):
    """协调器模式"""
    PIPELINE = "pipeline"          # 管道模式（顺序执行）
    REACT = "react"               # ReAct模式（推理-行动循环）
    ADAPTIVE = "adaptive"         # 自适应模式
    PLANNING_FIRST = "planning_first"  # 🎯 规划优先模式


class WorkflowStatus(Enum):
    """工作流状态"""
    INITIALIZING = "initializing"
    PLANNING = "planning"         # 🎯 规划阶段
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OrchestratorState:
    """协调器状态"""
    workflow_id: str
    mode: OrchestratorMode
    status: WorkflowStatus
    current_phase: str
    execution_plan: Optional[ExecutionPlan]
    active_agents: List[str]
    completed_tasks: List[str]
    failed_tasks: List[str]
    performance_metrics: Dict[str, Any]
    created_at: datetime
    last_updated: datetime
    
    # 🎯 ReAct循环状态
    react_iteration: int = 0
    react_max_iterations: int = 10
    react_state: Dict[str, Any] = None
    
    # 🎯 规划状态
    planning_depth: str = "comprehensive"  # basic, standard, comprehensive
    planning_quality: float = 0.0
    planning_time_spent: int = 0  # minutes


class MASOrchestrator:
    """
    🎯 MAS协调器 - 多Agent系统的智能协调核心
    
    核心功能：
    1. 🎯 规划优先的任务协调
    2. ReAct式自适应执行
    3. 智能Agent调度和负载均衡
    4. 实时状态监控和异常处理
    5. 性能优化和资源管理
    """
    
    def __init__(self):
        self.communication_hub = get_communication_hub()
        self.agent_registry = get_agent_registry()
        self.task_decomposer = TaskDecomposer()
        self.task_dispatcher = get_task_dispatcher()
        
        # 协调器状态管理
        self.active_workflows: Dict[str, OrchestratorState] = {}
        self.workflow_callbacks: Dict[str, List[Callable]] = {}
        
        # 系统配置
        self.config = {
            "default_mode": OrchestratorMode.PLANNING_FIRST,
            "react_enabled": True,
            "planning_timeout_minutes": 10,
            "execution_timeout_minutes": 60,
            "heartbeat_interval_seconds": 30,
            "performance_monitoring_enabled": True
        }
        
        self.logger = logging.getLogger("mas_orchestrator")
        self.logger.info("🎯 MASOrchestrator initialized with planning-first architecture")
        
        # 启动后台任务
        asyncio.create_task(self._background_monitoring())
    
    async def orchestrate_workflow(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: Any,
        db: Session,
        mode: OrchestratorMode = None
    ) -> Dict[str, Any]:
        """
        🎯 协调工作流 - 核心协调方法
        
        Args:
            task: 主任务
            input_data: 输入数据
            execution: 执行上下文
            db: 数据库会话
            mode: 协调模式
        
        Returns:
            Dict: 执行结果
        """
        try:
            workflow_id = input_data.get("workflow_state_id", f"workflow_{task.id}")
            mode = mode or self.config["default_mode"]
            
            self.logger.info(f"🎯 Starting workflow orchestration - ID: {workflow_id}, Mode: {mode.value}")
            
            # 1️⃣ 初始化协调器状态
            orchestrator_state = await self._initialize_workflow_state(
                workflow_id, task, input_data, mode
            )
            
            # 2️⃣ 根据模式执行协调
            if mode == OrchestratorMode.PLANNING_FIRST:
                result = await self._orchestrate_planning_first(
                    orchestrator_state, task, input_data, execution, db
                )
            elif mode == OrchestratorMode.REACT:
                result = await self._orchestrate_react_mode(
                    orchestrator_state, task, input_data, execution, db
                )
            elif mode == OrchestratorMode.PIPELINE:
                result = await self._orchestrate_pipeline_mode(
                    orchestrator_state, task, input_data, execution, db
                )
            else:  # ADAPTIVE
                result = await self._orchestrate_adaptive_mode(
                    orchestrator_state, task, input_data, execution, db
                )
            
            # 3️⃣ 更新最终状态
            orchestrator_state.status = WorkflowStatus.COMPLETED
            orchestrator_state.last_updated = datetime.now()
            
            self.logger.info(f"🎯 Workflow orchestration completed - ID: {workflow_id}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Workflow orchestration failed: {e}")
            # 更新失败状态
            if workflow_id in self.active_workflows:
                self.active_workflows[workflow_id].status = WorkflowStatus.FAILED
            raise
    
    async def _initialize_workflow_state(
        self,
        workflow_id: str,
        task: Task,
        input_data: Dict[str, Any],
        mode: OrchestratorMode
    ) -> OrchestratorState:
        """初始化工作流状态"""
        
        orchestrator_state = OrchestratorState(
            workflow_id=workflow_id,
            mode=mode,
            status=WorkflowStatus.INITIALIZING,
            current_phase="initialization",
            execution_plan=None,
            active_agents=[],
            completed_tasks=[],
            failed_tasks=[],
            performance_metrics={},
            created_at=datetime.now(),
            last_updated=datetime.now(),
            react_state={
                "observations": [],
                "thoughts": [],
                "actions": [],
                "reflections": []
            } if mode == OrchestratorMode.REACT else {}
        )
        
        self.active_workflows[workflow_id] = orchestrator_state
        
        self.logger.info(f"🎯 Workflow state initialized - ID: {workflow_id}, Mode: {mode.value}")
        
        return orchestrator_state
    
    async def _orchestrate_planning_first(
        self,
        state: OrchestratorState,
        task: Task,
        input_data: Dict[str, Any],
        execution: Any,
        db: Session
    ) -> Dict[str, Any]:
        """
        🎯 规划优先协调模式
        核心理念：先进行深度规划，再执行优化的计划
        """
        try:
            self.logger.info("🎯 Starting PLANNING_FIRST orchestration mode")
            
            # Phase 1: 🎯 深度规划阶段
            state.status = WorkflowStatus.PLANNING
            state.current_phase = "deep_planning"
            
            planning_result = await self._execute_deep_planning_phase(
                state, task, input_data, execution, db
            )
            
            if not planning_result["success"]:
                raise Exception("Deep planning phase failed")
            
            state.execution_plan = planning_result["execution_plan"]
            state.planning_quality = planning_result["quality_score"]
            state.planning_time_spent = planning_result["time_spent"]
            
            self.logger.info(f"🎯 Deep planning completed - Quality: {state.planning_quality:.2f}, "
                           f"Time: {state.planning_time_spent}min")
            
            # Phase 2: 🎯 优化执行阶段
            state.status = WorkflowStatus.EXECUTING
            state.current_phase = "optimized_execution"
            
            execution_result = await self._execute_optimized_plan(
                state, task, input_data, execution, db
            )
            
            # Phase 3: 🎯 质量验证和优化
            if execution_result["success"]:
                state.current_phase = "quality_optimization"
                optimization_result = await self._apply_quality_optimization(
                    state, execution_result, execution, db
                )
                
                if optimization_result["applied"]:
                    self.logger.info(f"🎯 Quality optimization applied: {optimization_result['improvements']}")
                    execution_result.update(optimization_result["enhanced_result"])
            
            return execution_result
            
        except Exception as e:
            self.logger.error(f"❌ Planning-first orchestration failed: {e}")
            state.status = WorkflowStatus.FAILED
            raise
    
    async def _execute_deep_planning_phase(
        self,
        state: OrchestratorState,
        task: Task,
        input_data: Dict[str, Any],
        execution: Any,
        db: Session
    ) -> Dict[str, Any]:
        """🎯 执行深度规划阶段"""
        try:
            planning_start = datetime.now()
            self.logger.info("🎯 Starting deep planning phase")
            
            # 1️⃣ 发现规划能力Agent
            planning_agents = await self.communication_hub.discover_agents(
                planning_required=True
            )
            
            if not planning_agents:
                self.logger.warning("🎯 No planning-capable agents found, using standard planning")
                return await self._fallback_to_standard_planning(state, task, input_data)
            
            self.logger.info(f"🎯 Found {len(planning_agents)} planning-capable agents")
            
            # 2️⃣ 选择最佳规划Agent
            best_planning_agent = min(planning_agents, key=lambda x: x.load_factor)
            self.logger.info(f"🎯 Selected planning agent: {best_planning_agent.agent_id}")
            
            # 3️⃣ 执行深度需求分析
            requirements_analysis = await self._execute_requirements_analysis(
                best_planning_agent, task, input_data
            )
            
            # 4️⃣ 生成综合执行计划
            main_task = {
                "task_type": "video_generation",
                "input_data": input_data,
                "requirements": {
                    "duration": input_data.get("duration", 30),
                    "video_style": input_data.get("video_style", "professional"),
                    "aspect_ratio": input_data.get("aspect_ratio", "16:9"),
                    "quality_requirements": requirements_analysis.get("quality_requirements", {})
                }
            }
            
            available_agents = await self.communication_hub.discover_agents()
            execution_plan = await self.task_decomposer.decompose_task(
                main_task=main_task,
                workflow_id=state.workflow_id,
                available_agents=available_agents,
                optimization_preferences={
                    "optimization_goal": "quality",  # 规划优先模式注重质量
                    "planning_depth": "comprehensive"
                }
            )
            
            # 5️⃣ 规划质量评估
            quality_score = await self._evaluate_plan_quality(execution_plan, requirements_analysis)
            
            # 6️⃣ 如果质量不足，进行规划优化
            if quality_score < 0.8:
                self.logger.info("🎯 Plan quality below threshold, applying optimization")
                execution_plan = await self._optimize_execution_plan(execution_plan, requirements_analysis)
                quality_score = await self._evaluate_plan_quality(execution_plan, requirements_analysis)
            
            planning_time = (datetime.now() - planning_start).total_seconds() / 60
            
            return {
                "success": True,
                "execution_plan": execution_plan,
                "quality_score": quality_score,
                "time_spent": int(planning_time),
                "requirements_analysis": requirements_analysis,
                "planning_agent": best_planning_agent.agent_id
            }
            
        except Exception as e:
            self.logger.error(f"❌ Deep planning phase failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _execute_requirements_analysis(
        self,
        planning_agent,
        task: Task,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """🎯 执行需求分析"""
        try:
            # 发送深度需求分析请求
            analysis_message = Message(
                id=f"req_analysis_{datetime.now().timestamp()}",
                type=MessageType.PLAN_REQUEST,
                priority=MessagePriority.PLANNING,
                from_agent="orchestrator",
                to_agent=planning_agent.agent_id,
                workflow_id=task.workflow_id if hasattr(task, 'workflow_id') else str(task.id),
                payload={
                    "analysis_type": "deep_requirements_analysis",
                    "user_prompt": input_data.get("user_prompt", ""),
                    "constraints": {
                        "duration": input_data.get("duration", 30),
                        "style": input_data.get("video_style", "professional"),
                        "aspect_ratio": input_data.get("aspect_ratio", "16:9")
                    },
                    "analysis_depth": "comprehensive"
                },
                timestamp=datetime.now()
            )
            
            success = await self.communication_hub.send_message(analysis_message)
            if not success:
                raise Exception("Failed to send requirements analysis request")
            
            # 等待响应（简化实现）
            await asyncio.sleep(2)  # 实际应该监听响应消息
            
            # 返回分析结果（简化实现）
            return {
                "complexity_level": "medium",
                "scene_count_estimate": 4,
                "quality_requirements": {
                    "visual_quality": "high",
                    "narrative_coherence": "high",
                    "technical_quality": "standard"
                },
                "resource_requirements": {
                    "gpu_intensive": True,
                    "estimated_gpu_hours": 1.5
                },
                "optimization_opportunities": [
                    "parallel_image_generation",
                    "batch_processing",
                    "quality_presets"
                ]
            }
            
        except Exception as e:
            self.logger.error(f"❌ Requirements analysis failed: {e}")
            # 返回默认分析
            return {
                "complexity_level": "medium",
                "quality_requirements": {},
                "resource_requirements": {},
                "optimization_opportunities": []
            }
    
    async def _evaluate_plan_quality(
        self, execution_plan: ExecutionPlan, requirements_analysis: Dict[str, Any]
    ) -> float:
        """🎯 评估执行计划质量"""
        try:
            quality_factors = {}
            
            # 1. 任务覆盖度评估
            required_capabilities = set()
            for req in requirements_analysis.get("required_capabilities", []):
                required_capabilities.add(req)
            
            plan_capabilities = set()
            for task in execution_plan.subtasks:
                plan_capabilities.update(task.required_capabilities)
            
            coverage_score = len(required_capabilities.intersection(plan_capabilities)) / max(len(required_capabilities), 1)
            quality_factors["coverage"] = coverage_score
            
            # 2. 依赖关系合理性
            dependency_score = 1.0
            if len(execution_plan.dependencies) > len(execution_plan.subtasks) * 1.5:
                dependency_score = 0.7  # 过多依赖降低分数
            quality_factors["dependencies"] = dependency_score
            
            # 3. 资源分配合理性
            resource_score = 1.0
            gpu_tasks = [t for t in execution_plan.subtasks if "image_generation" in t.required_capabilities or "video_generation" in t.required_capabilities]
            if len(gpu_tasks) > 3:  # GPU密集任务过多
                resource_score = 0.8
            quality_factors["resources"] = resource_score
            
            # 4. 时间估算合理性
            total_time = execution_plan.estimated_total_duration
            expected_time = requirements_analysis.get("expected_duration", 60)
            if total_time > expected_time * 1.5:
                time_score = 0.7
            elif total_time > expected_time * 1.2:
                time_score = 0.9
            else:
                time_score = 1.0
            quality_factors["timing"] = time_score
            
            # 5. 🎯 规划深度评估
            planning_score = 1.0
            if len(execution_plan.optimization_suggestions) > 0:
                planning_score = 1.0
            if len(execution_plan.contingency_plans) > 0:
                planning_score = min(1.0, planning_score + 0.1)
            quality_factors["planning_depth"] = planning_score
            
            # 综合质量评分
            weights = {
                "coverage": 0.25,
                "dependencies": 0.20,
                "resources": 0.20,
                "timing": 0.15,
                "planning_depth": 0.20
            }
            
            overall_quality = sum(
                quality_factors[factor] * weights[factor] 
                for factor in quality_factors
            )
            
            self.logger.info(f"🎯 Plan quality evaluation: {overall_quality:.2f} - Factors: {quality_factors}")
            
            return overall_quality
            
        except Exception as e:
            self.logger.error(f"❌ Plan quality evaluation failed: {e}")
            return 0.5  # 默认中等质量
    
    async def _optimize_execution_plan(
        self, execution_plan: ExecutionPlan, requirements_analysis: Dict[str, Any]
    ) -> ExecutionPlan:
        """🎯 优化执行计划"""
        try:
            self.logger.info("🎯 Applying execution plan optimization")
            
            # 1. 并行化优化
            independent_tasks = [
                task for task in execution_plan.subtasks 
                if not task.dependencies
            ]
            
            if len(independent_tasks) > 1:
                # 调整执行策略为并行
                execution_plan.execution_strategy = "aggressive_parallel"
                self.logger.info("🎯 Optimization: Enabled aggressive parallel execution")
            
            # 2. 资源优化
            gpu_tasks = [
                task for task in execution_plan.subtasks 
                if any(cap in task.required_capabilities for cap in ["image_generation", "video_generation"])
            ]
            
            if len(gpu_tasks) > 2:
                # 添加批处理优化
                for task in gpu_tasks:
                    if task.estimated_duration > 15:
                        # 分解为更小的批次
                        task.estimated_duration = int(task.estimated_duration * 0.8)  # 批处理效率提升
                
                execution_plan.optimization_suggestions.append(
                    "Applied GPU batch processing optimization for resource efficiency"
                )
                self.logger.info("🎯 Optimization: Applied GPU batch processing")
            
            # 3. 时间优化
            if execution_plan.estimated_total_duration > 60:
                # 添加时间压缩策略
                for task in execution_plan.subtasks:
                    if task.priority < 7:  # 低优先级任务
                        task.estimated_duration = int(task.estimated_duration * 0.9)
                
                execution_plan.estimated_total_duration = sum(
                    task.estimated_duration for task in execution_plan.subtasks
                )
                execution_plan.optimization_suggestions.append(
                    "Applied time compression optimization for low-priority tasks"
                )
                self.logger.info("🎯 Optimization: Applied time compression")
            
            # 4. 🎯 增加规划验证步骤
            planning_validation_task = SubTask(
                task_id=f"{execution_plan.workflow_id}_planning_validation",
                task_type=TaskStatus.PENDING,
                task_name="Planning Validation & Adjustment",
                description="Validate and adjust execution plan during execution",
                required_capabilities=["planning_validation", "adaptive_coordination"],
                input_data={"execution_plan": execution_plan.plan_id},
                expected_output={"validation_result": "plan validation report"},
                estimated_duration=3,
                priority=9,  # 高优先级
                dependencies=[]
            )
            
            # 在第一个任务后插入验证任务
            if execution_plan.subtasks:
                planning_validation_task.dependencies = [
                    TaskDependency(
                        source_task_id=execution_plan.subtasks[0].task_id,
                        target_task_id=planning_validation_task.task_id,
                        dependency_type=DependencyType.SEQUENTIAL
                    )
                ]
                execution_plan.subtasks.insert(1, planning_validation_task)
                self.logger.info("🎯 Optimization: Added planning validation checkpoint")
            
            return execution_plan
            
        except Exception as e:
            self.logger.error(f"❌ Plan optimization failed: {e}")
            return execution_plan  # 返回原计划
    
    async def _execute_optimized_plan(
        self,
        state: OrchestratorState,
        task: Task,
        input_data: Dict[str, Any],
        execution: Any,
        db: Session
    ) -> Dict[str, Any]:
        """🎯 执行优化后的计划"""
        try:
            self.logger.info("🎯 Starting optimized plan execution")
            
            if not state.execution_plan:
                raise Exception("No execution plan available")
            
            # 1️⃣ 分发任务到Agent
            dispatch_result = await self.task_dispatcher.dispatch_execution_plan(
                state.execution_plan,
                DispatchStrategy.PLANNING_OPTIMIZED
            )
            
            if not dispatch_result.success:
                raise Exception(f"Task dispatch failed: {dispatch_result.warnings}")
            
            self.logger.info(f"🎯 Tasks dispatched: {len(dispatch_result.assignments)} assigned, "
                           f"{len(dispatch_result.unassigned_tasks)} unassigned")
            
            # 2️⃣ 监控执行进度
            execution_result = await self._monitor_plan_execution(
                state, dispatch_result, execution, db
            )
            
            # 3️⃣ 处理未分配的任务
            if dispatch_result.unassigned_tasks:
                self.logger.warning(f"🎯 {len(dispatch_result.unassigned_tasks)} tasks remain unassigned")
                # 可以实现重试逻辑或降级处理
            
            return execution_result
            
        except Exception as e:
            self.logger.error(f"❌ Optimized plan execution failed: {e}")
            raise
    
    async def _monitor_plan_execution(
        self,
        state: OrchestratorState,
        dispatch_result,
        execution: Any,
        db: Session
    ) -> Dict[str, Any]:
        """🎯 监控计划执行"""
        try:
            self.logger.info("🎯 Starting plan execution monitoring")
            
            # 简化实现：等待一段时间后返回模拟结果
            # 实际应该监听Agent响应消息和状态更新
            
            total_estimated_time = dispatch_result.total_estimated_time
            monitoring_intervals = max(1, total_estimated_time // 10)  # 10个检查点
            
            for i in range(monitoring_intervals):
                await asyncio.sleep(min(30, total_estimated_time * 60 // monitoring_intervals))  # 最多等30秒
                
                progress_percentage = int((i + 1) / monitoring_intervals * 80)  # 80%为主要执行
                
                # 更新执行进度
                execution.progress_percentage = progress_percentage
                execution.status_message = f"🎯 Plan execution in progress - Phase {i+1}/{monitoring_intervals}"
                
                self.logger.info(f"🎯 Execution progress: {progress_percentage}%")
                
                # 检查是否有失败的任务需要处理
                # 这里应该实现实际的任务状态检查逻辑
            
            # 模拟成功完成
            execution.progress_percentage = 100
            execution.status_message = "🎯 Plan execution completed successfully"
            
            # 返回执行结果
            result = {
                "success": True,
                "workflow_id": state.workflow_id,
                "execution_time_minutes": total_estimated_time,
                "completed_tasks": len(dispatch_result.assignments),
                "failed_tasks": 0,
                "quality_metrics": {
                    "planning_quality": state.planning_quality,
                    "execution_efficiency": 0.9,
                    "resource_utilization": dispatch_result.resource_utilization
                },
                "final_output": {
                    "video_url": f"/outputs/{state.workflow_id}/final_video.mp4",
                    "metadata": {"duration": 30, "format": "mp4", "quality": "high"}
                }
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Plan execution monitoring failed: {e}")
            raise
    
    async def _apply_quality_optimization(
        self,
        state: OrchestratorState,
        execution_result: Dict[str, Any],
        execution: Any,
        db: Session
    ) -> Dict[str, Any]:
        """🎯 应用质量优化"""
        try:
            self.logger.info("🎯 Applying quality optimization")
            
            quality_metrics = execution_result.get("quality_metrics", {})
            planning_quality = quality_metrics.get("planning_quality", 0.8)
            execution_efficiency = quality_metrics.get("execution_efficiency", 0.8)
            
            improvements = []
            enhanced_result = execution_result.copy()
            
            # 1. 如果规划质量高但执行效率低，建议改进执行
            if planning_quality > 0.9 and execution_efficiency < 0.7:
                improvements.append("execution_optimization_recommended")
                enhanced_result["recommendations"] = [
                    "Consider agent performance tuning",
                    "Review resource allocation strategy"
                ]
            
            # 2. 如果整体质量高，可以应用额外优化
            if planning_quality > 0.8 and execution_efficiency > 0.8:
                improvements.append("high_quality_enhancement")
                enhanced_result["quality_enhanced"] = True
                enhanced_result["final_output"]["quality"] = "premium"
            
            # 3. 添加性能指标
            enhanced_result["optimization_metrics"] = {
                "planning_score": planning_quality,
                "execution_score": execution_efficiency,
                "overall_score": (planning_quality + execution_efficiency) / 2,
                "optimization_applied": len(improvements) > 0
            }
            
            optimization_result = {
                "applied": len(improvements) > 0,
                "improvements": improvements,
                "enhanced_result": enhanced_result
            }
            
            return optimization_result
            
        except Exception as e:
            self.logger.error(f"❌ Quality optimization failed: {e}")
            return {"applied": False, "improvements": [], "enhanced_result": execution_result}
    
    async def _fallback_to_standard_planning(
        self,
        state: OrchestratorState,
        task: Task,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """🎯 标准规划备选方案"""
        try:
            self.logger.info("🎯 Falling back to standard planning")
            
            # 使用任务分解器的标准规划
            main_task = {
                "task_type": "video_generation",
                "input_data": input_data,
                "requirements": {
                    "duration": input_data.get("duration", 30),
                    "video_style": input_data.get("video_style", "professional"),
                    "aspect_ratio": input_data.get("aspect_ratio", "16:9")
                }
            }
            
            available_agents = await self.communication_hub.discover_agents()
            execution_plan = await self.task_decomposer.decompose_task(
                main_task=main_task,
                workflow_id=state.workflow_id,
                available_agents=available_agents
            )
            
            return {
                "success": True,
                "execution_plan": execution_plan,
                "quality_score": 0.7,  # 标准质量
                "time_spent": 3,
                "requirements_analysis": {},
                "planning_agent": "standard_decomposer"
            }
            
        except Exception as e:
            self.logger.error(f"❌ Standard planning fallback failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _orchestrate_react_mode(
        self,
        state: OrchestratorState,
        task: Task,
        input_data: Dict[str, Any],
        execution: Any,
        db: Session
    ) -> Dict[str, Any]:
        """🎯 Iterative协调 - 推理-行动循环"""
        try:
            self.logger.info("🎯 Starting iterative mode orchestration")
            
            state.react_iteration = 0
            react_state = state.react_state
            
            while state.react_iteration < state.react_max_iterations:
                state.react_iteration += 1
                self.logger.info(f"🎯 Iteration {state.react_iteration}/{state.react_max_iterations}")
                
                # 1️⃣ OBSERVE - 观察当前状态
                observation = await self._observe_current_state(state, input_data)
                react_state["observations"].append(observation)
                
                # 2️⃣ THINK - 推理分析
                reasoning = await self._think_and_reason(observation, state, input_data)
                react_state["thoughts"].append(reasoning)
                
                # 3️⃣ PLAN - 🎯 规划下一步行动
                action_plan = await self._plan_next_action(reasoning, state, input_data)
                
                # 4️⃣ ACT - 执行行动
                action_result = await self._execute_action(action_plan, state, execution, db)
                react_state["actions"].append(action_result)
                
                # 5️⃣ REFLECT - 反思结果
                reflection = await self._reflect_on_results(action_result, state)
                react_state["reflections"].append(reflection)
                
                # 检查是否完成
                if reflection.get("workflow_complete", False):
                    self.logger.info(f"🎯 Iterative workflow completed in {state.react_iteration} iterations")
                    break
                
                # 检查是否需要调整策略
                if reflection.get("strategy_adjustment_needed", False):
                    self.logger.info("🎯 Strategy adjustment triggered in iterative loop")
                    # 可以实现策略调整逻辑
                
                await asyncio.sleep(1)  # 防止过快循环
            
            # 汇总结果
            final_result = {
                "success": True,
                "workflow_id": state.workflow_id,
                "react_iterations": state.react_iteration,
                "observations": len(react_state["observations"]),
                "reasoning_steps": len(react_state["thoughts"]),
                "actions_taken": len(react_state["actions"]),
                "reflections": len(react_state["reflections"]),
                "final_output": action_result.get("output", {}) if action_result else {}
            }
            
            return final_result
            
        except Exception as e:
            self.logger.error(f"❌ Iterative mode orchestration failed: {e}")
            raise
    
    async def _observe_current_state(self, state: OrchestratorState, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """🎯 观察当前状态"""
        return {
            "workflow_status": state.status.value,
            "completed_tasks": len(state.completed_tasks),
            "failed_tasks": len(state.failed_tasks),
            "active_agents": len(state.active_agents),
            "current_phase": state.current_phase,
            "timestamp": datetime.now().isoformat()
        }
    
    async def _think_and_reason(
        self, observation: Dict[str, Any], state: OrchestratorState, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """🎯 推理分析"""
        return {
            "analysis": "Analyzing current workflow state and determining next actions",
            "priorities": ["complete_remaining_tasks", "optimize_performance"],
            "constraints": ["resource_limitations", "time_constraints"],
            "opportunities": ["parallel_execution", "quality_enhancement"]
        }
    
    async def _plan_next_action(
        self, reasoning: Dict[str, Any], state: OrchestratorState, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """🎯 规划下一步行动"""
        return {
            "action_type": "execute_next_phase",
            "target_agents": ["concept_planner", "script_writer"],
            "expected_outcome": "Phase completion",
            "contingency": "Retry with different agents if needed"
        }
    
    async def _execute_action(
        self, action_plan: Dict[str, Any], state: OrchestratorState, execution: Any, db: Session
    ) -> Dict[str, Any]:
        """🎯 执行行动"""
        # 简化实现
        await asyncio.sleep(2)
        return {
            "action": action_plan["action_type"],
            "success": True,
            "output": {"result": "Action completed successfully"},
            "timestamp": datetime.now().isoformat()
        }
    
    async def _reflect_on_results(self, action_result: Dict[str, Any], state: OrchestratorState) -> Dict[str, Any]:
        """🎯 反思结果"""
        return {
            "success_rate": 1.0 if action_result.get("success") else 0.0,
            "workflow_complete": state.react_iteration >= 3,  # 简化的完成条件
            "strategy_adjustment_needed": False,
            "lessons_learned": ["Action executed successfully", "Continue current approach"]
        }
    
    async def _orchestrate_pipeline_mode(
        self, state: OrchestratorState, task: Task, input_data: Dict[str, Any], execution: Any, db: Session
    ) -> Dict[str, Any]:
        """🎯 管道模式协调"""
        # 简化实现 - 顺序执行各个Agent
        self.logger.info("🎯 Starting pipeline mode orchestration")
        return {"success": True, "mode": "pipeline", "workflow_id": state.workflow_id}
    
    async def _orchestrate_adaptive_mode(
        self, state: OrchestratorState, task: Task, input_data: Dict[str, Any], execution: Any, db: Session
    ) -> Dict[str, Any]:
        """🎯 自适应模式协调"""
        # 根据情况选择最佳模式
        self.logger.info("🎯 Starting adaptive mode orchestration")
        
        # 简单的自适应逻辑：如果输入复杂，使用规划优先；否则使用管道模式
        user_prompt = input_data.get("user_prompt", "")
        if len(user_prompt) > 100 or input_data.get("duration", 30) > 60:
            return await self._orchestrate_planning_first(state, task, input_data, execution, db)
        else:
            return await self._orchestrate_pipeline_mode(state, task, input_data, execution, db)
    
    async def _background_monitoring(self):
        """🎯 后台监控任务"""
        while True:
            try:
                await asyncio.sleep(self.config["heartbeat_interval_seconds"])
                
                # 检查活跃工作流状态
                current_time = datetime.now()
                for workflow_id, state in self.active_workflows.items():
                    time_since_update = (current_time - state.last_updated).total_seconds()
                    
                    # 检查超时
                    if time_since_update > self.config["execution_timeout_minutes"] * 60:
                        if state.status in [WorkflowStatus.EXECUTING, WorkflowStatus.PLANNING]:
                            self.logger.warning(f"⚠️ Workflow {workflow_id} timeout detected")
                            state.status = WorkflowStatus.FAILED
                
                # 清理完成的工作流（保留最近24小时的记录）
                cutoff_time = current_time - timedelta(hours=24)
                completed_workflows = [
                    workflow_id for workflow_id, state in self.active_workflows.items()
                    if state.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED] and 
                       state.last_updated < cutoff_time
                ]
                
                for workflow_id in completed_workflows:
                    del self.active_workflows[workflow_id]
                    self.logger.info(f"🧹 Cleaned up completed workflow: {workflow_id}")
                
            except Exception as e:
                self.logger.error(f"❌ Background monitoring error: {e}")
    
    def get_orchestrator_status(self) -> Dict[str, Any]:
        """🎯 获取协调器状态"""
        active_workflows = len([
            state for state in self.active_workflows.values()
            if state.status in [WorkflowStatus.EXECUTING, WorkflowStatus.PLANNING]
        ])
        
        return {
            "active_workflows": active_workflows,
            "total_workflows": len(self.active_workflows),
            "supported_modes": [mode.value for mode in OrchestratorMode],
            "default_mode": self.config["default_mode"].value,
            "react_enabled": self.config["react_enabled"],
            "planning_first_available": True,  # 🎯 规划优先可用
            "system_health": "healthy",
            "performance_monitoring": self.config["performance_monitoring_enabled"]
        }


# 全局协调器实例
_orchestrator = None


def get_orchestrator() -> MASOrchestrator:
    """获取全局协调器实例"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MASOrchestrator()
    return _orchestrator
