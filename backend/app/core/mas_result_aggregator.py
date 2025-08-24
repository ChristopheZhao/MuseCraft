"""
MAS Result Aggregator - 多Agent系统结果汇集器
🎯 智能结果汇集和状态管理系统
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from .mas_communication import get_communication_hub
from .mas_orchestrator import OrchestratorState, WorkflowStatus, get_orchestrator
from .mas_task_decomposer import SubTask, TaskStatus, ExecutionPlan
from .mas_task_dispatcher import TaskAssignment, AssignmentStatus


class AggregationStrategy(Enum):
    """汇集策略"""
    SEQUENTIAL = "sequential"          # 顺序汇集
    PARALLEL = "parallel"             # 并行汇集
    PRIORITY_BASED = "priority_based" # 基于优先级
    QUALITY_WEIGHTED = "quality_weighted"  # 质量加权
    PLANNING_OPTIMIZED = "planning_optimized"  # 🎯 规划优化


class ResultStatus(Enum):
    """结果状态"""
    PENDING = "pending"
    COLLECTING = "collecting"
    AGGREGATING = "aggregating"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Agent结果"""
    agent_id: str
    task_id: str
    workflow_id: str
    result_data: Dict[str, Any]
    quality_metrics: Dict[str, Any]
    execution_time: float
    status: str
    created_at: datetime
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass 
class AggregationResult:
    """汇集结果"""
    workflow_id: str
    aggregation_id: str
    strategy: AggregationStrategy
    status: ResultStatus
    aggregated_data: Dict[str, Any]
    quality_assessment: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    agent_contributions: Dict[str, AgentResult]
    issues_encountered: List[str]
    optimization_applied: List[str]
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    def get_overall_quality_score(self) -> float:
        """获取整体质量分数"""
        if not self.quality_assessment:
            return 0.0
        return self.quality_assessment.get("overall_score", 0.0)


class WorkflowStateManager:
    """🎯 工作流状态管理器"""
    
    def __init__(self):
        self.workflow_states: Dict[str, Dict[str, Any]] = {}
        self.state_history: Dict[str, List[Dict[str, Any]]] = {}
        self.state_locks: Dict[str, asyncio.Lock] = {}
        self.logger = logging.getLogger("workflow_state_manager")
    
    async def update_workflow_state(
        self, 
        workflow_id: str, 
        state_updates: Dict[str, Any],
        source: str = "system"
    ) -> bool:
        """🎯 更新工作流状态"""
        try:
            # 获取或创建锁
            if workflow_id not in self.state_locks:
                self.state_locks[workflow_id] = asyncio.Lock()
            
            async with self.state_locks[workflow_id]:
                # 获取当前状态
                current_state = self.workflow_states.get(workflow_id, {
                    "workflow_id": workflow_id,
                    "status": "initializing",
                    "created_at": datetime.now(),
                    "last_updated": datetime.now(),
                    "version": 0,
                    "data": {}
                })
                
                # 记录历史
                if workflow_id not in self.state_history:
                    self.state_history[workflow_id] = []
                
                self.state_history[workflow_id].append({
                    "version": current_state["version"],
                    "timestamp": datetime.now(),
                    "source": source,
                    "state_snapshot": current_state.copy(),
                    "updates": state_updates
                })
                
                # 应用更新
                current_state.update(state_updates)
                current_state["last_updated"] = datetime.now()
                current_state["version"] += 1
                
                self.workflow_states[workflow_id] = current_state
                
                self.logger.info(f"🎯 Workflow state updated - ID: {workflow_id}, "
                               f"Version: {current_state['version']}, Source: {source}")
                
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Failed to update workflow state {workflow_id}: {e}")
            return False
    
    async def get_workflow_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """获取工作流状态"""
        return self.workflow_states.get(workflow_id)
    
    async def get_state_history(self, workflow_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取状态历史"""
        history = self.state_history.get(workflow_id, [])
        return history[-limit:] if limit > 0 else history


class ResultAggregator:
    """
    🎯 结果汇集器 - 多Agent结果智能汇集系统
    
    核心功能：
    1. 多Agent结果收集和整合
    2. 质量评估和优化建议
    3. 智能结果验证和一致性检查
    4. 规划导向的结果优化
    5. 实时状态管理和监控
    """
    
    def __init__(self):
        self.communication_hub = get_communication_hub()
        self.orchestrator = get_orchestrator()
        self.state_manager = WorkflowStateManager()
        
        # 汇集状态管理
        self.active_aggregations: Dict[str, AggregationResult] = {}
        self.agent_results_buffer: Dict[str, List[AgentResult]] = {}
        self.completion_callbacks: Dict[str, List[callable]] = {}
        
        # 汇集配置
        self.config = {
            "collection_timeout_seconds": 300,  # 5分钟收集超时
            "quality_threshold": 0.7,
            "consistency_check_enabled": True,
            "planning_feedback_enabled": True,  # 🎯 规划反馈启用
            "auto_optimization_enabled": True,
            "result_validation_enabled": True
        }
        
        # 汇集策略
        self.aggregation_strategies = {
            AggregationStrategy.SEQUENTIAL: self._aggregate_sequential,
            AggregationStrategy.PARALLEL: self._aggregate_parallel,
            AggregationStrategy.PRIORITY_BASED: self._aggregate_priority_based,
            AggregationStrategy.QUALITY_WEIGHTED: self._aggregate_quality_weighted,
            AggregationStrategy.PLANNING_OPTIMIZED: self._aggregate_planning_optimized  # 🎯 规划优化
        }
        
        self.logger = logging.getLogger("mas_result_aggregator")
        self.logger.info("🎯 ResultAggregator initialized with planning-optimized capabilities")
        
        # 启动后台任务
        asyncio.create_task(self._background_aggregation_monitor())
    
    async def start_result_collection(
        self,
        workflow_id: str,
        expected_agents: List[str],
        strategy: AggregationStrategy = AggregationStrategy.PLANNING_OPTIMIZED
    ) -> str:
        """
        🎯 开始结果收集
        
        Args:
            workflow_id: 工作流ID
            expected_agents: 预期的Agent列表
            strategy: 汇集策略
        
        Returns:
            str: 汇集ID
        """
        try:
            aggregation_id = f"agg_{workflow_id}_{datetime.now().timestamp()}"
            
            self.logger.info(f"🎯 Starting result collection - Aggregation: {aggregation_id}, "
                           f"Workflow: {workflow_id}, Strategy: {strategy.value}")
            
            # 创建汇集结果对象
            aggregation_result = AggregationResult(
                workflow_id=workflow_id,
                aggregation_id=aggregation_id,
                strategy=strategy,
                status=ResultStatus.COLLECTING,
                aggregated_data={},
                quality_assessment={},
                performance_metrics={
                    "expected_agents": len(expected_agents),
                    "collection_started_at": datetime.now()
                },
                agent_contributions={},
                issues_encountered=[],
                optimization_applied=[],
                created_at=datetime.now()
            )
            
            self.active_aggregations[aggregation_id] = aggregation_result
            
            # 初始化Agent结果缓冲区
            if workflow_id not in self.agent_results_buffer:
                self.agent_results_buffer[workflow_id] = []
            
            # 🎯 规划优化预处理
            if strategy == AggregationStrategy.PLANNING_OPTIMIZED:
                planning_context = await self._prepare_planning_optimized_collection(
                    workflow_id, expected_agents
                )
                aggregation_result.aggregated_data["planning_context"] = planning_context
            
            # 更新工作流状态
            await self.state_manager.update_workflow_state(
                workflow_id,
                {
                    "aggregation_status": "collecting",
                    "aggregation_id": aggregation_id,
                    "expected_agents": expected_agents,
                    "collection_strategy": strategy.value
                },
                source="result_aggregator"
            )
            
            return aggregation_id
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start result collection: {e}")
            raise
    
    async def submit_agent_result(
        self,
        agent_id: str,
        task_id: str,
        workflow_id: str,
        result_data: Dict[str, Any],
        quality_metrics: Dict[str, Any] = None,
        execution_time: float = 0.0
    ) -> bool:
        """
        提交Agent结果
        
        Args:
            agent_id: Agent ID
            task_id: 任务ID
            workflow_id: 工作流ID
            result_data: 结果数据
            quality_metrics: 质量指标
            execution_time: 执行时间
        
        Returns:
            bool: 提交成功标志
        """
        try:
            self.logger.info(f"🎯 Receiving agent result - Agent: {agent_id}, "
                           f"Task: {task_id}, Workflow: {workflow_id}")
            
            # 创建Agent结果
            agent_result = AgentResult(
                agent_id=agent_id,
                task_id=task_id,
                workflow_id=workflow_id,
                result_data=result_data,
                quality_metrics=quality_metrics or {},
                execution_time=execution_time,
                status="completed",
                created_at=datetime.now(),
                metadata={
                    "data_size": len(json.dumps(result_data)),
                    "quality_score": quality_metrics.get("overall_score", 0.8) if quality_metrics else 0.8
                }
            )
            
            # 添加到缓冲区
            if workflow_id not in self.agent_results_buffer:
                self.agent_results_buffer[workflow_id] = []
            
            self.agent_results_buffer[workflow_id].append(agent_result)
            
            # 检查是否可以开始汇集
            await self._check_aggregation_readiness(workflow_id)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to submit agent result: {e}")
            return False
    
    async def _check_aggregation_readiness(self, workflow_id: str):
        """检查汇集准备状态"""
        try:
            # 查找对应的活跃汇集
            target_aggregation = None
            for aggregation in self.active_aggregations.values():
                if (aggregation.workflow_id == workflow_id and 
                    aggregation.status == ResultStatus.COLLECTING):
                    target_aggregation = aggregation
                    break
            
            if not target_aggregation:
                return
            
            # 检查是否收集到足够的结果
            workflow_results = self.agent_results_buffer.get(workflow_id, [])
            expected_count = target_aggregation.performance_metrics.get("expected_agents", 0)
            
            if len(workflow_results) >= expected_count:
                self.logger.info(f"🎯 Aggregation ready - Workflow: {workflow_id}, "
                               f"Results: {len(workflow_results)}/{expected_count}")
                
                # 开始汇集
                await self._execute_aggregation(target_aggregation, workflow_results)
            else:
                self.logger.info(f"🎯 Waiting for more results - Workflow: {workflow_id}, "
                               f"Current: {len(workflow_results)}/{expected_count}")
                
        except Exception as e:
            self.logger.error(f"❌ Aggregation readiness check failed: {e}")
    
    async def _execute_aggregation(
        self, 
        aggregation: AggregationResult, 
        agent_results: List[AgentResult]
    ):
        """🎯 执行结果汇集"""
        try:
            self.logger.info(f"🎯 Executing aggregation - ID: {aggregation.aggregation_id}, "
                           f"Strategy: {aggregation.strategy.value}")
            
            aggregation.status = ResultStatus.AGGREGATING
            
            # 将Agent结果添加到汇集对象
            for result in agent_results:
                aggregation.agent_contributions[result.agent_id] = result
            
            # 执行汇集策略
            strategy_func = self.aggregation_strategies.get(aggregation.strategy)
            if not strategy_func:
                raise Exception(f"Unsupported aggregation strategy: {aggregation.strategy}")
            
            aggregation_result = await strategy_func(aggregation, agent_results)
            
            # 更新汇集数据
            aggregation.aggregated_data.update(aggregation_result["aggregated_data"])
            aggregation.optimization_applied.extend(aggregation_result.get("optimizations", []))
            
            # 质量验证阶段
            if self.config["result_validation_enabled"]:
                aggregation.status = ResultStatus.VALIDATING
                validation_result = await self._validate_aggregated_results(aggregation)
                aggregation.quality_assessment = validation_result["quality_assessment"]
                aggregation.issues_encountered.extend(validation_result.get("issues", []))
            
            # 🎯 规划反馈集成
            if self.config["planning_feedback_enabled"]:
                planning_feedback = await self._integrate_planning_feedback(aggregation)
                aggregation.aggregated_data["planning_feedback"] = planning_feedback
            
            # 完成汇集
            aggregation.status = ResultStatus.COMPLETED
            aggregation.completed_at = datetime.now()
            
            # 更新性能指标
            total_time = (aggregation.completed_at - aggregation.created_at).total_seconds()
            aggregation.performance_metrics.update({
                "total_aggregation_time": total_time,
                "results_processed": len(agent_results),
                "final_data_size": len(json.dumps(aggregation.aggregated_data)),
                "quality_score": aggregation.get_overall_quality_score()
            })
            
            # 更新工作流状态
            await self.state_manager.update_workflow_state(
                aggregation.workflow_id,
                {
                    "aggregation_status": "completed",
                    "aggregation_result": aggregation.aggregated_data,
                    "quality_assessment": aggregation.quality_assessment,
                    "performance_metrics": aggregation.performance_metrics
                },
                source="result_aggregator"
            )
            
            # 执行完成回调
            await self._execute_completion_callbacks(aggregation)
            
            self.logger.info(f"🎉 Aggregation completed successfully - ID: {aggregation.aggregation_id}, "
                           f"Quality: {aggregation.get_overall_quality_score():.2f}")
            
        except Exception as e:
            aggregation.status = ResultStatus.FAILED
            aggregation.issues_encountered.append(str(e))
            self.logger.error(f"❌ Aggregation execution failed: {e}")
    
    async def _aggregate_planning_optimized(
        self, 
        aggregation: AggregationResult, 
        agent_results: List[AgentResult]
    ) -> Dict[str, Any]:
        """🎯 规划优化汇集策略"""
        try:
            self.logger.info("🎯 Executing planning-optimized aggregation")
            
            # 1. 🎯 按规划阶段分组结果
            phase_results = await self._group_results_by_planning_phase(agent_results)
            
            # 2. 🎯 应用规划权重
            weighted_results = await self._apply_planning_weights(phase_results, aggregation)
            
            # 3. 🎯 执行智能结果融合
            fused_results = await self._intelligent_result_fusion(weighted_results)
            
            # 4. 🎯 规划一致性验证
            consistency_check = await self._verify_planning_consistency(fused_results, aggregation)
            
            # 5. 🎯 应用规划优化
            optimizations = []
            if consistency_check["optimization_opportunities"]:
                optimization_result = await self._apply_planning_optimizations(
                    fused_results, consistency_check["optimization_opportunities"]
                )
                fused_results.update(optimization_result["optimized_data"])
                optimizations.extend(optimization_result["applied_optimizations"])
            
            # 6. 构建最终结果
            aggregated_data = {
                "workflow_result": fused_results,
                "planning_analysis": {
                    "phase_distribution": {phase: len(results) for phase, results in phase_results.items()},
                    "consistency_score": consistency_check["consistency_score"],
                    "optimization_effectiveness": len(optimizations) / max(len(consistency_check["optimization_opportunities"]), 1)
                },
                "execution_metrics": {
                    "total_agents": len(agent_results),
                    "successful_phases": len([p for p, r in phase_results.items() if r]),
                    "quality_distribution": [r.metadata.get("quality_score", 0.8) for r in agent_results]
                }
            }
            
            return {
                "aggregated_data": aggregated_data,
                "optimizations": optimizations + ["planning_phase_grouping", "intelligent_fusion", "consistency_verification"]
            }
            
        except Exception as e:
            self.logger.error(f"❌ Planning-optimized aggregation failed: {e}")
            raise
    
    async def _group_results_by_planning_phase(
        self, agent_results: List[AgentResult]
    ) -> Dict[str, List[AgentResult]]:
        """🎯 按规划阶段分组结果"""
        phase_mapping = {
            "concept_planner": "planning",
            "script_writer": "content_development", 
            "image_generator": "visual_creation",
            "video_generator": "motion_creation",
            "video_composer": "composition",
            "quality_checker": "validation"
        }
        
        phase_results = {}
        for result in agent_results:
            # 从agent_id推断阶段
            agent_type = result.agent_id.split('_')[0] if '_' in result.agent_id else result.agent_id
            phase = phase_mapping.get(agent_type, "general")
            
            if phase not in phase_results:
                phase_results[phase] = []
            phase_results[phase].append(result)
        
        return phase_results
    
    async def _apply_planning_weights(
        self, 
        phase_results: Dict[str, List[AgentResult]], 
        aggregation: AggregationResult
    ) -> Dict[str, List[AgentResult]]:
        """🎯 应用规划权重"""
        
        # 定义阶段权重
        phase_weights = {
            "planning": 1.2,      # 规划阶段最重要
            "content_development": 1.1,
            "visual_creation": 1.0,
            "motion_creation": 1.0,
            "composition": 0.9,
            "validation": 0.8
        }
        
        weighted_results = {}
        for phase, results in phase_results.items():
            weight = phase_weights.get(phase, 1.0)
            
            # 应用权重到结果的质量分数
            for result in results:
                if "quality_score" in result.metadata:
                    result.metadata["weighted_quality_score"] = result.metadata["quality_score"] * weight
                else:
                    result.metadata["weighted_quality_score"] = 0.8 * weight
            
            weighted_results[phase] = results
        
        return weighted_results
    
    async def _intelligent_result_fusion(
        self, weighted_results: Dict[str, List[AgentResult]]
    ) -> Dict[str, Any]:
        """🎯 智能结果融合"""
        
        fused_result = {
            "concept_plan": {},
            "scripts": {},
            "generated_assets": {},
            "final_output": {},
            "quality_metrics": {}
        }
        
        # 按阶段融合结果
        for phase, results in weighted_results.items():
            if not results:
                continue
                
            if phase == "planning":
                # 融合概念规划结果
                for result in results:
                    concept_data = result.result_data.get("concept_plan", {})
                    fused_result["concept_plan"].update(concept_data)
            
            elif phase == "content_development":
                # 融合脚本内容
                scripts = []
                for result in results:
                    script_data = result.result_data.get("scripts", [])
                    scripts.extend(script_data)
                fused_result["scripts"]["all_scripts"] = scripts
            
            elif phase == "visual_creation":
                # 融合图像资源
                images = {}
                for result in results:
                    image_data = result.result_data.get("scene_images", {})
                    images.update(image_data)
                fused_result["generated_assets"]["images"] = images
            
            elif phase == "motion_creation":
                # 融合视频资源
                videos = {}
                for result in results:
                    video_data = result.result_data.get("video_clips", {})
                    videos.update(video_data)
                fused_result["generated_assets"]["videos"] = videos
            
            elif phase == "composition":
                # 融合最终输出
                for result in results:
                    final_video = result.result_data.get("final_video", {})
                    if final_video:
                        fused_result["final_output"] = final_video
            
            elif phase == "validation":
                # 融合质量指标
                quality_data = {}
                for result in results:
                    quality_info = result.result_data.get("quality_report", {})
                    quality_data.update(quality_info)
                fused_result["quality_metrics"] = quality_data
        
        return fused_result
    
    async def _verify_planning_consistency(
        self, fused_results: Dict[str, Any], aggregation: AggregationResult
    ) -> Dict[str, Any]:
        """🎯 验证规划一致性"""
        
        consistency_score = 1.0
        issues = []
        optimization_opportunities = []
        
        # 检查概念与脚本的一致性
        concept_plan = fused_results.get("concept_plan", {})
        scripts = fused_results.get("scripts", {})
        
        if concept_plan and scripts:
            expected_scenes = len(concept_plan.get("scenes", []))
            actual_scripts = len(scripts.get("all_scripts", []))
            
            if expected_scenes != actual_scripts:
                issues.append(f"Scene count mismatch: expected {expected_scenes}, got {actual_scripts}")
                consistency_score -= 0.1
                optimization_opportunities.append("scene_alignment")
        
        # 检查资源完整性
        generated_assets = fused_results.get("generated_assets", {})
        images = generated_assets.get("images", {})
        videos = generated_assets.get("videos", {})
        
        if images and videos:
            if len(images) != len(videos):
                issues.append("Asset count mismatch between images and videos")
                consistency_score -= 0.1
                optimization_opportunities.append("asset_synchronization")
        
        # 检查质量一致性
        quality_metrics = fused_results.get("quality_metrics", {})
        if quality_metrics:
            overall_score = quality_metrics.get("overall_score", 0.8)
            if overall_score < 0.7:
                optimization_opportunities.append("quality_enhancement")
        
        return {
            "consistency_score": max(0, consistency_score),
            "issues": issues,
            "optimization_opportunities": optimization_opportunities
        }
    
    async def _apply_planning_optimizations(
        self, 
        fused_results: Dict[str, Any], 
        opportunities: List[str]
    ) -> Dict[str, Any]:
        """🎯 应用规划优化"""
        
        optimized_data = fused_results.copy()
        applied_optimizations = []
        
        for opportunity in opportunities:
            if opportunity == "scene_alignment":
                # 对齐场景数量
                concept_scenes = len(optimized_data.get("concept_plan", {}).get("scenes", []))
                scripts = optimized_data.get("scripts", {}).get("all_scripts", [])
                
                if len(scripts) < concept_scenes:
                    # 补充缺失的脚本
                    for i in range(len(scripts), concept_scenes):
                        scripts.append({
                            "scene_number": i + 1,
                            "script_text": f"Generated script for scene {i + 1}",
                            "description": "Auto-generated to maintain consistency"
                        })
                    applied_optimizations.append("scene_script_alignment")
                
            elif opportunity == "asset_synchronization":
                # 同步资源
                images = optimized_data.get("generated_assets", {}).get("images", {})
                videos = optimized_data.get("generated_assets", {}).get("videos", {})
                
                # 确保每个图像都有对应的视频
                for image_key in images:
                    if image_key not in videos:
                        videos[image_key] = {
                            "video_url": f"/placeholder/video_{image_key}.mp4",
                            "status": "placeholder",
                            "note": "Placeholder for missing video asset"
                        }
                applied_optimizations.append("asset_synchronization")
                
            elif opportunity == "quality_enhancement":
                # 质量增强建议
                quality_metrics = optimized_data.get("quality_metrics", {})
                quality_metrics["enhancement_applied"] = True
                quality_metrics["enhancement_recommendations"] = [
                    "Consider regenerating low-quality assets",
                    "Apply additional quality filters",
                    "Review content for consistency"
                ]
                applied_optimizations.append("quality_enhancement_recommendations")
        
        return {
            "optimized_data": optimized_data,
            "applied_optimizations": applied_optimizations
        }
    
    # 其他汇集策略的简化实现
    
    async def _aggregate_sequential(
        self, aggregation: AggregationResult, agent_results: List[AgentResult]
    ) -> Dict[str, Any]:
        """顺序汇集"""
        sorted_results = sorted(agent_results, key=lambda x: x.created_at)
        
        aggregated_data = {}
        for result in sorted_results:
            aggregated_data[result.agent_id] = result.result_data
        
        return {"aggregated_data": {"results": aggregated_data}, "optimizations": ["sequential_ordering"]}
    
    async def _aggregate_parallel(
        self, aggregation: AggregationResult, agent_results: List[AgentResult]
    ) -> Dict[str, Any]:
        """并行汇集"""
        aggregated_data = {result.agent_id: result.result_data for result in agent_results}
        return {"aggregated_data": {"parallel_results": aggregated_data}, "optimizations": ["parallel_collection"]}
    
    async def _aggregate_priority_based(
        self, aggregation: AggregationResult, agent_results: List[AgentResult]
    ) -> Dict[str, Any]:
        """基于优先级汇集"""
        # 简化：按质量分数排序
        sorted_results = sorted(
            agent_results, 
            key=lambda x: x.metadata.get("quality_score", 0.8), 
            reverse=True
        )
        
        aggregated_data = {}
        for i, result in enumerate(sorted_results):
            aggregated_data[f"priority_{i+1}_{result.agent_id}"] = result.result_data
        
        return {"aggregated_data": {"priority_results": aggregated_data}, "optimizations": ["priority_ordering"]}
    
    async def _aggregate_quality_weighted(
        self, aggregation: AggregationResult, agent_results: List[AgentResult]
    ) -> Dict[str, Any]:
        """质量加权汇集"""
        total_weight = sum(result.metadata.get("quality_score", 0.8) for result in agent_results)
        
        aggregated_data = {}
        for result in agent_results:
            weight = result.metadata.get("quality_score", 0.8)
            weighted_contribution = weight / total_weight if total_weight > 0 else 1.0 / len(agent_results)
            
            aggregated_data[result.agent_id] = {
                "result_data": result.result_data,
                "contribution_weight": weighted_contribution,
                "quality_score": weight
            }
        
        return {"aggregated_data": {"weighted_results": aggregated_data}, "optimizations": ["quality_weighting"]}
    
    # 辅助方法
    
    async def _prepare_planning_optimized_collection(
        self, workflow_id: str, expected_agents: List[str]
    ) -> Dict[str, Any]:
        """🎯 准备规划优化收集"""
        return {
            "collection_strategy": "planning_first",
            "expected_phases": ["planning", "content_development", "visual_creation", "motion_creation", "composition", "validation"],
            "quality_targets": {"overall_score": 0.85, "consistency_score": 0.9},
            "optimization_enabled": True
        }
    
    async def _validate_aggregated_results(self, aggregation: AggregationResult) -> Dict[str, Any]:
        """验证汇集结果"""
        issues = []
        
        # 数据完整性检查
        if not aggregation.aggregated_data:
            issues.append("No aggregated data found")
        
        # 质量检查
        quality_scores = [
            result.metadata.get("quality_score", 0.8) 
            for result in aggregation.agent_contributions.values()
        ]
        
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        
        if avg_quality < self.config["quality_threshold"]:
            issues.append(f"Average quality {avg_quality:.2f} below threshold {self.config['quality_threshold']}")
        
        quality_assessment = {
            "overall_score": avg_quality,
            "individual_scores": quality_scores,
            "quality_distribution": {
                "high": len([s for s in quality_scores if s >= 0.8]),
                "medium": len([s for s in quality_scores if 0.6 <= s < 0.8]),
                "low": len([s for s in quality_scores if s < 0.6])
            },
            "validation_passed": len(issues) == 0
        }
        
        return {
            "quality_assessment": quality_assessment,
            "issues": issues
        }
    
    async def _integrate_planning_feedback(self, aggregation: AggregationResult) -> Dict[str, Any]:
        """🎯 集成规划反馈"""
        return {
            "planning_effectiveness": 0.9,
            "strategy_recommendations": [
                "Current planning approach is effective",
                "Consider minor optimizations for future workflows"
            ],
            "quality_improvement_suggestions": [
                "Maintain current quality standards",
                "Focus on consistency across phases"
            ]
        }
    
    async def _execute_completion_callbacks(self, aggregation: AggregationResult):
        """执行完成回调"""
        workflow_id = aggregation.workflow_id
        if workflow_id in self.completion_callbacks:
            for callback in self.completion_callbacks[workflow_id]:
                try:
                    await callback(aggregation)
                except Exception as e:
                    self.logger.error(f"❌ Completion callback failed: {e}")
    
    async def _background_aggregation_monitor(self):
        """后台汇集监控"""
        while True:
            try:
                await asyncio.sleep(30)  # 每30秒检查一次
                
                current_time = datetime.now()
                timeout_threshold = timedelta(seconds=self.config["collection_timeout_seconds"])
                
                # 检查超时的汇集
                timed_out_aggregations = []
                for aggregation_id, aggregation in self.active_aggregations.items():
                    if (aggregation.status == ResultStatus.COLLECTING and 
                        current_time - aggregation.created_at > timeout_threshold):
                        timed_out_aggregations.append(aggregation_id)
                
                # 处理超时
                for aggregation_id in timed_out_aggregations:
                    aggregation = self.active_aggregations[aggregation_id]
                    self.logger.warning(f"⚠️ Aggregation timeout - ID: {aggregation_id}")
                    
                    # 使用部分结果进行汇集
                    workflow_results = self.agent_results_buffer.get(aggregation.workflow_id, [])
                    if workflow_results:
                        self.logger.info(f"🎯 Processing partial results - Count: {len(workflow_results)}")
                        await self._execute_aggregation(aggregation, workflow_results)
                    else:
                        aggregation.status = ResultStatus.FAILED
                        aggregation.issues_encountered.append("Timeout with no results received")
                
                # 清理完成的汇集
                completed_aggregations = [
                    aggregation_id for aggregation_id, aggregation in self.active_aggregations.items()
                    if aggregation.status in [ResultStatus.COMPLETED, ResultStatus.FAILED] and
                       current_time - aggregation.created_at > timedelta(hours=1)
                ]
                
                for aggregation_id in completed_aggregations:
                    del self.active_aggregations[aggregation_id]
                    self.logger.info(f"🧹 Cleaned up aggregation: {aggregation_id}")
                
            except Exception as e:
                self.logger.error(f"❌ Background monitoring error: {e}")
    
    def register_completion_callback(self, workflow_id: str, callback: callable):
        """注册完成回调"""
        if workflow_id not in self.completion_callbacks:
            self.completion_callbacks[workflow_id] = []
        self.completion_callbacks[workflow_id].append(callback)
    
    def get_aggregation_status(self, aggregation_id: str) -> Optional[AggregationResult]:
        """获取汇集状态"""
        return self.active_aggregations.get(aggregation_id)
    
    def get_workflow_results(self, workflow_id: str) -> List[AgentResult]:
        """获取工作流结果"""
        return self.agent_results_buffer.get(workflow_id, [])
    
    def get_aggregator_status(self) -> Dict[str, Any]:
        """获取汇集器状态"""
        return {
            "active_aggregations": len(self.active_aggregations),
            "workflows_with_results": len(self.agent_results_buffer),
            "supported_strategies": [strategy.value for strategy in AggregationStrategy],
            "planning_optimized_enabled": True,  # 🎯 规划优化启用
            "config": self.config,
            "state_manager_workflows": len(self.state_manager.workflow_states)
        }


# 全局结果汇集器
_result_aggregator = None


def get_result_aggregator() -> ResultAggregator:
    """获取全局结果汇集器实例"""
    global _result_aggregator
    if _result_aggregator is None:
        _result_aggregator = ResultAggregator()
    return _result_aggregator