"""
Archived: Supervisor Orchestrator (experimental)

This module is archived and must not be imported in production paths.
It remains in the repo for reference only.
"""

raise ImportError(
    "Archived module 'supervisor_orchestrator'. Do not import in production."
)

import asyncio
import os
import logging
import time
from typing import Dict, Any, List, Optional, Union
from enum import Enum
from dataclasses import dataclass
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, TaskStatus, AgentType
from ..services.ai_client import AIClient
from ..services.context_assembler import context_assembler
from ..services.memory_writer import memory_writer


class ExecutionStrategy(Enum):
    """执行策略类型"""
    PIPELINE = "pipeline"           # 串行执行
    PARALLEL = "parallel"           # 并行执行
    COLLABORATIVE = "collaborative" # 协作执行
    ADAPTIVE = "adaptive"           # 自适应执行


class CollaborationType(Enum):
    """协作类型"""
    PEER_REVIEW = "peer_review"                     # 同行评议
    ITERATIVE_REFINEMENT = "iterative_refinement"  # 迭代优化
    CONSENSUS_BUILDING = "consensus_building"       # 共识构建
    EXPERT_CONSULTATION = "expert_consultation"     # 专家咨询


@dataclass
class WorkflowPlan:
    """工作流计划"""
    strategy: ExecutionStrategy
    agent_sequence: List[AgentType]
    collaboration_sessions: List[Dict[str, Any]]
    estimated_duration: float
    quality_target: float
    cost_estimate: float


@dataclass
class CollaborationSession:
    """协作会话"""
    session_id: str
    type: CollaborationType
    participants: List[str]
    objectives: List[str]
    max_iterations: int
    convergence_criteria: Dict[str, Any]
    current_iteration: int = 0
    status: str = "pending"


class SupervisorOrchestrator(BaseAgent):
    """
    智能监督者编排器
    
    职责：
    1. 分析任务复杂度和需求
    2. 选择最优执行策略 
    3. 协调Agent间协作
    4. 监控执行质量和进度
    5. 处理冲突和异常情况
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="supervisor_orchestrator",
            timeout_seconds=3600,
            tools=[
                "workflow_analyzer", "strategy_selector", "agent_coordinator",
                "quality_monitor", "conflict_resolver"
            ]
        )
        
        self.ai_client = AIClient()
        
        # 执行策略映射
        self.strategy_handlers = {
            ExecutionStrategy.PIPELINE: self._execute_pipeline_strategy,
            ExecutionStrategy.PARALLEL: self._execute_parallel_strategy,
            ExecutionStrategy.COLLABORATIVE: self._execute_collaborative_strategy,
            ExecutionStrategy.ADAPTIVE: self._execute_adaptive_strategy
        }
        
        # Agent能力映射
        self.agent_capabilities = {
            AgentType.CONCEPT_PLANNER: ["creative_planning", "narrative_design"],
            AgentType.SCRIPT_WRITER: ["script_generation", "dialogue_creation"],
            AgentType.IMAGE_GENERATOR: ["visual_creation", "style_consistency"],
            AgentType.VIDEO_GENERATOR: ["motion_synthesis", "scene_composition"],
            AgentType.VIDEO_COMPOSER: ["video_editing", "transition_effects"],
            AgentType.QUALITY_CHECKER: ["quality_assessment", "content_validation"]
        }
        
        # 协作模式配置
        self.collaboration_configs = {
            CollaborationType.PEER_REVIEW: {
                "min_reviewers": 1,
                "consensus_threshold": 0.8,
                "max_review_cycles": 2
            },
            CollaborationType.ITERATIVE_REFINEMENT: {
                "max_iterations": 3,
                "improvement_threshold": 0.1,
                "quality_target": 8.0
            }
        }
    
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """执行监督编排流程"""
        
        start_time = time.time()
        self.logger.info(f"Starting supervised workflow for task {task.task_id}")
        
        try:
            # 1. 分析任务和创建工作流计划
            workflow_plan = await self._create_workflow_plan(task, input_data)
            
            self.logger.info(f"Workflow plan created: strategy={workflow_plan.strategy.value}, "
                           f"agents={len(workflow_plan.agent_sequence)}, "
                           f"collaborations={len(workflow_plan.collaboration_sessions)}")
            
            # 2. 执行工作流计划
            execution_result = await self._execute_workflow_plan(
                workflow_plan, task, input_data, db
            )
            
            # 3. 质量评估和优化
            quality_result = await self._perform_quality_assessment(
                execution_result, workflow_plan, task
            )
            
            # 4. 生成执行报告
            execution_report = await self._generate_execution_report(
                workflow_plan, execution_result, quality_result, time.time() - start_time
            )
            
            # 5. 更新任务状态
            task.status = TaskStatus.COMPLETED
            task.update_progress("Supervised workflow completed", 100)
            db.commit()
            
            return {
                "workflow_plan": workflow_plan.__dict__,
                "execution_result": execution_result,
                "quality_assessment": quality_result,
                "execution_report": execution_report,
                "total_duration": time.time() - start_time
            }
            
        except Exception as e:
            error_msg = f"Supervised workflow failed: {str(e)}"
            task.status = TaskStatus.FAILED
            task.add_error(error_msg)
            db.commit()
            
            self.logger.error(error_msg, exc_info=True)
            raise AgentError(error_msg) from e
    
    async def _create_workflow_plan(
        self,
        task: Task,
        input_data: Dict[str, Any]
    ) -> WorkflowPlan:
        """创建工作流计划"""
        
        # 分析任务复杂度
        complexity_analysis = await self._analyze_task_complexity(input_data)
        
        # 选择执行策略
        strategy = await self._select_execution_strategy(complexity_analysis, input_data)
        
        # 确定Agent序列
        agent_sequence = await self._determine_agent_sequence(strategy, complexity_analysis)
        
        # 规划协作会话
        collaboration_sessions = await self._plan_collaboration_sessions(
            strategy, agent_sequence, complexity_analysis
        )
        
        # 估算时间和成本
        duration_estimate = await self._estimate_execution_duration(
            strategy, agent_sequence, collaboration_sessions
        )
        
        cost_estimate = await self._estimate_execution_cost(
            agent_sequence, collaboration_sessions
        )
        
        return WorkflowPlan(
            strategy=strategy,
            agent_sequence=agent_sequence,
            collaboration_sessions=collaboration_sessions,
            estimated_duration=duration_estimate,
            quality_target=complexity_analysis.get("quality_target", 8.0),
            cost_estimate=cost_estimate
        )
    
    async def _analyze_task_complexity(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析任务复杂度"""
        
        complexity_prompt = self.render_prompt(
            "supervisor_orchestrator/complexity_analysis",
            **{
                "user_prompt": input_data.get("user_prompt", ""),
                "requirements": input_data.get("requirements", {}),
                "constraints": input_data.get("constraints", {}),
                "quality_expectations": input_data.get("quality_level", "standard")
            }
        )
        
        try:
            response = await self.ai_client.generate_text(
                prompt=complexity_prompt,
                model="gpt-4",
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            return self._parse_complexity_analysis(response["content"])
            
        except Exception as e:
            self.logger.warning(f"Complexity analysis failed, using fallback: {e}")
            return self._get_fallback_complexity_analysis(input_data)
    
    async def _select_execution_strategy(
        self,
        complexity_analysis: Dict[str, Any],
        input_data: Dict[str, Any]
    ) -> ExecutionStrategy:
        """选择执行策略"""
        
        complexity_score = complexity_analysis.get("complexity_score", 5.0)
        quality_requirements = complexity_analysis.get("quality_requirements", "standard")
        collaboration_needs = complexity_analysis.get("collaboration_needs", False)
        
        # 策略选择逻辑
        if collaboration_needs or complexity_score >= 8.0:
            return ExecutionStrategy.COLLABORATIVE
        elif complexity_score >= 6.0 and quality_requirements == "high":
            return ExecutionStrategy.PARALLEL
        elif complexity_score >= 7.0:
            return ExecutionStrategy.ADAPTIVE
        else:
            return ExecutionStrategy.PIPELINE
    
    async def _execute_workflow_plan(
        self,
        workflow_plan: WorkflowPlan,
        task: Task,
        input_data: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """执行工作流计划"""
        
        strategy_handler = self.strategy_handlers[workflow_plan.strategy]
        return await strategy_handler(workflow_plan, task, input_data, db)
    
    async def _execute_collaborative_strategy(
        self,
        workflow_plan: WorkflowPlan,
        task: Task,
        input_data: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """执行协作策略"""
        
        execution_result = {
            "strategy": "collaborative",
            "agent_results": {},
            "collaboration_results": [],
            "quality_improvements": []
        }
        
        workflow_data = input_data.copy()
        
        # 执行协作会话
        for session_config in workflow_plan.collaboration_sessions:
            collaboration_result = await self._execute_collaboration_session(
                session_config, workflow_data, task, db
            )
            
            execution_result["collaboration_results"].append(collaboration_result)
            
            # 更新工作流数据
            if collaboration_result.get("success"):
                workflow_data.update(collaboration_result.get("result", {}))
        
        # 执行剩余的Agent
        remaining_agents = [
            agent for agent in workflow_plan.agent_sequence
            if agent not in self._get_collaboration_participants(workflow_plan.collaboration_sessions)
        ]
        
        for agent_type in remaining_agents:
            agent_result = await self._execute_single_agent(
                agent_type, workflow_data, task, db
            )
            execution_result["agent_results"][agent_type.value] = agent_result
            workflow_data.update(agent_result)
        
        return execution_result
    
    async def _execute_collaboration_session(
        self,
        session_config: Dict[str, Any],
        workflow_data: Dict[str, Any],
        task: Task,
        db: Session
    ) -> Dict[str, Any]:
        """执行协作会话"""
        
        session = CollaborationSession(
            session_id=session_config["session_id"],
            type=CollaborationType(session_config["type"]),
            participants=session_config["participants"],
            objectives=session_config["objectives"],
            max_iterations=session_config.get("max_iterations", 3),
            convergence_criteria=session_config.get("convergence_criteria", {})
        )
        
        self.logger.info(f"Starting collaboration session: {session.session_id}")
        
        try:
            if session.type == CollaborationType.PEER_REVIEW:
                return await self._execute_peer_review_session(session, workflow_data, task, db)
            elif session.type == CollaborationType.ITERATIVE_REFINEMENT:
                return await self._execute_iterative_refinement_session(session, workflow_data, task, db)
            else:
                raise NotImplementedError(f"Collaboration type {session.type} not implemented")
                
        except Exception as e:
            self.logger.error(f"Collaboration session failed: {e}")
            return {
                "session_id": session.session_id,
                "success": False,
                "error": str(e),
                "partial_results": workflow_data
            }
    
    async def _execute_peer_review_session(
        self,
        session: CollaborationSession,
        workflow_data: Dict[str, Any],
        task: Task,
        db: Session
    ) -> Dict[str, Any]:
        """执行同行评议协作会话"""
        
        # 第一步：创建者生成初始内容
        creator_agent = session.participants[0]
        reviewer_agents = session.participants[1:]
        
        # 执行创建者Agent
        creator_result = await self._execute_single_agent(
            AgentType(creator_agent), workflow_data, task, db
        )
        
        # 第二步：评议者提供反馈
        review_results = []
        for reviewer in reviewer_agents:
            review_input = workflow_data.copy()
            review_input["content_to_review"] = creator_result
            review_input["review_objectives"] = session.objectives
            
            reviewer_result = await self._execute_single_agent(
                AgentType(reviewer), review_input, task, db
            )
            review_results.append({
                "reviewer": reviewer,
                "feedback": reviewer_result.get("feedback", {}),
                "quality_score": reviewer_result.get("quality_score", 7.0)
            })
        
        # 第三步：整合反馈和优化
        if self._should_iterate_based_on_reviews(review_results, session.convergence_criteria):
            # 基于反馈重新生成
            improvement_input = workflow_data.copy()
            improvement_input["original_content"] = creator_result
            improvement_input["review_feedback"] = review_results
            
            improved_result = await self._execute_single_agent(
                AgentType(creator_agent), improvement_input, task, db
            )
            
            return {
                "session_id": session.session_id,
                "success": True,
                "iterations": 2,
                "result": improved_result,
                "review_summary": self._summarize_reviews(review_results),
                "quality_improvement": self._calculate_quality_improvement(creator_result, improved_result)
            }
        
        return {
            "session_id": session.session_id,
            "success": True,
            "iterations": 1,
            "result": creator_result,
            "review_summary": self._summarize_reviews(review_results)
        }
    
    async def _execute_single_agent(
        self,
        agent_type: AgentType,
        input_data: Dict[str, Any],
        task: Task,
        db: Session
    ) -> Dict[str, Any]:
        """执行单个Agent"""

        try:
            # Before hook: assemble context (declarative, optional)
            try:
                if os.getenv("MEMORY_CONTEXT_ENABLED", "true").lower() != "false":
                    # Prefer explicit workflow_id/scene_number from input_data; fallback to task.task_id
                    workflow_id = input_data.get("workflow_id") or task.task_id
                    scene_number = input_data.get("scene_number")
                    # Assemble by task_type; if not found, skip silently
                    assembled = await context_assembler.assemble(
                        task.task_type, workflow_id=workflow_id, scene_number=scene_number, token_budget=2000
                    )
                    if assembled and assembled.get("has_context"):
                        # Merge context into input_data under a reserved key
                        input_data = {**input_data, "_assembled_context": assembled}
            except Exception as hook_err:  # non-fatal
                self.logger.warning(f"Context assemble hook failed: {hook_err}")

            # 动态导入和实例化Agent
            agent_class = self._get_agent_class(agent_type)
            agent = agent_class()

            # 执行Agent
            result = await agent.execute(task, input_data, db)

            # After hook: write back memories per policy (non-fatal)
            try:
                if os.getenv("MEMORY_WRITE_ENABLED", "true").lower() != "false":
                    workflow_id = input_data.get("workflow_id") or task.task_id
                    scene_number = input_data.get("scene_number")
                    await memory_writer.write(task.task_type, workflow_id=workflow_id, scene_number=scene_number, output=result or {})
            except Exception as write_err:
                self.logger.warning(f"Memory write hook failed: {write_err}")

            return result
            
        except Exception as e:
            self.logger.error(f"Agent {agent_type.value} execution failed: {e}")
            raise
    
    def _get_agent_class(self, agent_type: AgentType):
        """根据Agent类型获取对应的类"""
        
        agent_mapping = {
            AgentType.CONCEPT_PLANNER: "ConceptPlannerAgent",
            AgentType.SCRIPT_WRITER: "ScriptWriterAgent",
            AgentType.IMAGE_GENERATOR: "ImageGeneratorAgent",
            AgentType.VIDEO_GENERATOR: "VideoGeneratorAgent",
            AgentType.VIDEO_COMPOSER: "VideoComposerAgent",
            AgentType.QUALITY_CHECKER: "QualityCheckerAgent"
        }
        
        class_name = agent_mapping.get(agent_type)
        if not class_name:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        # 动态导入
        module_name = f".{class_name.lower().replace('agent', '')}"
        module = __import__(module_name, fromlist=[class_name], level=1)
        return getattr(module, class_name)
    
    async def _perform_quality_assessment(
        self,
        execution_result: Dict[str, Any],
        workflow_plan: WorkflowPlan,
        task: Task
    ) -> Dict[str, Any]:
        """执行质量评估"""
        
        quality_assessment = {
            "overall_quality": 0.0,
            "agent_quality_scores": {},
            "collaboration_effectiveness": 0.0,
            "improvement_suggestions": []
        }
        
        # 评估各Agent输出质量
        for agent_type, agent_result in execution_result.get("agent_results", {}).items():
            quality_score = agent_result.get("quality_score", 7.0)
            quality_assessment["agent_quality_scores"][agent_type] = quality_score
        
        # 计算整体质量
        if quality_assessment["agent_quality_scores"]:
            quality_assessment["overall_quality"] = sum(
                quality_assessment["agent_quality_scores"].values()
            ) / len(quality_assessment["agent_quality_scores"])
        
        # 评估协作效果
        collaboration_results = execution_result.get("collaboration_results", [])
        if collaboration_results:
            collaboration_scores = [
                result.get("quality_improvement", 0.0) 
                for result in collaboration_results
            ]
            quality_assessment["collaboration_effectiveness"] = sum(collaboration_scores) / len(collaboration_scores)
        
        return quality_assessment
    
    async def _generate_execution_report(
        self,
        workflow_plan: WorkflowPlan,
        execution_result: Dict[str, Any],
        quality_result: Dict[str, Any],
        total_duration: float
    ) -> Dict[str, Any]:
        """生成执行报告"""
        
        return {
            "execution_summary": {
                "strategy_used": workflow_plan.strategy.value,
                "agents_executed": len(workflow_plan.agent_sequence),
                "collaborations_completed": len(workflow_plan.collaboration_sessions),
                "total_duration": total_duration,
                "estimated_vs_actual": {
                    "estimated_duration": workflow_plan.estimated_duration,
                    "actual_duration": total_duration,
                    "accuracy": abs(workflow_plan.estimated_duration - total_duration) / workflow_plan.estimated_duration
                }
            },
            "quality_metrics": quality_result,
            "performance_insights": {
                "strategy_effectiveness": self._calculate_strategy_effectiveness(workflow_plan, execution_result),
                "collaboration_value": quality_result.get("collaboration_effectiveness", 0.0),
                "efficiency_score": workflow_plan.estimated_duration / total_duration if total_duration > 0 else 0
            },
            "recommendations": await self._generate_recommendations(workflow_plan, execution_result, quality_result)
        }
    
    # 辅助方法
    def _parse_complexity_analysis(self, content: str) -> Dict[str, Any]:
        """解析复杂度分析结果"""
        try:
            import json
            return json.loads(content.strip())
        except:
            return self._get_fallback_complexity_analysis({})
    
    def _get_fallback_complexity_analysis(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """获取fallback复杂度分析"""
        return {
            "complexity_score": 5.0,
            "quality_requirements": "standard",
            "collaboration_needs": False,
            "estimated_agents_needed": 5
        }
    
    def _get_collaboration_participants(self, collaboration_sessions: List[Dict[str, Any]]) -> List[AgentType]:
        """获取参与协作的Agent类型"""
        participants = set()
        for session in collaboration_sessions:
            participants.update(session.get("participants", []))
        return [AgentType(p) for p in participants if p in [at.value for at in AgentType]]
    
    def _should_iterate_based_on_reviews(self, review_results: List[Dict], convergence_criteria: Dict) -> bool:
        """根据评议结果判断是否需要迭代"""
        if not review_results:
            return False
        
        avg_quality = sum(r.get("quality_score", 7.0) for r in review_results) / len(review_results)
        threshold = convergence_criteria.get("quality_threshold", 8.0)
        
        return avg_quality < threshold
    
    def _summarize_reviews(self, review_results: List[Dict]) -> Dict[str, Any]:
        """总结评议结果"""
        return {
            "total_reviews": len(review_results),
            "average_quality": sum(r.get("quality_score", 7.0) for r in review_results) / len(review_results),
            "key_feedback": [r.get("feedback", {}).get("summary", "") for r in review_results]
        }
    
    def _calculate_quality_improvement(self, original: Dict, improved: Dict) -> float:
        """计算质量改进程度"""
        original_quality = original.get("quality_score", 7.0)
        improved_quality = improved.get("quality_score", 7.0)
        return max(0.0, improved_quality - original_quality)
    
    def _calculate_strategy_effectiveness(self, workflow_plan: WorkflowPlan, execution_result: Dict) -> float:
        """计算策略有效性"""
        # 简化的策略有效性计算
        success_rate = 1.0 if execution_result else 0.0
        return success_rate
    
    async def _generate_recommendations(
        self,
        workflow_plan: WorkflowPlan,
        execution_result: Dict[str, Any],
        quality_result: Dict[str, Any]
    ) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # 基于质量结果的建议
        overall_quality = quality_result.get("overall_quality", 7.0)
        if overall_quality < 7.5:
            recommendations.append("Consider enabling more collaboration sessions for quality improvement")
        
        # 基于协作效果的建议
        collaboration_effectiveness = quality_result.get("collaboration_effectiveness", 0.0)
        if collaboration_effectiveness > 0.5:
            recommendations.append("Collaboration sessions were effective, consider expanding their use")
        
        return recommendations
    
    # 其他策略执行方法的简化实现
    async def _execute_pipeline_strategy(self, workflow_plan, task, input_data, db):
        """串行策略执行"""
        result = {"strategy": "pipeline", "agent_results": {}}
        workflow_data = input_data.copy()
        
        for agent_type in workflow_plan.agent_sequence:
            agent_result = await self._execute_single_agent(agent_type, workflow_data, task, db)
            result["agent_results"][agent_type.value] = agent_result
            workflow_data.update(agent_result)
        
        return result
    
    async def _execute_parallel_strategy(self, workflow_plan, task, input_data, db):
        """并行策略执行"""
        # 简化实现，实际需要更复杂的依赖管理
        return await self._execute_pipeline_strategy(workflow_plan, task, input_data, db)
    
    async def _execute_adaptive_strategy(self, workflow_plan, task, input_data, db):
        """自适应策略执行"""
        # 简化实现，实际需要动态策略调整
        return await self._execute_pipeline_strategy(workflow_plan, task, input_data, db)
    
    # 其他辅助方法的存根实现
    async def _determine_agent_sequence(self, strategy, complexity_analysis):
        return [AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER, 
                AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR, 
                AgentType.VIDEO_COMPOSER]
    
    async def _plan_collaboration_sessions(self, strategy, agent_sequence, complexity_analysis):
        if strategy == ExecutionStrategy.COLLABORATIVE:
            return [{
                "session_id": "creative_alignment",
                "type": "peer_review",
                "participants": ["concept_planner", "script_writer"],
                "objectives": ["ensure_creative_coherence"],
                "max_iterations": 2
            }]
        return []
    
    async def _estimate_execution_duration(self, strategy, agent_sequence, collaboration_sessions):
        base_time = len(agent_sequence) * 30  # 30秒每个Agent
        collaboration_time = len(collaboration_sessions) * 45  # 45秒每个协作会话
        return base_time + collaboration_time
    
    async def _estimate_execution_cost(self, agent_sequence, collaboration_sessions):
        return len(agent_sequence) * 0.5 + len(collaboration_sessions) * 0.8
    
    async def _execute_iterative_refinement_session(self, session, workflow_data, task, db):
        """迭代优化协作会话的存根实现"""
        return {
            "session_id": session.session_id,
            "success": True,
            "iterations": 1,
            "result": workflow_data
        }
