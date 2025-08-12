"""
ReAct (Reasoning + Acting) Orchestrator Agent
Enhanced orchestrator that implements iterative reasoning and action cycles
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, TaskStatus, AgentType
from ..services.ai_client import AIClient


class ReasoningStep(Enum):
    """Types of reasoning steps in the ReAct cycle"""
    OBSERVE = "observe"
    THINK = "think"
    PLAN = "plan"
    ACT = "act"
    REFLECT = "reflect"


class ActionType(Enum):
    """Available actions the orchestrator can take"""
    GENERATE_CONCEPT = "generate_concept"
    WRITE_SCRIPT = "write_script" 
    GENERATE_IMAGES = "generate_images"
    GENERATE_VIDEO = "generate_video"
    COMPOSE_VIDEO = "compose_video"
    CHECK_QUALITY = "check_quality"
    REFINE_CONCEPT = "refine_concept"
    ADJUST_SCRIPT = "adjust_script"
    REGENERATE_ASSETS = "regenerate_assets"
    COMPLETE_TASK = "complete_task"


class ReActOrchestratorAgent(BaseAgent):
    """
    ReAct (Reasoning + Acting) Orchestrator Agent
    
    Implements iterative cycles of:
    1. Observe - Analyze current state and results
    2. Think - Reason about next steps
    3. Plan - Create action plan 
    4. Act - Execute specific action
    5. Reflect - Evaluate results and decide next iteration
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="react_orchestrator",
            timeout_seconds=3600,  # 1 hour for iterative process
            max_retries=1
        )
        
        self.ai_client = AIClient()
        self.reasoning_history = []
        self.max_iterations = 10
        self.quality_threshold = 7.0
        
        # 获取AI配置
        from ..core.ai_config import get_ai_config
        self.ai_config_manager = get_ai_config()
        self.orchestrator_model = self.ai_config_manager.get_model_for_agent("default")
        self.model_config = self.ai_config_manager.get_model_config(self.orchestrator_model)
        
        # Available agents for actions
        self.available_agents = {
            ActionType.GENERATE_CONCEPT: "ConceptPlannerAgent",
            ActionType.WRITE_SCRIPT: "ScriptWriterAgent",
            ActionType.GENERATE_IMAGES: "ImageGeneratorAgent", 
            ActionType.GENERATE_VIDEO: "VideoGeneratorAgent",
            ActionType.COMPOSE_VIDEO: "VideoComposerAgent",
            ActionType.CHECK_QUALITY: "QualityCheckerAgent"
        }
    
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Execute ReAct iterative workflow"""
        
        self._current_task = task
        task.status = TaskStatus.IN_PROGRESS
        db.commit()
        
        # Initialize workflow state
        workflow_state = {
            "user_requirements": input_data,
            "current_results": {},
            "quality_scores": {},
            "iteration_count": 0,
            "completed_actions": [],
            "failed_actions": [],
            "reasoning_chain": []
        }
        
        try:
            # Main ReAct loop
            while workflow_state["iteration_count"] < self.max_iterations:
                iteration = workflow_state["iteration_count"] + 1
                
                self.logger.info(f"Starting ReAct iteration {iteration}")
                await self._update_progress(
                    execution, 
                    min(90, iteration * 10), 
                    f"ReAct iteration {iteration}",
                    db
                )
                
                # 1. OBSERVE - Analyze current state
                observation = await self._observe_current_state(workflow_state)
                
                # 2. THINK - Reason about the situation
                reasoning = await self._think_and_reason(observation, workflow_state)
                
                # 3. PLAN - Decide on next action
                action_plan = await self._plan_next_action(reasoning, workflow_state)
                
                # 4. ACT - Execute the planned action
                action_result = await self._execute_action(action_plan, workflow_state, db)
                
                # 5. REFLECT - Evaluate results and decide if complete
                reflection = await self._reflect_on_results(action_result, workflow_state)
                
                # Update workflow state
                workflow_state["iteration_count"] = iteration
                workflow_state["reasoning_chain"].append({
                    "iteration": iteration,
                    "observation": observation,
                    "reasoning": reasoning,
                    "action_plan": action_plan,
                    "action_result": action_result,
                    "reflection": reflection
                })
                
                # Check if workflow is complete
                if reflection.get("workflow_complete", False):
                    self.logger.info(f"Workflow completed after {iteration} iterations")
                    break
                
                # Check for critical failures
                if reflection.get("critical_failure", False):
                    raise AgentError(f"Critical failure in iteration {iteration}: {reflection.get('error')}")
                
                # Brief pause between iterations
                await asyncio.sleep(1)
            
            # Finalize results
            final_results = await self._finalize_workflow(workflow_state, db)
            
            task.status = TaskStatus.COMPLETED
            task.update_progress("Completed", 100)
            db.commit()
            
            return final_results
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.add_error(str(e))
            db.commit()
            raise AgentError(f"ReAct workflow failed: {str(e)}") from e
    
    async def _observe_current_state(self, workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """OBSERVE: Analyze current workflow state and available information"""
        
        observation_prompt = f"""
        Analyze the current state of the video generation workflow:
        
        User Requirements: {json.dumps(workflow_state['user_requirements'], indent=2)}
        
        Current Results: {json.dumps(workflow_state['current_results'], indent=2)}
        
        Completed Actions: {workflow_state['completed_actions']}
        Failed Actions: {workflow_state['failed_actions']}
        
        Quality Scores: {json.dumps(workflow_state['quality_scores'], indent=2)}
        
        Iteration: {workflow_state['iteration_count'] + 1}
        
        Provide a detailed observation of:
        1. What has been accomplished so far
        2. What is still needed
        3. Any quality issues or gaps
        4. Current workflow progress status
        
        Return as JSON with keys: accomplished, needed, issues, progress_assessment
        """
        
        try:
            response = await self.ai_client.generate_text(
                prompt=observation_prompt,
                model=self.orchestrator_model,
                max_tokens=self.model_config.max_tokens if self.model_config else 1000,
                temperature=0.3
            )
            
            return self._parse_json_response(response["content"])
            
        except Exception as e:
            return {
                "accomplished": workflow_state['completed_actions'],
                "needed": ["error_in_observation"],
                "issues": [f"Observation failed: {str(e)}"],
                "progress_assessment": "uncertain"
            }
    
    async def _think_and_reason(
        self, 
        observation: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """THINK: Reason about the current situation and what should be done"""
        
        reasoning_prompt = f"""
        Based on the following observation, reason about the next steps:
        
        Observation: {json.dumps(observation, indent=2)}
        
        Consider:
        1. What is the most critical next step?
        2. Are there any quality issues that need addressing?
        3. Should we proceed forward or refine existing work?
        4. What are the risks and benefits of different approaches?
        5. How close are we to completion?
        
        Available actions: {[action.value for action in ActionType]}
        
        Provide reasoning with:
        - analysis: Your analysis of the situation
        - priority_assessment: What needs immediate attention
        - risk_evaluation: Potential risks and mitigation
        - recommended_approach: Your recommended next step
        - confidence_level: How confident you are (1-10)
        
        Return as JSON.
        """
        
        try:
            response = await self.ai_client.generate_text(
                prompt=reasoning_prompt,
                model=self.orchestrator_model,
                max_tokens=1200,
                temperature=0.4
            )
            
            return self._parse_json_response(response["content"])
            
        except Exception as e:
            return {
                "analysis": f"Reasoning failed: {str(e)}",
                "priority_assessment": "proceed_with_caution",
                "risk_evaluation": "high_uncertainty",
                "recommended_approach": "retry_last_action",
                "confidence_level": 1
            }
    
    async def _plan_next_action(
        self, 
        reasoning: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """PLAN: Create specific action plan based on reasoning"""
        
        planning_prompt = f"""
        Create a specific action plan based on this reasoning:
        
        Reasoning: {json.dumps(reasoning, indent=2)}
        
        Workflow State: 
        - Completed: {workflow_state['completed_actions']}
        - Failed: {workflow_state['failed_actions']}
        
        Available actions: {[action.value for action in ActionType]}
        
        Create a plan with:
        - action: The specific action to take (from available actions)
        - parameters: Parameters for the action
        - success_criteria: How to measure success
        - fallback_plan: What to do if this action fails
        - expected_duration: Estimated time in seconds
        
        Return as JSON.
        """
        
        try:
            response = await self.ai_client.generate_text(
                prompt=planning_prompt,
                model=self.orchestrator_model,
                max_tokens=800,
                temperature=0.3
            )
            
            return self._parse_json_response(response["content"])
            
        except Exception as e:
            # Fallback to basic sequential action
            return self._get_fallback_action_plan(workflow_state)
    
    async def _execute_action(
        self, 
        action_plan: Dict[str, Any], 
        workflow_state: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """ACT: Execute the planned action"""
        
        action_name = action_plan.get("action")
        parameters = action_plan.get("parameters", {})
        
        self.logger.info(f"Executing action: {action_name}")
        
        try:
            if action_name == ActionType.GENERATE_CONCEPT.value:
                result = await self._execute_concept_generation(parameters, workflow_state, db)
            elif action_name == ActionType.WRITE_SCRIPT.value:
                result = await self._execute_script_writing(parameters, workflow_state, db)
            elif action_name == ActionType.GENERATE_IMAGES.value:
                result = await self._execute_image_generation(parameters, workflow_state, db)
            elif action_name == ActionType.GENERATE_VIDEO.value:
                result = await self._execute_video_generation(parameters, workflow_state, db)
            elif action_name == ActionType.COMPOSE_VIDEO.value:
                result = await self._execute_video_composition(parameters, workflow_state, db)
            elif action_name == ActionType.CHECK_QUALITY.value:
                result = await self._execute_quality_check(parameters, workflow_state, db)
            elif action_name == ActionType.REFINE_CONCEPT.value:
                result = await self._execute_concept_refinement(parameters, workflow_state, db)
            elif action_name == ActionType.COMPLETE_TASK.value:
                result = await self._execute_task_completion(parameters, workflow_state, db)
            else:
                raise AgentError(f"Unknown action: {action_name}")
            
            workflow_state['completed_actions'].append(action_name)
            workflow_state['current_results'][action_name] = result
            
            return {
                "action": action_name,
                "success": True,
                "result": result,
                "execution_time": result.get("execution_time", 0)
            }
            
        except Exception as e:
            workflow_state['failed_actions'].append({
                "action": action_name,
                "error": str(e),
                "iteration": workflow_state["iteration_count"] + 1
            })
            
            return {
                "action": action_name,
                "success": False,
                "error": str(e),
                "execution_time": 0
            }
    
    async def _reflect_on_results(
        self, 
        action_result: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """REFLECT: Evaluate action results and decide on next steps"""
        
        reflection_prompt = f"""
        Reflect on the action result and current workflow state:
        
        Action Result: {json.dumps(action_result, indent=2)}
        
        Current Workflow State:
        - Completed Actions: {workflow_state['completed_actions']}
        - Failed Actions: {workflow_state['failed_actions']}
        - Quality Scores: {workflow_state['quality_scores']}
        - Iteration: {workflow_state['iteration_count'] + 1}
        
        Quality Threshold: {self.quality_threshold}
        Max Iterations: {self.max_iterations}
        
        Evaluate:
        1. Was the action successful?
        2. Does the result meet quality standards?
        3. Is the workflow ready to complete?
        4. Are there critical issues that need addressing?
        5. Should we continue or conclude?
        
        Return JSON with:
        - action_success: boolean
        - quality_acceptable: boolean
        - workflow_complete: boolean
        - critical_failure: boolean
        - next_recommendation: string
        - confidence: number (1-10)
        - reasoning: string explanation
        """
        
        try:
            response = await self.ai_client.generate_text(
                prompt=reflection_prompt,
                model=self.orchestrator_model,
                max_tokens=800,
                temperature=0.2
            )
            
            reflection = self._parse_json_response(response["content"])
            
            # Additional programmatic checks
            if len(workflow_state['completed_actions']) >= 6:  # All main actions done
                reflection['workflow_complete'] = True
            
            if workflow_state['iteration_count'] >= self.max_iterations - 1:
                reflection['workflow_complete'] = True
                
            return reflection
            
        except Exception as e:
            return {
                "action_success": action_result.get("success", False),
                "quality_acceptable": False,
                "workflow_complete": False,
                "critical_failure": True,
                "next_recommendation": "error_recovery",
                "confidence": 1,
                "reasoning": f"Reflection failed: {str(e)}"
            }
    
    # Action execution methods (simplified implementations)
    async def _execute_concept_generation(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute concept generation with dynamic parameters"""
        # Import and use existing ConceptPlannerAgent
        from .concept_planner import ConceptPlannerAgent
        
        agent = ConceptPlannerAgent()
        input_data = workflow_state['user_requirements'].copy()
        input_data.update(parameters)
        
        return await agent._execute_impl(self._current_task, input_data, None, db)
    
    async def _execute_script_writing(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute script writing with concept context"""
        from .script_writer import ScriptWriterAgent
        
        agent = ScriptWriterAgent()
        input_data = workflow_state['current_results'].copy()
        input_data.update(parameters)
        
        return await agent._execute_impl(self._current_task, input_data, None, db)
    
    async def _execute_image_generation(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute image generation with script context"""
        from .image_generator import ImageGeneratorAgent
        
        agent = ImageGeneratorAgent()
        input_data = workflow_state['current_results'].copy()
        input_data.update(parameters)
        
        return await agent._execute_impl(self._current_task, input_data, None, db)
    
    async def _execute_video_generation(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute video generation with image context"""
        from .video_generator import VideoGeneratorAgent
        
        agent = VideoGeneratorAgent()
        input_data = workflow_state['current_results'].copy()
        input_data.update(parameters)
        
        return await agent._execute_impl(self._current_task, input_data, None, db)
    
    async def _execute_video_composition(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute video composition with all previous context"""
        from .video_composer import VideoComposerAgent
        
        agent = VideoComposerAgent()
        input_data = workflow_state['current_results'].copy()
        input_data.update(parameters)
        
        return await agent._execute_impl(self._current_task, input_data, None, db)
    
    async def _execute_quality_check(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute quality check on current results"""
        from .quality_checker import QualityCheckerAgent
        
        agent = QualityCheckerAgent()
        input_data = workflow_state['current_results'].copy()
        input_data.update(parameters)
        
        result = await agent._execute_impl(self._current_task, input_data, None, db)
        
        # Update quality scores
        if 'quality_score' in result:
            workflow_state['quality_scores']['overall'] = result['quality_score']
        
        return result
    
    async def _execute_concept_refinement(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Refine concept based on quality feedback"""
        # Enhanced concept generation with feedback
        refinement_params = parameters.copy()
        refinement_params['refinement_feedback'] = workflow_state.get('quality_scores', {})
        
        return await self._execute_concept_generation(refinement_params, workflow_state, db)
    
    async def _execute_task_completion(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Complete the task and prepare final output"""
        return {
            "status": "completed",
            "final_results": workflow_state['current_results'],
            "reasoning_chain": workflow_state['reasoning_chain'],
            "total_iterations": workflow_state['iteration_count']
        }
    
    def _get_fallback_action_plan(self, workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """Get fallback action plan if planning fails"""
        completed = workflow_state['completed_actions']
        
        # Simple sequential fallback
        if ActionType.GENERATE_CONCEPT.value not in completed:
            return {"action": ActionType.GENERATE_CONCEPT.value, "parameters": {}}
        elif ActionType.WRITE_SCRIPT.value not in completed:
            return {"action": ActionType.WRITE_SCRIPT.value, "parameters": {}}
        elif ActionType.GENERATE_IMAGES.value not in completed:
            return {"action": ActionType.GENERATE_IMAGES.value, "parameters": {}}
        elif ActionType.GENERATE_VIDEO.value not in completed:
            return {"action": ActionType.GENERATE_VIDEO.value, "parameters": {}}
        elif ActionType.COMPOSE_VIDEO.value not in completed:
            return {"action": ActionType.COMPOSE_VIDEO.value, "parameters": {}}
        else:
            return {"action": ActionType.COMPLETE_TASK.value, "parameters": {}}
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Safely parse JSON response from AI"""
        try:
            # Clean response
            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            return json.loads(content)
        except json.JSONDecodeError:
            return {"error": "failed_to_parse_json", "raw_response": response}
    
    async def _finalize_workflow(self, workflow_state: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Finalize workflow and prepare final results"""
        
        return {
            "workflow_type": "react_iterative",
            "total_iterations": workflow_state["iteration_count"],
            "completed_actions": workflow_state["completed_actions"],
            "failed_actions": workflow_state["failed_actions"], 
            "quality_scores": workflow_state["quality_scores"],
            "final_results": workflow_state["current_results"],
            "reasoning_chain": workflow_state["reasoning_chain"],
            "performance_metrics": {
                "efficiency": len(workflow_state["completed_actions"]) / max(1, workflow_state["iteration_count"]),
                "success_rate": len(workflow_state["completed_actions"]) / (len(workflow_state["completed_actions"]) + len(workflow_state["failed_actions"])) if (len(workflow_state["completed_actions"]) + len(workflow_state["failed_actions"])) > 0 else 1.0,
                "avg_quality": sum(workflow_state["quality_scores"].values()) / max(1, len(workflow_state["quality_scores"]))
            }
        }