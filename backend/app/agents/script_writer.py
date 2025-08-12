"""
Script Writer Agent - Generates detailed scripts for video scenes
"""
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene
from ..services.ai_client import AIClient
from ..core.workflow_state import WorkflowState, SceneData


class ScriptWriterAgent(BaseAgent):
    """
    Script Writer Agent generates detailed scripts, narratives, and voice-over
    text for each scene based on the concept plan
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.SCRIPT_WRITER,
            agent_name="script_writer",
            timeout_seconds=180,
            max_retries=2
        )
        self.ai_client = AIClient()
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Generate scripts for all scenes"""
        
        # Validate input
        self._validate_input(input_data, ["concept_plan", "workflow_state_id"])
        
        concept_plan = input_data["concept_plan"]
        workflow_state_id = input_data["workflow_state_id"]
        
        # 通过 workflow_manager 获取 WorkflowState
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {workflow_state_id} not found")
        
        await self._update_progress(execution, 10, "Loading scenes", db)
        
        # Get scenes from WorkflowState instead of database
        scenes = workflow_state.scenes
        
        if not scenes:
            raise AgentError("No scenes found in workflow state")
        
        await self._update_progress(execution, 20, "Generating scripts", db)
        
        script_results = []
        total_scenes = len(scenes)
        
        for i, scene_data in enumerate(scenes):
            scene_progress = 20 + int((i / total_scenes) * 60)
            await self._update_progress(
                execution, 
                scene_progress, 
                f"Writing script for scene {scene_data.scene_number}",
                db
            )
            
            # Generate script for this scene
            scene_script = await self._generate_scene_script_from_data(scene_data, concept_plan, execution)
            
            # Update scene data in WorkflowState with enhanced scene design elements
            workflow_state.update_scene(scene_data.scene_number, 
                script_text=scene_script["script_text"],
                voice_over_text=scene_script["voice_over_text"], 
                narrative_description=scene_script["narrative_description"],
                background_music_style=scene_script.get("background_music_style", ""),
                sound_effects=scene_script.get("sound_effects", []),
                # 新增：ScriptWriter专注的场景设计元素
                scene_design_elements=scene_script.get("scene_design_elements", {}),
                narrative_structure=scene_script.get("narrative_structure", {}),
                audio_design=scene_script.get("audio_design", {}),
                pacing_and_timing=scene_script.get("pacing_and_timing", {}),
                content_development_arc=scene_script.get("content_development_arc", {})
            )
            
            script_results.append({
                "scene_number": scene_data.scene_number,
                "script": scene_script
            })
        
        await self._update_progress(execution, 85, "Generating overall narrative", db)
        
        # Generate overall video narrative using WorkflowState scenes
        overall_narrative = await self._generate_overall_narrative_from_state(
            workflow_state.scenes, concept_plan
        )
        
        # Update workflow state with overall narrative
        workflow_state.overall_narrative = overall_narrative.get("story_arc", "")
        workflow_state.script_themes = self._extract_themes(script_results)
        workflow_state.voice_over_instructions = self._generate_voice_instructions(concept_plan)
        workflow_state.estimated_word_count = sum(
            len(script["script"]["script_text"].split()) 
            for script in script_results
        )
        workflow_state.estimated_reading_time = self._calculate_reading_time(script_results)
        
        await self._update_progress(execution, 95, "Finalizing scripts", db)
        
        # Prepare output data
        output_data = {
            "scripts": script_results,
            "overall_narrative": overall_narrative,
            "total_scenes": len(scenes),
            "estimated_word_count": workflow_state.estimated_word_count,
            "estimated_reading_time": workflow_state.estimated_reading_time,
            "script_themes": workflow_state.script_themes,
            "voice_over_instructions": workflow_state.voice_over_instructions,
            "workflow_state_id": workflow_state_id  # 返回状态ID而不是对象
        }
        
        await self._update_progress(execution, 100, "Script writing completed", db)
        
        return output_data
    
    async def _generate_scene_script_from_data(
        self, 
        scene_data: SceneData, 
        concept_plan: Dict[str, Any],
        execution: AgentExecution
    ) -> Dict[str, Any]:
        """Generate script for a single scene"""
        
        script_prompt = f"""
You are a professional scriptwriter creating a script for a video scene.

Scene Information:
- Scene Number: {scene_data.scene_number}
- Scene Type: {scene_data.scene_type}
- Title: {scene_data.title}
- Duration: {scene_data.duration} seconds
- Description: {scene_data.description}
- Visual Description: {scene_data.visual_description}
- Mood: {scene_data.mood_and_atmosphere}
- Camera Angle: {scene_data.camera_angle}
- Characters: {scene_data.character_descriptions}
- Props: {scene_data.props_and_objects}

Video Context:
- Overall Concept: {concept_plan.get('overview', '')}
- Target Audience: {concept_plan.get('target_audience', '')}
- Key Messages: {concept_plan.get('key_messages', [])}
- Visual Style: {concept_plan.get('visual_style', '')}
- Mood and Tone: {concept_plan.get('mood_and_tone', '')}

Please create a detailed script focused on scene narrative and development in JSON format:

{{
    "script_text": "Main script/dialogue text that will be spoken or displayed",
    "voice_over_text": "Optimized text for voice-over narration (if different from script)",
    "narrative_description": "Detailed narrative description of what happens in this scene",
    "content_development_arc": {{
        "scene_concept_duration": "Dynamic duration based on content complexity (not hardcoded)",
        "narrative_progression": "How the scene advances the overall story",
        "emotional_journey": "Emotional arc within this scene duration",
        "action_sequence": "Key actions/events that happen in sequence",
        "scene_transition": "How this scene connects to the next scene"
    }},
    "scene_design_elements": {{
        "key_subjects": ["list", "of", "main", "subjects", "in", "scene"],
        "scene_setting": "Physical environment and location description",
        "visual_style_notes": "Visual style guidance for image generation",
        "composition_requirements": "Key composition elements that must be maintained",
        "continuity_elements": "Elements that must remain consistent throughout scene"
    }},
    "narrative_structure": {{
        "opening_state": "How the scene begins - narrative context",
        "main_action": "Central action or event in the scene", 
        "closing_state": "How the scene concludes - narrative context",
        "story_function": "What role this scene plays in overall narrative"
    }},
    "audio_design": {{
        "background_music_style": "Type of background music that would fit",
        "sound_effects": ["list", "of", "sound", "effects", "needed"],
        "audio_pacing": "Audio rhythm and timing notes"
    }},
    "pacing_and_timing": {{
        "narrative_tempo": "Fast/Medium/Slow narrative pacing for this scene",
        "key_timing_moments": ["important", "timing", "cues"],
        "transition_timing": "How long transitions should take"
    }},
    "emotional_tone": "Emotional tone of this scene",
    "key_words": ["important", "keywords", "for", "emphasis"]
}}

Guidelines for Scene Design and Narrative Structure:
1. Design content development arc based on scene concept (not hardcoded {scene_data.duration}s)
2. Focus on NARRATIVE STRUCTURE: story progression, character development, emotional journey
3. Create clear scene transitions that connect seamlessly with adjacent scenes
4. Design action sequences that are filmable and visually compelling
5. Provide detailed scene design elements for ImageGenerator to use
6. Match the visual style and mood from Creative Director's guidance
7. Consider the target audience and overall narrative flow
8. Ensure continuity with overall video concept and previous scenes
9. Voice-over text should be natural, engaging, and match the emotional tone
10. Plan pacing and timing that serves the story, not arbitrary durations
11. Identify key subjects and elements that define each scene
12. Design narrative opening/closing states that create story flow
13. Provide clear composition requirements for visual consistency
14. CRITICAL: Focus on story structure, leave visual frame generation to ImageGenerator

Return only the JSON object, no additional text.
"""
        
        try:
            # 使用AI配置管理器获取适合的模型
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            script_model = ai_config_manager.get_model_for_agent("script_writer")
            model_config = ai_config_manager.get_model_config(script_model)
            
            response = await self.ai_client.generate_text(
                prompt=script_prompt,
                model=script_model,
                max_tokens=model_config.max_tokens if model_config else 1500,
                temperature=model_config.temperature if model_config else 0.7
            )
            
            self._update_token_usage(
                execution, 
                response.get("usage", {}).get("total_tokens", 0)
            )
            
            return self._parse_script_response(response["content"])
            
        except Exception as e:
            self.logger.error(f"Failed to generate script for scene {scene_data.scene_number}: {str(e)}")
            # Return fallback script
            return self._generate_fallback_script_from_data(scene_data)
    
    def _parse_script_response(self, response_content: str) -> Dict[str, Any]:
        """Parse AI response into structured script data"""
        
        try:
            # Clean response if needed
            content = response_content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            script_data = json.loads(content)
            
            # Validate required fields
            required_fields = ["script_text", "voice_over_text", "narrative_description"]
            for field in required_fields:
                if field not in script_data:
                    script_data[field] = script_data.get("script_text", "")
            
            # Ensure scene design elements exist
            if "scene_design_elements" not in script_data:
                script_data["scene_design_elements"] = {
                    "key_subjects": [],
                    "scene_setting": script_data.get("narrative_description", ""),
                    "visual_style_notes": "Standard visual style",
                    "composition_requirements": "Balanced composition",
                    "continuity_elements": []
                }
            
            if "narrative_structure" not in script_data:
                script_data["narrative_structure"] = {
                    "opening_state": "Scene beginning",
                    "main_action": script_data.get("narrative_description", ""),
                    "closing_state": "Scene completion",
                    "story_function": "Narrative progression"
                }
                
            if "audio_design" not in script_data:
                script_data["audio_design"] = {
                    "background_music_style": script_data.get("background_music_style", "ambient"),
                    "sound_effects": script_data.get("sound_effects", []),
                    "audio_pacing": "moderate"
                }
            
            if "content_development_arc" not in script_data:
                script_data["content_development_arc"] = {
                    "scene_concept_duration": "based on content complexity",
                    "narrative_progression": script_data.get("narrative_description", ""),
                    "emotional_journey": script_data.get("emotional_tone", "neutral"),
                    "action_sequence": "scene actions"
                }
            
            return script_data
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse script JSON: {str(e)}")
            raise AgentError(f"Invalid script format: {str(e)}")
    
    def _generate_fallback_script_from_data(self, scene_data: SceneData) -> Dict[str, Any]:
        """Generate fallback script when AI generation fails"""
        
        return {
            "script_text": scene_data.description or f"Scene {scene_data.scene_number}",
            "voice_over_text": scene_data.description or f"Scene {scene_data.scene_number}",
            "narrative_description": scene_data.visual_description or scene_data.description or "",
            "content_development_arc": {
                "scene_concept_duration": f"Dynamic duration for scene {scene_data.scene_number}",
                "narrative_progression": scene_data.description or "Scene progression",
                "emotional_journey": scene_data.mood_and_atmosphere or "neutral emotional flow",
                "action_sequence": "Basic scene actions",
                "scene_transition": "Standard transition to next scene"
            },
            "scene_design_elements": {
                "key_subjects": scene_data.props_and_objects or [],
                "scene_setting": scene_data.description or "Scene environment",
                "visual_style_notes": scene_data.mood_and_atmosphere or "neutral visual style",
                "composition_requirements": "Balanced composition with clear focus",
                "continuity_elements": scene_data.props_and_objects or []
            },
            "narrative_structure": {
                "opening_state": f"Scene {scene_data.scene_number} beginning context",
                "main_action": scene_data.description or "Basic scene action",
                "closing_state": f"Scene {scene_data.scene_number} completion",
                "story_function": "Sequential narrative progression"
            },
            "audio_design": {
                "background_music_style": "ambient",
                "sound_effects": [],
                "audio_pacing": "moderate"
            },
            "pacing_and_timing": {
                "narrative_tempo": "medium",
                "key_timing_moments": [],
                "transition_timing": "standard"
            },
            "emotional_tone": scene_data.mood_and_atmosphere or "neutral",
            "key_words": []
        }
    
    async def _generate_overall_narrative_from_state(
        self, 
        scenes: List[SceneData], 
        concept_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate overall narrative structure for the video"""
        
        scenes_summary = []
        for scene_data in scenes:
            scenes_summary.append({
                "scene_number": scene_data.scene_number,
                "title": scene_data.title,
                "duration": scene_data.duration,
                "script": scene_data.script_text[:200] if scene_data.script_text else "",
                "narrative": scene_data.narrative_description[:200] if scene_data.narrative_description else ""
            })
        
        narrative_prompt = f"""
Create an overall narrative structure for this video based on all scenes.

Video Concept: {concept_plan.get('overview', '')}
Total Scenes: {len(scenes)}

Scene Summary:
{json.dumps(scenes_summary, indent=2)}

Please provide:
{{
    "story_arc": "Description of the overall story progression",
    "opening_hook": "How the video captures attention in the first few seconds",
    "main_message": "Core message or theme",
    "climax_scene": "Which scene number contains the climax/key moment",
    "resolution": "How the video concludes",
    "narrative_flow": "Description of how scenes connect",
    "call_to_action": "What action viewers should take after watching",
    "tone_consistency": "Notes about maintaining consistent tone",
    "pacing_strategy": "Overall pacing and rhythm strategy"
}}

Return only JSON, no additional text.
"""
        
        try:
            # 使用AI配置管理器获取适合的模型
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            script_model = ai_config_manager.get_model_for_agent("script_writer")
            model_config = ai_config_manager.get_model_config(script_model)
            
            response = await self.ai_client.generate_text(
                prompt=narrative_prompt,
                model=script_model,
                max_tokens=model_config.max_tokens if model_config else 800,
                temperature=model_config.temperature if model_config else 0.6
            )
            
            return json.loads(response["content"].strip())
            
        except Exception as e:
            self.logger.warning(f"Failed to generate overall narrative: {str(e)}")
            return {
                "story_arc": "Standard progression",
                "main_message": concept_plan.get("overview", ""),
                "narrative_flow": "Sequential scene progression"
            }
    
    def _calculate_reading_time(self, script_results: List[Dict]) -> int:
        """Calculate estimated reading time in seconds"""
        
        total_words = sum(
            len(script["script"]["script_text"].split()) 
            for script in script_results
        )
        
        # Average reading speed: 150-160 words per minute for voice-over
        words_per_second = 2.5
        return int(total_words / words_per_second)
    
    def _extract_themes(self, script_results: List[Dict]) -> List[str]:
        """Extract main themes from all scripts"""
        
        themes = set()
        
        for script_result in script_results:
            script = script_result["script"]
            
            # Extract keywords
            keywords = script.get("key_words", [])
            themes.update(keywords)
            
            # Extract from emotional tones
            emotional_tone = script.get("emotional_tone", "")
            if emotional_tone:
                themes.add(emotional_tone)
        
        return list(themes)[:10]  # Return top 10 themes
    
    def _generate_voice_instructions(self, concept_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Generate voice-over instructions for the entire video"""
        
        return {
            "overall_tone": concept_plan.get("mood_and_tone", "professional"),
            "pace": "moderate",
            "style": "conversational and engaging",
            "target_audience": concept_plan.get("target_audience", "general"),
            "pronunciation_notes": [],
            "emphasis_points": concept_plan.get("key_messages", []),
            "pauses_and_timing": "Natural pauses between scenes"
        }