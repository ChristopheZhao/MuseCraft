"""
Enhanced Orchestrator Agent with Advanced Features:
- Intelligent workflow optimization and parallel execution
- Advanced error handling and recovery mechanisms
- Comprehensive monitoring and cost optimization
- Quality control integration
- Real-time performance analytics
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, TaskStatus, AgentType
from ..events.publisher import publish_state_event
from .concept_planner import ConceptPlannerAgent
from .script_writer import ScriptWriterAgent
from .image_generator import ImageGeneratorAgent
from .video_generator import VideoGeneratorAgent
from .video_composer import VideoComposerAgent
from .quality_checker import QualityCheckerAgent

# Import optimization services
from ..services.workflow_optimizer import workflow_optimizer, ExecutionStrategy, OptimizationLevel
from ..services.monitoring_service import monitoring_service
from ..services.quality_control import quality_control_service, ContentType
from ..services.enhanced_ai_client import enhanced_ai_client
from ..services.memory_provider import build_memory_services, MemoryServices


class EnhancedOrchestratorAgent(BaseAgent):
    """
    Enhanced Orchestrator Agent with intelligent workflow optimization,
    advanced error handling, and comprehensive monitoring
    """
    
    def __init__(self, memory_services: Optional[MemoryServices] = None):
        if memory_services is None:
            memory_services = build_memory_services()
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="enhanced_orchestrator",
            timeout_seconds=3600,  # 1 hour for complex workflows
            max_retries=2,
            memory_services=memory_services,
        )
        
        # Initialize specialized agents
        self.agents = {
            AgentType.CONCEPT_PLANNER: ConceptPlannerAgent(memory_services=memory_services),
            AgentType.SCRIPT_WRITER: ScriptWriterAgent(memory_services=memory_services),
            AgentType.IMAGE_GENERATOR: ImageGeneratorAgent(memory_services=memory_services),
            AgentType.VIDEO_GENERATOR: VideoGeneratorAgent(memory_services=memory_services),
            AgentType.VIDEO_COMPOSER: VideoComposerAgent(memory_services=memory_services),
            AgentType.QUALITY_CHECKER: QualityCheckerAgent(memory_services=memory_services),
        }
        
        # Configuration
        self.optimization_level = OptimizationLevel.BALANCED
        self.execution_strategy = ExecutionStrategy.ADAPTIVE
        self.enable_quality_control = True
        self.enable_cost_optimization = True
        
        # Performance tracking
        self.execution_metrics = {}
        
        # Recovery mechanisms
        self.recovery_strategies = self._initialize_recovery_strategies()
    
    def _initialize_recovery_strategies(self) -> Dict[AgentType, List[str]]:
        """Initialize recovery strategies for each agent type"""
        return {
            AgentType.CONCEPT_PLANNER: [
                "retry_with_simplified_prompt",
                "use_fallback_template",
                "reduce_complexity"
            ],
            AgentType.SCRIPT_WRITER: [
                "retry_with_different_model",
                "use_template_based_generation",
                "break_into_smaller_chunks"
            ],
            AgentType.IMAGE_GENERATOR: [
                "retry_with_different_provider",
                "simplify_prompt",
                "reduce_quality_requirements",
                "use_cached_similar_image"
            ],
            AgentType.VIDEO_GENERATOR: [
                "retry_with_shorter_duration",
                "use_different_provider",
                "fallback_to_slideshow",
                "reduce_quality_settings"
            ],
            AgentType.VIDEO_COMPOSER: [
                "retry_with_simpler_composition",
                "use_basic_transitions",
                "reduce_effects"
            ],
            AgentType.QUALITY_CHECKER: [
                "use_basic_validation",
                "skip_advanced_checks",
                "manual_review_required"
            ]
        }
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        db: Session
    ) -> Dict[str, Any]:
        """Execute the enhanced workflow with optimization and monitoring"""
        
        self.logger.info(f"Starting enhanced workflow for task {task.task_id}")
        start_time = time.time()
        
        # Record task start
        await monitoring_service.record_task_start(task)
        
        try:
            # Create optimized execution plan
            execution_plan = await workflow_optimizer.create_execution_plan(
                task=task,
                input_data=input_data,
                strategy=self.execution_strategy,
                optimization_level=self.optimization_level
            )
            
            self.logger.info(f"Execution plan created: {len(execution_plan.execution_groups)} groups, "
                           f"estimated time: {execution_plan.estimated_total_time:.1f}s")
            
            # Update task with execution plan info
            task.update_progress("Execution plan created", 5)
            task.estimated_duration = int(execution_plan.estimated_total_time)
            db.commit()
            
            # Execute workflow with optimization
            workflow_result = await workflow_optimizer.execute_workflow_optimized(
                task=task,
                input_data=input_data,
                execution_plan=execution_plan,
                agents=self.agents,
                db=db
            )
            
            # Perform comprehensive quality control if enabled
            if self.enable_quality_control:
                await self._perform_comprehensive_quality_control(
                    task, workflow_result, db
                )
            
            # Record successful completion
            total_duration = time.time() - start_time
            await monitoring_service.record_task_completion(task, total_duration)
            
            # Generate cost analysis
            if self.enable_cost_optimization:
                cost_analysis = await self._generate_cost_analysis(task, workflow_result, db)
                workflow_result["cost_analysis"] = cost_analysis
            
            # Add performance insights
            workflow_result["performance_insights"] = await self._generate_performance_insights(
                task, execution_plan, total_duration
            )
            
            # Send completion notification with enhanced data
            await self._send_enhanced_completion_notification(task, workflow_result)
            
            self.logger.info(f"Enhanced workflow completed successfully in {total_duration:.1f}s")
            
            return workflow_result
            
        except Exception as e:
            # Enhanced error handling and recovery
            error_msg = f"Enhanced workflow failed: {str(e)}"
            
            # Record failure
            total_duration = time.time() - start_time
            await monitoring_service.record_task_completion(task, total_duration)
            
            # Try recovery if possible
            recovery_result = await self._attempt_workflow_recovery(task, input_data, str(e), db)
            
            if recovery_result:
                self.logger.info("Workflow recovery successful")
                return recovery_result
            
            # Final failure
            task.status = TaskStatus.FAILED
            task.add_error(error_msg)
            db.commit()
            
            await self._send_enhanced_failure_notification(task, error_msg)
            
            raise AgentError(error_msg) from e
    
    async def _perform_comprehensive_quality_control(
        self,
        task: Task,
        workflow_result: Dict[str, Any],
        db: Session
    ):
        """Perform comprehensive quality control on all generated content"""
        
        self.logger.info("Starting comprehensive quality control")
        
        # Prepare content for quality control
        content_batch = []
        
        # Add concept plan for text quality control
        if "concept_planner" in workflow_result:
            concept_data = workflow_result["concept_planner"]
            content_batch.append((concept_data, ContentType.TEXT))
        
        # Add script for text quality control
        if "script_writer" in workflow_result:
            script_data = workflow_result["script_writer"]
            content_batch.append((script_data, ContentType.TEXT))
        
        # Add images for quality control
        if "image_generator" in workflow_result:
            image_data = workflow_result["image_generator"]
            for image_info in image_data.get("images", []):
                if not image_info.get("is_placeholder"):
                    content_batch.append((image_info, ContentType.IMAGE))
        
        # Add videos for quality control
        if "video_generator" in workflow_result:
            video_data = workflow_result["video_generator"]
            for video_info in video_data.get("videos", []):
                content_batch.append((video_info, ContentType.VIDEO))
        
        # Perform batch quality control
        if content_batch:
            quality_results = await quality_control_service.batch_quality_control(
                task, content_batch, db
            )
            
            # Add quality control results to workflow result
            workflow_result["quality_control"] = {
                "results": quality_results,
                "summary": quality_control_service.get_quality_summary(quality_results)
            }
            
            # Check if any content failed quality control
            failed_items = [r for r in quality_results if not r.approved]
            review_items = [r for r in quality_results if r.requires_human_review]
            
            if failed_items:
                self.logger.warning(f"{len(failed_items)} items failed quality control")
                # Mark task for review
                task.requires_human_review = True
                db.commit()
            
            if review_items:
                self.logger.info(f"{len(review_items)} items require human review")
                task.requires_human_review = True
                db.commit()
        
        self.logger.info("Quality control completed")
    
    async def _generate_cost_analysis(
        self,
        task: Task,
        workflow_result: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """Generate comprehensive cost analysis"""
        
        # Get cost data from monitoring service
        cost_analysis = await monitoring_service.get_cost_analysis(db, days=1)
        
        # Calculate workflow-specific costs
        workflow_cost = 0.0
        cost_breakdown = {}
        
        # Aggregate costs from agent executions
        for agent_type, agent_result in workflow_result.get("results", {}).items():
            if isinstance(agent_result, dict) and "cost" in agent_result:
                agent_cost = agent_result["cost"]
                workflow_cost += agent_cost
                cost_breakdown[agent_type] = agent_cost
        
        # Get AI service costs
        ai_service_metrics = enhanced_ai_client.get_performance_metrics()
        service_costs = {}
        for provider, metrics in ai_service_metrics["providers"].items():
            service_costs[provider] = metrics.get("total_cost", 0)
        
        # Generate cost optimization recommendations
        recommendations = []
        
        # Check for expensive operations
        if workflow_cost > 2.0:  # $2 threshold
            recommendations.append({
                "type": "high_cost",
                "message": f"Workflow cost is ${workflow_cost:.2f}",
                "recommendation": "Consider using caching or lower-cost providers"
            })
        
        # Check cache effectiveness
        cache_stats = ai_service_metrics.get("cache_stats", {})
        if cache_stats.get("total_cache_cost_saved", 0) > 0:
            recommendations.append({
                "type": "caching_effective",
                "message": f"Caching saved ${cache_stats['total_cache_cost_saved']:.2f}",
                "recommendation": "Continue current caching strategy"
            })
        
        return {
            "workflow_cost": workflow_cost,
            "cost_breakdown": cost_breakdown,
            "service_costs": service_costs,
            "recommendations": recommendations,
            "estimated_monthly_cost": workflow_cost * 30  # Rough estimate
        }
    
    async def _generate_performance_insights(
        self,
        task: Task,
        execution_plan,
        actual_duration: float
    ) -> Dict[str, Any]:
        """Generate performance insights and recommendations"""
        
        insights = {
            "execution_time": {
                "estimated": execution_plan.estimated_total_time,
                "actual": actual_duration,
                "efficiency": execution_plan.estimated_total_time / actual_duration if actual_duration > 0 else 0
            },
            "optimization_effectiveness": {},
            "recommendations": []
        }
        
        # Analyze execution efficiency
        if actual_duration > execution_plan.estimated_total_time * 1.5:
            insights["recommendations"].append({
                "type": "performance",
                "message": "Execution took longer than estimated",
                "recommendation": "Consider reviewing resource allocation or optimization strategy"
            })
        elif actual_duration < execution_plan.estimated_total_time * 0.8:
            insights["recommendations"].append({
                "type": "performance",
                "message": "Execution was faster than estimated",
                "recommendation": "Optimization strategies are working well"
            })
        
        # Get optimization recommendations from workflow optimizer
        task_signature = workflow_optimizer._generate_task_signature(task, task.input_parameters)
        optimizer_recommendations = workflow_optimizer.get_optimization_recommendations(task_signature)
        
        if optimizer_recommendations:
            insights["recommendations"].extend(optimizer_recommendations)
        
        return insights
    
    async def _attempt_workflow_recovery(
        self,
        task: Task,
        input_data: Dict[str, Any],
        error_message: str,
        db: Session
    ) -> Optional[Dict[str, Any]]:
        """Attempt to recover from workflow failure"""
        
        self.logger.info(f"Attempting workflow recovery for error: {error_message}")
        
        # Analyze the error to determine recovery strategy
        recovery_strategy = await self._analyze_error_and_select_recovery(error_message, task, db)
        
        if not recovery_strategy:
            self.logger.warning("No suitable recovery strategy found")
            return None
        
        try:
            # Apply recovery strategy
            self.logger.info(f"Applying recovery strategy: {recovery_strategy['type']}")
            
            if recovery_strategy["type"] == "reduce_quality":
                # Reduce quality requirements and retry
                modified_input = input_data.copy()
                modified_input["quality_level"] = "standard"
                modified_input["optimization_level"] = "conservative"
                
                # Create conservative execution plan
                execution_plan = await workflow_optimizer.create_execution_plan(
                    task=task,
                    input_data=modified_input,
                    strategy=ExecutionStrategy.SEQUENTIAL,
                    optimization_level=OptimizationLevel.CONSERVATIVE
                )
                
                # Execute with reduced requirements
                return await workflow_optimizer.execute_workflow_optimized(
                    task=task,
                    input_data=modified_input,
                    execution_plan=execution_plan,
                    agents=self.agents,
                    db=db
                )
            
            elif recovery_strategy["type"] == "partial_execution":
                # Execute only essential agents
                essential_agents = [AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER]
                
                # Execute essential workflow
                return await self._execute_partial_workflow(task, input_data, essential_agents, db)
            
            elif recovery_strategy["type"] == "fallback_providers":
                # Switch to fallback AI providers
                # This would be handled by the enhanced AI client automatically
                return await self._retry_with_fallback_providers(task, input_data, db)
            
        except Exception as recovery_error:
            self.logger.error(f"Recovery attempt failed: {str(recovery_error)}")
            return None
        
        return None
    
    async def _analyze_error_and_select_recovery(
        self,
        error_message: str,
        task: Task,
        db: Session
    ) -> Optional[Dict[str, Any]]:
        """Analyze error and select appropriate recovery strategy"""
        
        error_lower = error_message.lower()
        
        # API rate limit or quota errors
        if any(keyword in error_lower for keyword in ["rate limit", "quota", "timeout"]):
            return {
                "type": "fallback_providers",
                "description": "Switch to alternative AI providers"
            }
        
        # Resource or quality issues
        if any(keyword in error_lower for keyword in ["memory", "resource", "quality"]):
            return {
                "type": "reduce_quality",
                "description": "Reduce quality requirements and resource usage"
            }
        
        # Partial failures
        if any(keyword in error_lower for keyword in ["generation failed", "partial"]):
            return {
                "type": "partial_execution",
                "description": "Execute essential components only"
            }
        
        # Check historical failures for this task type
        similar_tasks = db.query(Task).filter(
            Task.task_type == task.task_type,
            Task.status == TaskStatus.FAILED
        ).limit(5).all()
        
        if len(similar_tasks) >= 3:
            # Many similar failures - use conservative approach
            return {
                "type": "reduce_quality",
                "description": "Use conservative settings due to historical failures"
            }
        
        return None
    
    async def _execute_partial_workflow(
        self,
        task: Task,
        input_data: Dict[str, Any],
        agent_types: List[AgentType],
        db: Session
    ) -> Dict[str, Any]:
        """Execute partial workflow with only specified agents"""
        
        self.logger.info(f"Executing partial workflow with agents: {[a.value for a in agent_types]}")
        
        workflow_data = input_data.copy()
        workflow_results = {}
        
        for i, agent_type in enumerate(agent_types):
            agent = self.agents[agent_type]
            
            # Update progress
            progress = int((i / len(agent_types)) * 80) + 10
            task.update_progress(f"Executing {agent.agent_name} (recovery mode)", progress)
            db.commit()
            
            try:
                # Execute agent
                agent_result = await agent.execute(
                    task=task,
                    input_data=workflow_data,
                    db=db,
                    execution_order=i + 1
                )
                
                workflow_results[agent_type.value] = agent_result
                workflow_data.update(agent_result)
                
            except Exception as e:
                self.logger.error(f"Partial workflow failed at {agent_type.value}: {str(e)}")
                raise
        
        # Mark as partially completed
        task.status = TaskStatus.COMPLETED
        task.update_progress("Partial workflow completed", 90)
        db.commit()
        
        return {
            "workflow_status": "partially_completed",
            "results": workflow_results,
            "note": "Workflow completed with reduced functionality due to recovery mode"
        }
    
    async def _retry_with_fallback_providers(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """Retry workflow with fallback AI providers"""
        
        self.logger.info("Retrying workflow with fallback providers")
        
        # The enhanced AI client should automatically handle provider fallbacks
        # We just need to retry with a conservative execution plan
        
        execution_plan = await workflow_optimizer.create_execution_plan(
            task=task,
            input_data=input_data,
            strategy=ExecutionStrategy.SEQUENTIAL,
            optimization_level=OptimizationLevel.CONSERVATIVE
        )
        
        return await workflow_optimizer.execute_workflow_optimized(
            task=task,
            input_data=input_data,
            execution_plan=execution_plan,
            agents=self.agents,
            db=db
        )
    
    async def _send_enhanced_completion_notification(
        self,
        task: Task,
        workflow_result: Dict[str, Any]
    ):
        """Send enhanced completion notification with detailed metrics"""
        
        try:
            # Get performance metrics
            # Note: This would require a db session, simplified for now
            
            await publish_state_event(
                status="completed",
                extra_payload={
                    "state": "enhanced_workflow_completed",
                    "results": workflow_result.get("results", {}),
                    "performance_metrics": workflow_result.get("execution_metrics", {}),
                    "quality_control": workflow_result.get("quality_control", {}),
                    "cost_analysis": workflow_result.get("cost_analysis", {}),
                    "performance_insights": workflow_result.get("performance_insights", {}),
                    "final_video_url": workflow_result.get("final_video_url"),
                    "quality_score": workflow_result.get("quality_score"),
                },
                task_id=str(task.task_id),
                task_db_id=getattr(task, "id", None),
                workflow_state_id=str(task.task_id),
                agent_type=self.agent_type.value,
                agent_name=self.agent_name,
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to send enhanced completion notification: {e}")
    
    async def _send_enhanced_failure_notification(
        self,
        task: Task,
        error_message: str
    ):
        """Send enhanced failure notification with diagnostic information"""
        
        try:
            # Get system health for diagnostics
            health_status = await monitoring_service.health_check()
            
            await publish_state_event(
                status="failed",
                extra_payload={
                    "state": "enhanced_workflow_failed",
                    "error": error_message,
                    "system_health": health_status,
                    "recovery_attempted": True,
                    "support_info": {
                        "error_id": f"error_{int(time.time())}",
                        "task_type": getattr(task.task_type, "value", str(task.task_type)),
                        "timestamp": int(time.time())
                    }
                },
                task_id=str(task.task_id),
                task_db_id=getattr(task, "id", None),
                workflow_state_id=str(task.task_id),
                agent_type=self.agent_type.value,
                agent_name=self.agent_name,
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to send enhanced failure notification: {e}")
    
    def configure_optimization(
        self,
        execution_strategy: ExecutionStrategy = None,
        optimization_level: OptimizationLevel = None,
        enable_quality_control: bool = None,
        enable_cost_optimization: bool = None
    ):
        """Configure optimization settings"""
        
        if execution_strategy is not None:
            self.execution_strategy = execution_strategy
        
        if optimization_level is not None:
            self.optimization_level = optimization_level
        
        if enable_quality_control is not None:
            self.enable_quality_control = enable_quality_control
        
        if enable_cost_optimization is not None:
            self.enable_cost_optimization = enable_cost_optimization
        
        self.logger.info(f"Optimization configured: strategy={self.execution_strategy.value}, "
                        f"level={self.optimization_level.value}, "
                        f"quality_control={self.enable_quality_control}, "
                        f"cost_optimization={self.enable_cost_optimization}")
    
    async def get_workflow_analytics(self, task: Task, db: Session) -> Dict[str, Any]:
        """Get comprehensive workflow analytics"""
        
        # Get basic workflow status
        workflow_status = self.get_workflow_status(task, db)
        
        # Get performance insights
        performance_insights = await monitoring_service.generate_performance_insights(db)
        
        # Get cost analysis
        cost_analysis = await monitoring_service.get_cost_analysis(db, days=7)
        
        # Get AI service health
        ai_health = await enhanced_ai_client.health_check()
        
        return {
            "workflow_status": workflow_status,
            "performance_insights": [insight.__dict__ for insight in performance_insights],
            "cost_analysis": cost_analysis,
            "ai_service_health": ai_health,
            "optimization_recommendations": workflow_optimizer.get_optimization_recommendations(
                workflow_optimizer._generate_task_signature(task, task.input_parameters)
            ),
            "timestamp": int(time.time())
        }
