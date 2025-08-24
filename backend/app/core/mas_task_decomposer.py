"""
MAS Task Decomposer - 多Agent系统任务分解器
🎯 强化规划能力的智能任务分解与协调
"""
import json
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

from .mas_communication import MessageType, MessagePriority, AgentCapability


class TaskType(Enum):
    """任务类型"""
    VIDEO_GENERATION = "video_generation"
    CONCEPT_PLANNING = "concept_planning"
    SCRIPT_WRITING = "script_writing"
    IMAGE_GENERATION = "image_generation"
    VIDEO_COMPOSITION = "video_composition"
    QUALITY_CHECK = "quality_check"


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    PLANNING = "planning"          # 🎯 规划阶段
    PLANNED = "planned"           # 🎯 已规划
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class DependencyType(Enum):
    """依赖类型"""
    SEQUENTIAL = "sequential"     # 顺序依赖
    PARALLEL = "parallel"         # 并行依赖
    CONDITIONAL = "conditional"   # 条件依赖
    RESOURCE = "resource"         # 资源依赖


@dataclass
class TaskDependency:
    """任务依赖"""
    source_task_id: str
    target_task_id: str
    dependency_type: DependencyType
    condition: Optional[Dict[str, Any]] = None
    resource_requirement: Optional[str] = None


@dataclass
class SubTask:
    """子任务"""
    task_id: str
    task_type: TaskType
    task_name: str
    description: str
    required_capabilities: List[str]
    input_data: Dict[str, Any]
    expected_output: Dict[str, Any]
    estimated_duration: int  # minutes
    priority: int  # 1-10
    dependencies: List[TaskDependency]
    assigned_agent: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class ExecutionPlan:
    """🎯 执行计划 - 强调规划的核心作用"""
    plan_id: str
    workflow_id: str
    main_task_id: str
    subtasks: List[SubTask]
    dependencies: List[TaskDependency]
    execution_strategy: str  # sequential, parallel, adaptive
    estimated_total_duration: int  # minutes
    resource_requirements: Dict[str, Any]
    contingency_plans: List[Dict[str, Any]]  # 🎯 应急计划
    optimization_suggestions: List[str]      # 🎯 优化建议
    created_at: datetime
    created_by: str = "task_decomposer"
    status: str = "draft"  # draft, approved, executing, completed
    
    def get_execution_phases(self) -> List[List[str]]:
        """🎯 获取执行阶段 - 基于依赖关系的智能分组"""
        phases = []
        remaining_tasks = set(task.task_id for task in self.subtasks)
        completed_tasks = set()
        
        while remaining_tasks:
            current_phase = []
            
            for task_id in list(remaining_tasks):
                task = next(t for t in self.subtasks if t.task_id == task_id)
                
                # 检查是否所有依赖都已完成
                dependencies_met = all(
                    dep.source_task_id in completed_tasks
                    for dep in task.dependencies
                )
                
                if dependencies_met:
                    current_phase.append(task_id)
            
            if not current_phase:
                # 检测循环依赖
                logging.error(f"🎯 Circular dependency detected in plan {self.plan_id}")
                break
            
            phases.append(current_phase)
            remaining_tasks -= set(current_phase)
            completed_tasks.update(current_phase)
        
        return phases


class TaskDecomposer:
    """
    🎯 任务分解器 - 智能规划导向的任务分解系统
    
    核心功能:
    1. 智能任务分析和分解
    2. 依赖关系建模和优化
    3. 资源需求评估和分配
    4. 执行计划生成和优化
    5. 应急策略制定
    """
    
    def __init__(self):
        self.logger = logging.getLogger("mas_task_decomposer")
        
        # 任务模板库
        self.task_templates = self._load_task_templates()
        
        # 分解策略
        self.decomposition_strategies = {
            TaskType.VIDEO_GENERATION: self._decompose_video_generation,
            TaskType.CONCEPT_PLANNING: self._decompose_concept_planning,
            TaskType.SCRIPT_WRITING: self._decompose_script_writing,
            TaskType.IMAGE_GENERATION: self._decompose_image_generation,
            TaskType.VIDEO_COMPOSITION: self._decompose_video_composition,
            TaskType.QUALITY_CHECK: self._decompose_quality_check
        }
        
        self.logger.info("🎯 TaskDecomposer initialized with enhanced planning capabilities")
    
    def _load_task_templates(self) -> Dict[TaskType, Dict[str, Any]]:
        """加载任务模板"""
        return {
            TaskType.VIDEO_GENERATION: {
                "estimated_duration": 30,
                "required_capabilities": ["video_generation", "content_creation"],
                "resource_requirements": {"gpu": True, "memory_gb": 8},
                "typical_subtasks": [
                    "concept_planning", "script_writing", "image_generation", 
                    "video_generation", "composition", "quality_check"
                ]
            },
            TaskType.CONCEPT_PLANNING: {
                "estimated_duration": 10,
                "required_capabilities": ["concept_generation", "scene_planning"],
                "resource_requirements": {"ai_model": "planning"},
                "planning_intensive": True  # 🎯 规划密集型任务
            },
            TaskType.SCRIPT_WRITING: {
                "estimated_duration": 15,
                "required_capabilities": ["script_generation", "narrative_creation"],
                "resource_requirements": {"ai_model": "text_generation"}
            },
            TaskType.IMAGE_GENERATION: {
                "estimated_duration": 20,
                "required_capabilities": ["image_generation", "visual_creation"],
                "resource_requirements": {"gpu": True, "ai_model": "image_generation"}
            },
            TaskType.VIDEO_GENERATION: {
                "estimated_duration": 25,
                "required_capabilities": ["video_generation", "motion_creation"],
                "resource_requirements": {"gpu": True, "memory_gb": 16}
            },
            TaskType.VIDEO_COMPOSITION: {
                "estimated_duration": 10,
                "required_capabilities": ["video_composition", "timeline_assembly"],
                "resource_requirements": {"cpu_cores": 4}
            },
            TaskType.QUALITY_CHECK: {
                "estimated_duration": 5,
                "required_capabilities": ["quality_analysis", "validation"],
                "resource_requirements": {"ai_model": "analysis"}
            }
        }
    
    async def decompose_task(
        self,
        main_task: Dict[str, Any],
        workflow_id: str,
        available_agents: List[AgentCapability],
        optimization_preferences: Dict[str, Any] = None
    ) -> ExecutionPlan:
        """
        🎯 核心任务分解方法 - 生成智能执行计划
        
        Args:
            main_task: 主任务描述
            workflow_id: 工作流ID
            available_agents: 可用Agent列表
            optimization_preferences: 优化偏好 (速度/质量/成本)
        
        Returns:
            ExecutionPlan: 详细执行计划
        """
        try:
            task_type = TaskType(main_task.get("task_type", "video_generation"))
            plan_id = str(uuid.uuid4())
            main_task_id = str(uuid.uuid4())
            
            self.logger.info(f"🎯 Starting intelligent task decomposition for {task_type.value}")
            
            # 1️⃣ 任务分析阶段
            task_analysis = await self._analyze_task_complexity(main_task, available_agents)
            self.logger.info(f"🎯 Task analysis completed - complexity: {task_analysis['complexity_level']}")
            
            # 2️⃣ 智能分解阶段
            subtasks = await self._intelligent_decomposition(
                main_task, task_type, task_analysis, workflow_id
            )
            self.logger.info(f"🎯 Generated {len(subtasks)} subtasks")
            
            # 3️⃣ 依赖关系建模
            dependencies = await self._model_task_dependencies(subtasks, task_analysis)
            self.logger.info(f"🎯 Modeled {len(dependencies)} task dependencies")
            
            # 4️⃣ 资源需求评估
            resource_requirements = await self._assess_resource_requirements(
                subtasks, available_agents
            )
            self.logger.info(f"🎯 Resource requirements assessed")
            
            # 5️⃣ 执行策略选择
            execution_strategy = await self._select_execution_strategy(
                subtasks, dependencies, optimization_preferences or {}
            )
            self.logger.info(f"🎯 Selected execution strategy: {execution_strategy}")
            
            # 6️⃣ 应急计划制定
            contingency_plans = await self._create_contingency_plans(
                subtasks, dependencies, available_agents
            )
            self.logger.info(f"🎯 Generated {len(contingency_plans)} contingency plans")
            
            # 7️⃣ 优化建议生成
            optimization_suggestions = await self._generate_optimization_suggestions(
                subtasks, dependencies, resource_requirements
            )
            
            # 8️⃣ 创建执行计划
            execution_plan = ExecutionPlan(
                plan_id=plan_id,
                workflow_id=workflow_id,
                main_task_id=main_task_id,
                subtasks=subtasks,
                dependencies=dependencies,
                execution_strategy=execution_strategy,
                estimated_total_duration=sum(task.estimated_duration for task in subtasks),
                resource_requirements=resource_requirements,
                contingency_plans=contingency_plans,
                optimization_suggestions=optimization_suggestions,
                created_at=datetime.now(),
                status="draft"
            )
            
            self.logger.info(f"🎯 Execution plan created - ID: {plan_id}, "
                           f"Duration: {execution_plan.estimated_total_duration}min, "
                           f"Strategy: {execution_strategy}")
            
            return execution_plan
            
        except Exception as e:
            self.logger.error(f"❌ Task decomposition failed: {e}")
            raise
    
    async def _analyze_task_complexity(
        self, 
        main_task: Dict[str, Any],
        available_agents: List[AgentCapability]
    ) -> Dict[str, Any]:
        """🎯 任务复杂度分析"""
        
        complexity_factors = {
            "data_complexity": 1,
            "processing_complexity": 1,
            "coordination_complexity": 1,
            "resource_intensity": 1
        }
        
        # 数据复杂度分析
        input_data = main_task.get("input_data", {})
        if len(input_data) > 10:
            complexity_factors["data_complexity"] = 3
        elif len(input_data) > 5:
            complexity_factors["data_complexity"] = 2
        
        # 处理复杂度分析
        task_requirements = main_task.get("requirements", {})
        duration = task_requirements.get("duration", 30)
        if duration > 120:
            complexity_factors["processing_complexity"] = 3
        elif duration > 60:
            complexity_factors["processing_complexity"] = 2
        
        # 协调复杂度分析
        required_agents = len([
            agent for agent in available_agents
            if any(cap in agent.capabilities 
                   for cap in task_requirements.get("required_capabilities", []))
        ])
        if required_agents > 4:
            complexity_factors["coordination_complexity"] = 3
        elif required_agents > 2:
            complexity_factors["coordination_complexity"] = 2
        
        # 资源强度分析
        if task_requirements.get("gpu_required", False):
            complexity_factors["resource_intensity"] = 2
        if task_requirements.get("high_memory", False):
            complexity_factors["resource_intensity"] = 3
        
        # 总体复杂度
        total_complexity = sum(complexity_factors.values())
        if total_complexity >= 10:
            complexity_level = "high"
        elif total_complexity >= 7:
            complexity_level = "medium"
        else:
            complexity_level = "low"
        
        return {
            "complexity_level": complexity_level,
            "complexity_score": total_complexity,
            "factors": complexity_factors,
            "recommended_agents": required_agents,
            "estimated_coordination_overhead": required_agents * 0.1  # 10% per agent
        }
    
    async def _intelligent_decomposition(
        self,
        main_task: Dict[str, Any],
        task_type: TaskType,
        task_analysis: Dict[str, Any],
        workflow_id: str
    ) -> List[SubTask]:
        """🎯 智能任务分解"""
        
        # 获取分解策略
        decomposition_strategy = self.decomposition_strategies.get(task_type)
        if not decomposition_strategy:
            return await self._generic_decomposition(main_task, workflow_id)
        
        # 执行具体分解策略
        subtasks = await decomposition_strategy(main_task, task_analysis, workflow_id)
        
        # 🎯 根据复杂度调整任务粒度
        if task_analysis["complexity_level"] == "high":
            subtasks = await self._refine_high_complexity_tasks(subtasks)
        
        return subtasks
    
    async def _decompose_video_generation(
        self,
        main_task: Dict[str, Any],
        task_analysis: Dict[str, Any],
        workflow_id: str
    ) -> List[SubTask]:
        """分解视频生成任务"""
        
        input_data = main_task.get("input_data", {})
        requirements = main_task.get("requirements", {})
        
        subtasks = []
        
        # 1. 概念规划任务 🎯 规划阶段
        concept_task = SubTask(
            task_id=f"{workflow_id}_concept_planning",
            task_type=TaskType.CONCEPT_PLANNING,
            task_name="Concept Planning & Strategy",
            description="Analyze requirements and create comprehensive video concept plan",
            required_capabilities=["concept_generation", "scene_planning", "requirement_analysis"],
            input_data={
                "user_prompt": input_data.get("user_prompt", ""),
                "video_style": requirements.get("video_style", "professional"),
                "duration": requirements.get("duration", 30),
                "aspect_ratio": requirements.get("aspect_ratio", "16:9"),
                "planning_depth": "comprehensive"  # 🎯 深度规划
            },
            expected_output={
                "concept_plan": "detailed video concept with scenes",
                "execution_strategy": "recommended execution approach",
                "resource_allocation": "suggested resource distribution"
            },
            estimated_duration=15,  # 增加规划时间
            priority=10,  # 🎯 最高优先级
            dependencies=[]
        )
        subtasks.append(concept_task)
        
        # 2. 脚本编写任务
        script_task = SubTask(
            task_id=f"{workflow_id}_script_writing",
            task_type=TaskType.SCRIPT_WRITING,
            task_name="Script Writing & Narrative Development",
            description="Generate detailed scripts and narratives for all scenes",
            required_capabilities=["script_generation", "narrative_creation", "content_writing"],
            input_data={"concept_plan": "from_previous_task"},
            expected_output={"scripts": "scene scripts with timing"},
            estimated_duration=10,
            priority=8,
            dependencies=[
                TaskDependency(
                    source_task_id=concept_task.task_id,
                    target_task_id=f"{workflow_id}_script_writing",
                    dependency_type=DependencyType.SEQUENTIAL
                )
            ]
        )
        subtasks.append(script_task)
        
        # 3. 图像生成任务
        image_task = SubTask(
            task_id=f"{workflow_id}_image_generation",
            task_type=TaskType.IMAGE_GENERATION,
            task_name="Visual Content Generation",
            description="Generate images for all scenes based on concept and scripts",
            required_capabilities=["image_generation", "visual_creation", "prompt_processing"],
            input_data={"concept_plan": "from_concept_task", "scripts": "from_script_task"},
            expected_output={"scene_images": "generated images with metadata"},
            estimated_duration=20,
            priority=7,
            dependencies=[
                TaskDependency(
                    source_task_id=concept_task.task_id,
                    target_task_id=f"{workflow_id}_image_generation",
                    dependency_type=DependencyType.SEQUENTIAL
                ),
                TaskDependency(
                    source_task_id=script_task.task_id,
                    target_task_id=f"{workflow_id}_image_generation",
                    dependency_type=DependencyType.SEQUENTIAL
                )
            ]
        )
        subtasks.append(image_task)
        
        # 4. 视频生成任务
        video_task = SubTask(
            task_id=f"{workflow_id}_video_generation",
            task_type=TaskType.VIDEO_GENERATION,
            task_name="Video Clip Generation",
            description="Generate video clips from images and scripts",
            required_capabilities=["video_generation", "motion_creation", "scene_animation"],
            input_data={"images": "from_image_task", "scripts": "from_script_task"},
            expected_output={"video_clips": "generated video segments"},
            estimated_duration=25,
            priority=6,
            dependencies=[
                TaskDependency(
                    source_task_id=image_task.task_id,
                    target_task_id=f"{workflow_id}_video_generation",
                    dependency_type=DependencyType.SEQUENTIAL
                )
            ]
        )
        subtasks.append(video_task)
        
        # 5. 视频合成任务
        composition_task = SubTask(
            task_id=f"{workflow_id}_video_composition",
            task_type=TaskType.VIDEO_COMPOSITION,
            task_name="Video Assembly & Composition",
            description="Assemble video clips into final composition",
            required_capabilities=["video_composition", "timeline_assembly", "audio_sync"],
            input_data={"video_clips": "from_video_task", "concept_plan": "from_concept_task"},
            expected_output={"final_video": "composed video file"},
            estimated_duration=10,
            priority=5,
            dependencies=[
                TaskDependency(
                    source_task_id=video_task.task_id,
                    target_task_id=f"{workflow_id}_video_composition",
                    dependency_type=DependencyType.SEQUENTIAL
                )
            ]
        )
        subtasks.append(composition_task)
        
        # 6. 质量检查任务
        quality_task = SubTask(
            task_id=f"{workflow_id}_quality_check",
            task_type=TaskType.QUALITY_CHECK,
            task_name="Quality Assurance & Validation",
            description="Comprehensive quality check and validation",
            required_capabilities=["quality_analysis", "validation", "compliance_check"],
            input_data={"final_video": "from_composition_task", "original_requirements": input_data},
            expected_output={"quality_report": "detailed quality assessment"},
            estimated_duration=8,
            priority=4,
            dependencies=[
                TaskDependency(
                    source_task_id=composition_task.task_id,
                    target_task_id=f"{workflow_id}_quality_check",
                    dependency_type=DependencyType.SEQUENTIAL
                )
            ]
        )
        subtasks.append(quality_task)
        
        return subtasks
    
    async def _decompose_concept_planning(
        self, main_task: Dict[str, Any], task_analysis: Dict[str, Any], workflow_id: str
    ) -> List[SubTask]:
        """分解概念规划任务"""
        # 概念规划是原子任务，通常不需要进一步分解
        # 但可以根据复杂度分解为多个规划阶段
        return [
            SubTask(
                task_id=f"{workflow_id}_concept_analysis",
                task_type=TaskType.CONCEPT_PLANNING,
                task_name="Concept Analysis & Planning",
                description="Comprehensive concept analysis and strategic planning",
                required_capabilities=["concept_generation", "scene_planning"],
                input_data=main_task.get("input_data", {}),
                expected_output={"concept_plan": "detailed concept plan"},
                estimated_duration=15,
                priority=10,
                dependencies=[]
            )
        ]
    
    async def _decompose_script_writing(
        self, main_task: Dict[str, Any], task_analysis: Dict[str, Any], workflow_id: str
    ) -> List[SubTask]:
        """分解脚本编写任务"""
        return [
            SubTask(
                task_id=f"{workflow_id}_script_creation",
                task_type=TaskType.SCRIPT_WRITING,
                task_name="Script Creation",
                description="Generate scripts for all scenes",
                required_capabilities=["script_generation", "narrative_creation"],
                input_data=main_task.get("input_data", {}),
                expected_output={"scripts": "scene scripts"},
                estimated_duration=12,
                priority=8,
                dependencies=[]
            )
        ]
    
    async def _decompose_image_generation(
        self, main_task: Dict[str, Any], task_analysis: Dict[str, Any], workflow_id: str
    ) -> List[SubTask]:
        """分解图像生成任务"""
        return [
            SubTask(
                task_id=f"{workflow_id}_image_creation",
                task_type=TaskType.IMAGE_GENERATION,
                task_name="Image Generation",
                description="Generate images for all scenes",
                required_capabilities=["image_generation", "visual_creation"],
                input_data=main_task.get("input_data", {}),
                expected_output={"images": "generated scene images"},
                estimated_duration=20,
                priority=7,
                dependencies=[]
            )
        ]
    
    async def _decompose_video_generation(
        self, main_task: Dict[str, Any], task_analysis: Dict[str, Any], workflow_id: str
    ) -> List[SubTask]:
        """分解视频生成任务"""
        return [
            SubTask(
                task_id=f"{workflow_id}_video_creation",
                task_type=TaskType.VIDEO_GENERATION,
                task_name="Video Generation",
                description="Generate video clips from images",
                required_capabilities=["video_generation", "motion_creation"],
                input_data=main_task.get("input_data", {}),
                expected_output={"videos": "generated video clips"},
                estimated_duration=25,
                priority=6,
                dependencies=[]
            )
        ]
    
    async def _decompose_video_composition(
        self, main_task: Dict[str, Any], task_analysis: Dict[str, Any], workflow_id: str
    ) -> List[SubTask]:
        """分解视频合成任务"""
        return [
            SubTask(
                task_id=f"{workflow_id}_video_assembly",
                task_type=TaskType.VIDEO_COMPOSITION,
                task_name="Video Assembly",
                description="Assemble video clips into final composition",
                required_capabilities=["video_composition", "timeline_assembly"],
                input_data=main_task.get("input_data", {}),
                expected_output={"final_video": "composed video"},
                estimated_duration=10,
                priority=5,
                dependencies=[]
            )
        ]
    
    async def _decompose_quality_check(
        self, main_task: Dict[str, Any], task_analysis: Dict[str, Any], workflow_id: str
    ) -> List[SubTask]:
        """分解质量检查任务"""
        return [
            SubTask(
                task_id=f"{workflow_id}_quality_validation",
                task_type=TaskType.QUALITY_CHECK,
                task_name="Quality Validation",
                description="Comprehensive quality check and validation",
                required_capabilities=["quality_analysis", "validation"],
                input_data=main_task.get("input_data", {}),
                expected_output={"quality_report": "quality assessment"},
                estimated_duration=8,
                priority=4,
                dependencies=[]
            )
        ]
    
    async def _generic_decomposition(
        self, main_task: Dict[str, Any], workflow_id: str
    ) -> List[SubTask]:
        """通用任务分解"""
        return [
            SubTask(
                task_id=f"{workflow_id}_generic_task",
                task_type=TaskType.VIDEO_GENERATION,
                task_name="Generic Task",
                description="Generic task execution",
                required_capabilities=["general"],
                input_data=main_task.get("input_data", {}),
                expected_output={"result": "task result"},
                estimated_duration=15,
                priority=5,
                dependencies=[]
            )
        ]
    
    async def _refine_high_complexity_tasks(self, subtasks: List[SubTask]) -> List[SubTask]:
        """🎯 细化高复杂度任务"""
        refined_tasks = []
        
        for task in subtasks:
            if task.estimated_duration > 20:  # 超过20分钟的任务需要进一步分解
                # 创建更小的子任务
                if task.task_type == TaskType.IMAGE_GENERATION:
                    # 分解为批次处理
                    batch_size = 3
                    num_batches = max(1, task.estimated_duration // 8)
                    
                    for i in range(num_batches):
                        batch_task = SubTask(
                            task_id=f"{task.task_id}_batch_{i+1}",
                            task_type=task.task_type,
                            task_name=f"{task.task_name} - Batch {i+1}",
                            description=f"Generate images for batch {i+1}",
                            required_capabilities=task.required_capabilities,
                            input_data=task.input_data.copy(),
                            expected_output=task.expected_output,
                            estimated_duration=8,
                            priority=task.priority,
                            dependencies=task.dependencies.copy()
                        )
                        refined_tasks.append(batch_task)
                else:
                    refined_tasks.append(task)
            else:
                refined_tasks.append(task)
        
        return refined_tasks
    
    async def _model_task_dependencies(
        self, subtasks: List[SubTask], task_analysis: Dict[str, Any]
    ) -> List[TaskDependency]:
        """🎯 建模任务依赖关系"""
        dependencies = []
        
        # 收集现有依赖
        for task in subtasks:
            dependencies.extend(task.dependencies)
        
        # 🎯 添加智能依赖优化
        if task_analysis["complexity_level"] == "high":
            # 高复杂度任务增加资源依赖
            for task in subtasks:
                if task.task_type in [TaskType.IMAGE_GENERATION, TaskType.VIDEO_GENERATION]:
                    # 添加资源依赖，避免GPU资源竞争
                    for other_task in subtasks:
                        if (other_task.task_id != task.task_id and 
                            other_task.task_type in [TaskType.IMAGE_GENERATION, TaskType.VIDEO_GENERATION]):
                            dependencies.append(
                                TaskDependency(
                                    source_task_id=task.task_id,
                                    target_task_id=other_task.task_id,
                                    dependency_type=DependencyType.RESOURCE,
                                    resource_requirement="gpu_exclusive"
                                )
                            )
        
        return dependencies
    
    async def _assess_resource_requirements(
        self, subtasks: List[SubTask], available_agents: List[AgentCapability]
    ) -> Dict[str, Any]:
        """🎯 评估资源需求"""
        
        total_cpu_hours = sum(task.estimated_duration / 60 for task in subtasks)
        gpu_tasks = [task for task in subtasks if task.task_type in [
            TaskType.IMAGE_GENERATION, TaskType.VIDEO_GENERATION
        ]]
        
        return {
            "total_cpu_hours": total_cpu_hours,
            "gpu_hours": sum(task.estimated_duration / 60 for task in gpu_tasks),
            "parallel_agents_needed": len(set(task.task_type for task in subtasks)),
            "memory_requirements": {
                "minimum_gb": 8,
                "recommended_gb": 16 if gpu_tasks else 8
            },
            "agent_requirements": {
                "concept_planners": len([t for t in subtasks if t.task_type == TaskType.CONCEPT_PLANNING]),
                "content_generators": len([t for t in subtasks if t.task_type in [
                    TaskType.IMAGE_GENERATION, TaskType.VIDEO_GENERATION
                ]]),
                "processors": len([t for t in subtasks if t.task_type in [
                    TaskType.SCRIPT_WRITING, TaskType.VIDEO_COMPOSITION, TaskType.QUALITY_CHECK
                ]])
            }
        }
    
    async def _select_execution_strategy(
        self, 
        subtasks: List[SubTask], 
        dependencies: List[TaskDependency],
        preferences: Dict[str, Any]
    ) -> str:
        """🎯 选择执行策略"""
        
        # 分析任务特征
        total_tasks = len(subtasks)
        has_dependencies = len(dependencies) > 0
        parallel_potential = len([
            task for task in subtasks 
            if not task.dependencies
        ])
        
        optimization_goal = preferences.get("optimization_goal", "balanced")  # speed, quality, cost, balanced
        
        if optimization_goal == "speed" and parallel_potential > 1:
            return "aggressive_parallel"
        elif optimization_goal == "quality":
            return "sequential_with_validation"
        elif optimization_goal == "cost":
            return "resource_conservative"
        elif has_dependencies and total_tasks > 3:
            return "adaptive_hybrid"
        else:
            return "sequential"
    
    async def _create_contingency_plans(
        self,
        subtasks: List[SubTask],
        dependencies: List[TaskDependency],
        available_agents: List[AgentCapability]
    ) -> List[Dict[str, Any]]:
        """🎯 创建应急计划"""
        
        contingency_plans = []
        
        # 1. Agent失效应急计划
        critical_tasks = [task for task in subtasks if task.priority >= 8]
        for task in critical_tasks:
            suitable_agents = [
                agent for agent in available_agents
                if any(cap in agent.capabilities for cap in task.required_capabilities)
            ]
            
            if len(suitable_agents) > 1:
                contingency_plans.append({
                    "trigger": f"agent_failure_{task.task_id}",
                    "description": f"Backup agent assignment for {task.task_name}",
                    "action": "reassign_to_backup_agent",
                    "backup_agents": [agent.agent_id for agent in suitable_agents[1:3]]
                })
        
        # 2. 资源不足应急计划
        resource_intensive_tasks = [
            task for task in subtasks 
            if task.task_type in [TaskType.IMAGE_GENERATION, TaskType.VIDEO_GENERATION]
        ]
        
        if resource_intensive_tasks:
            contingency_plans.append({
                "trigger": "resource_shortage",
                "description": "Reduce quality settings when resources are limited",
                "action": "fallback_to_lower_quality",
                "parameters": {
                    "image_resolution": "512x512",
                    "video_length_reduction": 0.8
                }
            })
        
        # 3. 时间超时应急计划
        contingency_plans.append({
            "trigger": "execution_timeout",
            "description": "Skip non-critical tasks when execution exceeds time budget",
            "action": "skip_optional_tasks",
            "skippable_tasks": [
                task.task_id for task in subtasks 
                if task.priority < 6
            ]
        })
        
        return contingency_plans
    
    async def _generate_optimization_suggestions(
        self,
        subtasks: List[SubTask],
        dependencies: List[TaskDependency],
        resource_requirements: Dict[str, Any]
    ) -> List[str]:
        """🎯 生成优化建议"""
        
        suggestions = []
        
        # 并行化建议
        independent_tasks = [task for task in subtasks if not task.dependencies]
        if len(independent_tasks) > 1:
            suggestions.append(
                f"Consider parallel execution of {len(independent_tasks)} independent tasks "
                f"to reduce total execution time by up to 40%"
            )
        
        # 资源优化建议
        gpu_hours = resource_requirements.get("gpu_hours", 0)
        if gpu_hours > 2:
            suggestions.append(
                "High GPU usage detected. Consider batch processing or GPU scheduling "
                "to optimize resource utilization"
            )
        
        # 任务优先级建议
        high_priority_tasks = len([task for task in subtasks if task.priority >= 8])
        if high_priority_tasks > 3:
            suggestions.append(
                "Multiple high-priority tasks detected. Consider load balancing "
                "to prevent resource conflicts"
            )
        
        # 依赖链优化建议
        max_dependency_chain = self._calculate_max_dependency_chain(subtasks, dependencies)
        if max_dependency_chain > 4:
            suggestions.append(
                f"Long dependency chain detected ({max_dependency_chain} tasks). "
                "Consider breaking down critical path for better fault tolerance"
            )
        
        return suggestions
    
    def _calculate_max_dependency_chain(
        self, subtasks: List[SubTask], dependencies: List[TaskDependency]
    ) -> int:
        """计算最长依赖链"""
        # 构建依赖图
        dependency_graph = {}
        for dep in dependencies:
            if dep.target_task_id not in dependency_graph:
                dependency_graph[dep.target_task_id] = []
            dependency_graph[dep.target_task_id].append(dep.source_task_id)
        
        # 计算最长路径
        def calculate_depth(task_id: str, visited: set) -> int:
            if task_id in visited:
                return 0
            visited.add(task_id)
            
            if task_id not in dependency_graph:
                return 1
            
            max_depth = 0
            for dependency in dependency_graph[task_id]:
                depth = calculate_depth(dependency, visited.copy())
                max_depth = max(max_depth, depth)
            
            return max_depth + 1
        
        max_chain = 0
        for task in subtasks:
            chain_length = calculate_depth(task.task_id, set())
            max_chain = max(max_chain, chain_length)
        
        return max_chain
    
    def get_decomposer_stats(self) -> Dict[str, Any]:
        """获取分解器统计信息"""
        return {
            "supported_task_types": [task_type.value for task_type in self.task_templates.keys()],
            "decomposition_strategies": len(self.decomposition_strategies),
            "template_count": len(self.task_templates),
            "planning_enhanced": True,  # 🎯 强调规划增强
            "version": "2.0_planning_focused"
        }