"""
Archived: ReAct Concept Planner Agent (experimental)

This module is archived and must not be imported in production paths.
It remains in the repo for reference only.
"""

raise ImportError(
    "Archived module 'react_concept_planner'. Do not import in production."
)

import json
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene
from ..services.ai_client import AIClient


class ReActConceptPlannerAgent(BaseAgent):
    """
    ReAct-enhanced Concept Planner that uses iterative reasoning cycles
    to refine and improve video concepts through observation and reflection
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.CONCEPT_PLANNER,
            agent_name="react_concept_planner",
            timeout_seconds=300,  # Extended timeout for iterative process
            max_retries=2
        )
        self.ai_client = AIClient()
        self.max_refinement_cycles = 3
        self.quality_threshold = 7.5
    
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Execute ReAct concept planning with iterative refinement"""
        
        # Validate input
        self._validate_input(input_data, ["user_prompt", "video_style", "duration"])
        
        user_prompt = input_data["user_prompt"]
        video_style = input_data.get("video_style", "professional")
        duration = input_data.get("duration", 30)
        aspect_ratio = input_data.get("aspect_ratio", "16:9")
        
        # Initialize ReAct state
        react_state = {
            "cycle": 0,
            "current_concept": None,
            "observations": [],
            "thoughts": [],
            "actions": [],
            "reflections": [],
            "quality_scores": [],
            "improvement_areas": []
        }
        
        await self._update_progress(execution, 10, "Starting ReAct concept planning", db)
        
        try:
            # Initial concept generation
            initial_concept = await self._generate_initial_concept(
                user_prompt, video_style, duration, aspect_ratio
            )
            react_state["current_concept"] = initial_concept
            
            await self._update_progress(execution, 30, "Initial concept generated", db)
            
            # ReAct refinement cycles
            for cycle in range(self.max_refinement_cycles):
                react_state["cycle"] = cycle + 1
                
                await self._update_progress(
                    execution, 
                    30 + (cycle + 1) * 20, 
                    f"ReAct cycle {cycle + 1}", 
                    db
                )
                
                # OBSERVE: Analyze current concept
                observation = await self._observe_concept(react_state["current_concept"], user_prompt)
                react_state["observations"].append(observation)
                
                # THINK: Reason about improvements
                thought = await self._think_about_improvements(observation, react_state)
                react_state["thoughts"].append(thought)
                
                # Check if concept is good enough
                if thought.get("quality_score", 0) >= self.quality_threshold:
                    self.logger.info(f"Concept quality threshold reached in cycle {cycle + 1}")
                    break
                
                # ACT: Refine the concept
                action_result = await self._act_refine_concept(thought, react_state)
                react_state["actions"].append(action_result)
                
                # Update current concept
                if action_result.get("success") and action_result.get("refined_concept"):
                    react_state["current_concept"] = action_result["refined_concept"]
                
                # REFLECT: Evaluate the refinement
                reflection = await self._reflect_on_refinement(action_result, react_state)
                react_state["reflections"].append(reflection)
                
                # Brief pause between cycles
                await asyncio.sleep(0.5)
            
            await self._update_progress(execution, 90, "Creating final concept structure", db)
            
            # Create final scenes and output
            final_concept = react_state["current_concept"]
            scenes = await self._create_scenes(task, final_concept, db)
            
            await self._update_progress(execution, 100, "ReAct concept planning completed", db)
            
            # Prepare comprehensive output
            output_data = {
                "concept_plan": final_concept,
                "scenes": [self._scene_to_dict(scene) for scene in scenes],
                "total_scenes": len(scenes),
                "estimated_duration": duration,
                "video_concept": final_concept.get("overview", ""),
                "visual_style": final_concept.get("visual_style", video_style),
                "target_audience": final_concept.get("target_audience", "general"),
                "key_messages": final_concept.get("key_messages", []),
                
                # ReAct-specific metadata
                "react_metadata": {
                    "total_cycles": react_state["cycle"],
                    "final_quality_score": react_state["reflections"][-1].get("quality_score", 0) if react_state["reflections"] else 0,
                    "improvement_iterations": len([obs for obs in react_state["observations"] if obs.get("needs_improvement", False)]),
                    "reasoning_chain": self._build_reasoning_chain(react_state),
                    "quality_progression": [r.get("quality_score", 0) for r in react_state["reflections"]]
                }
            }
            
            return output_data
            
        except Exception as e:
            error_msg = f"ReAct concept planning failed: {str(e)}"
            self.logger.error(error_msg)
            raise AgentError(error_msg) from e
    
    async def _generate_initial_concept(
        self, 
        user_prompt: str, 
        video_style: str, 
        duration: int,
        aspect_ratio: str
    ) -> Dict[str, Any]:
        """Generate initial concept as starting point for ReAct process"""
        
        initial_prompt = f"""
        Create an initial video concept plan based on these requirements:
        
        User Prompt: {user_prompt}
        Style: {video_style}
        Duration: {duration} seconds
        Aspect Ratio: {aspect_ratio}
        
        This is an initial draft that will be refined through iterative improvement.
        Focus on capturing the core ideas and basic structure.
        
        Return JSON with the standard concept structure including:
        - overview, target_audience, key_messages
        - visual_style, mood_and_tone, color_palette
        - scenes array with basic scene information
        - technical_requirements
        
        Prioritize creativity and alignment with user requirements.
        """
        
        response = await self.ai_client.generate_text(
            prompt=initial_prompt,
            model="gpt-4",
            max_tokens=2000,
            temperature=0.8,  # Higher creativity for initial generation
            response_format={"type": "json_object"}
        )
        
        return self._parse_concept_response(response["content"])
    
    async def _observe_concept(self, concept: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
        """OBSERVE: Analyze the current concept for strengths and weaknesses"""
        
        observation_prompt = f"""
        Analyze this video concept against the user requirements:
        
        User Requirements: {user_prompt}
        
        Current Concept: {json.dumps(concept, indent=2)}
        
        Provide a detailed observation focusing on:
        1. Alignment with user requirements (1-10)
        2. Creative quality and originality (1-10)
        3. Technical feasibility (1-10)
        4. Scene flow and coherence (1-10)
        5. Visual appeal and engagement (1-10)
        
        Identify specific areas that could be improved:
        - Content gaps or misalignments
        - Scene structure issues
        - Visual style inconsistencies
        - Missing elements or opportunities
        
        Return JSON with:
        - alignment_score: number
        - creativity_score: number
        - feasibility_score: number
        - flow_score: number
        - visual_appeal_score: number
        - overall_quality: number (average of above)
        - strengths: [list of strengths]
        - weaknesses: [list of weaknesses]
        - needs_improvement: boolean
        - improvement_priorities: [ordered list of what to improve first]
        """
        
        response = await self.ai_client.generate_text(
            prompt=observation_prompt,
            model="gpt-4",
            max_tokens=1200,
            temperature=0.3,  # Lower temperature for analytical observation
            response_format={"type": "json_object"}
        )
        
        return self._parse_json_response(response["content"])
    
    async def _think_about_improvements(
        self, 
        observation: Dict[str, Any], 
        react_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """THINK: Reason about what improvements should be made"""
        
        thinking_prompt = f"""
        Based on this observation, think about how to improve the concept:
        
        Current Observation: {json.dumps(observation, indent=2)}
        
        Previous Thoughts: {json.dumps(react_state["thoughts"], indent=2)}
        
        Current Cycle: {react_state["cycle"]}
        
        Think through:
        1. What are the most critical issues to address?
        2. What improvements would have the biggest impact?
        3. How can we enhance creativity while maintaining feasibility?
        4. What specific changes should be made to scenes, style, or structure?
        5. Is the concept ready, or does it need more work?
        
        Quality threshold: {self.quality_threshold}
        
        Return JSON with:
        - analysis: Your analytical reasoning
        - priority_improvements: [ordered list of improvements to make]
        - recommended_changes: detailed change recommendations
        - quality_score: your assessment of current quality (1-10)
        - confidence: your confidence in this assessment (1-10)
        - ready_for_production: boolean
        - reasoning: explanation of your recommendations
        """
        
        response = await self.ai_client.generate_text(
            prompt=thinking_prompt,
            model="gpt-4",
            max_tokens=1000,
            temperature=0.4,
            response_format={"type": "json_object"}
        )
        
        return self._parse_json_response(response["content"])
    
    async def _act_refine_concept(
        self, 
        thought: Dict[str, Any], 
        react_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """ACT: Execute refinements based on reasoning"""
        
        if thought.get("ready_for_production", False):
            return {
                "action": "no_refinement_needed",
                "success": True,
                "refined_concept": react_state["current_concept"],
                "reasoning": "Concept meets quality threshold"
            }
        
        refinement_prompt = f"""
        Refine the video concept based on this analysis:
        
        Current Concept: {json.dumps(react_state["current_concept"], indent=2)}
        
        Improvement Analysis: {json.dumps(thought, indent=2)}
        
        Make specific improvements to address the identified issues:
        {thought.get("priority_improvements", [])}
        
        Recommended Changes:
        {thought.get("recommended_changes", "")}
        
        Return the refined concept as JSON with the same structure but improved:
        - Enhanced scenes based on feedback
        - Better alignment with user requirements
        - Improved visual style and coherence
        - More engaging and feasible execution
        
        Focus on the most impactful improvements while maintaining the core concept integrity.
        """
        
        try:
            response = await self.ai_client.generate_text(
                prompt=refinement_prompt,
                model="gpt-4",
                max_tokens=2500,
                temperature=0.6,  # Balanced creativity and control
                response_format={"type": "json_object"}
            )
            
            refined_concept = self._parse_concept_response(response["content"])
            
            return {
                "action": "concept_refined",
                "success": True,
                "refined_concept": refined_concept,
                "improvements_made": thought.get("priority_improvements", []),
                "reasoning": "Successfully refined concept based on analysis"
            }
            
        except Exception as e:
            return {
                "action": "refinement_failed",
                "success": False,
                "refined_concept": react_state["current_concept"],  # Keep original
                "error": str(e),
                "reasoning": "Refinement failed, keeping current concept"
            }
    
    async def _reflect_on_refinement(
        self, 
        action_result: Dict[str, Any], 
        react_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """REFLECT: Evaluate the refinement results and plan next steps"""
        
        reflection_prompt = f"""
        Reflect on the refinement results:
        
        Action Taken: {json.dumps(action_result, indent=2)}
        
        Previous Concept Quality: {react_state["reflections"][-1].get("quality_score", "unknown") if react_state["reflections"] else "unknown"}
        
        Current Cycle: {react_state["cycle"]}
        Max Cycles: {self.max_refinement_cycles}
        
        Evaluate:
        1. Did the refinement improve the concept?
        2. What is the current quality level?
        3. Are there still significant issues?
        4. Should we continue refining or is it good enough?
        5. What would be the next most valuable improvement?
        
        Return JSON with:
        - refinement_success: boolean
        - quality_improvement: boolean
        - quality_score: current quality assessment (1-10)
        - remaining_issues: [list of remaining issues]
        - should_continue: boolean
        - next_focus_area: string
        - confidence: your confidence level (1-10)
        - reasoning: detailed reasoning for your assessment
        """
        
        response = await self.ai_client.generate_text(
            prompt=reflection_prompt,
            model="gpt-4",
            max_tokens=800,
            temperature=0.2,  # Lower temperature for evaluation
            response_format={"type": "json_object"}
        )
        
        reflection = self._parse_json_response(response["content"])
        
        # Add programmatic checks
        if react_state["cycle"] >= self.max_refinement_cycles:
            reflection["should_continue"] = False
        
        if reflection.get("quality_score", 0) >= self.quality_threshold:
            reflection["should_continue"] = False
        
        return reflection
    
    def _build_reasoning_chain(self, react_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build a comprehensive reasoning chain from ReAct cycles"""
        
        reasoning_chain = []
        
        for i in range(len(react_state["observations"])):
            cycle_reasoning = {
                "cycle": i + 1,
                "observation": react_state["observations"][i] if i < len(react_state["observations"]) else None,
                "thought": react_state["thoughts"][i] if i < len(react_state["thoughts"]) else None,
                "action": react_state["actions"][i] if i < len(react_state["actions"]) else None,
                "reflection": react_state["reflections"][i] if i < len(react_state["reflections"]) else None
            }
            reasoning_chain.append(cycle_reasoning)
        
        return reasoning_chain
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Safely parse JSON response from AI"""
        try:
            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            return json.loads(content)
        except json.JSONDecodeError:
            return {"error": "failed_to_parse_json", "raw_response": response}
    
    def _parse_concept_response(self, response_content: str) -> Dict[str, Any]:
        """Parse AI response into structured concept plan"""
        try:
            content = response_content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            concept_plan = json.loads(content)
            
            # Validate required fields
            required_fields = ["overview", "scenes"]
            for field in required_fields:
                if field not in concept_plan:
                    raise ValueError(f"Missing required field: {field}")
            
            if not isinstance(concept_plan["scenes"], list) or len(concept_plan["scenes"]) == 0:
                raise ValueError("Scenes must be a non-empty list")
            
            return concept_plan
            
        except json.JSONDecodeError as e:
            raise AgentError(f"Failed to parse concept plan JSON: {str(e)}")
        except Exception as e:
            raise AgentError(f"Invalid concept plan format: {str(e)}")
    
    async def _create_scenes(
        self, 
        task: Task, 
        concept_plan: Dict[str, Any], 
        db: Session
    ) -> List[Scene]:
        """Create scene records in database (same as original implementation)"""
        
        scenes = []
        current_start_time = 0.0
        
        for scene_data in concept_plan["scenes"]:
            scene = Scene(
                task_id=task.id,
                scene_number=scene_data.get("scene_number", len(scenes) + 1),
                scene_type=self._map_scene_type(scene_data.get("scene_type", "main_content")),
                title=scene_data.get("title", f"Scene {len(scenes) + 1}"),
                description=scene_data.get("description", ""),
                
                narrative_description=scene_data.get("narrative_description", ""),
                visual_description=scene_data.get("visual_description", ""),
                
                duration=float(scene_data.get("duration", 5)),
                start_time=current_start_time,
                
                background_prompt=scene_data.get("visual_description", ""),
                character_descriptions=scene_data.get("characters", []),
                props_and_objects=scene_data.get("props", []),
                mood_and_atmosphere=scene_data.get("mood", ""),
                
                camera_angle=scene_data.get("camera_angle", "medium shot"),
                lighting_style=scene_data.get("lighting", "natural"),
                art_style=concept_plan.get("visual_style", "realistic"),
                color_palette=concept_plan.get("color_palette", [])
            )
            
            scene.end_time = current_start_time + scene.duration
            current_start_time = scene.end_time
            
            db.add(scene)
            scenes.append(scene)
        
        db.commit()
        
        for scene in scenes:
            db.refresh(scene)
        
        return scenes
    
    def _map_scene_type(self, scene_type_str: str):
        """Map string scene type to enum (same as original)"""
        from ..models import SceneType
        mapping = {
            "intro": SceneType.INTRO,
            "main_content": SceneType.MAIN_CONTENT,
            "transition": SceneType.TRANSITION,
            "outro": SceneType.OUTRO,
            "background": SceneType.BACKGROUND
        }
        return mapping.get(scene_type_str.lower(), SceneType.MAIN_CONTENT)
    
    def _scene_to_dict(self, scene: Scene) -> Dict[str, Any]:
        """Convert scene model to dictionary (same as original)"""
        return {
            "id": scene.id,
            "scene_number": scene.scene_number,
            "scene_type": scene.scene_type.value,
            "title": scene.title,
            "description": scene.description,
            "duration": scene.duration,
            "start_time": scene.start_time,
            "end_time": scene.end_time,
            "visual_description": scene.visual_description,
            "narrative_description": scene.narrative_description,
            "mood": scene.mood_and_atmosphere,
            "camera_angle": scene.camera_angle,
            "lighting": scene.lighting_style,
            "art_style": scene.art_style,
            "characters": scene.character_descriptions,
            "props": scene.props_and_objects,
            "color_palette": scene.color_palette
        }
