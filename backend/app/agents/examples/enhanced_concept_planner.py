"""
Enhanced Concept Planner Agent - Example using new agent architecture
"""

import json
import asyncio
from typing import Dict, Any
from sqlalchemy.orm import Session

from ..base import BaseAgent
from ...models import Task, AgentExecution, AgentType


class EnhancedConceptPlannerAgent(BaseAgent):
    """
    Enhanced concept planner agent using tools, memory, and prompt templates
    
    This agent demonstrates the new architecture with:
    - Tool integration (OpenAI client)
    - Memory management
    - Prompt template rendering
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.CONCEPT_PLANNER,
            agent_name="enhanced_concept_planner",
            timeout_seconds=120,
            max_retries=3,
            tools=["openai_client"],  # Load OpenAI client tool
            memory_config={
                "short_term_ttl": 3600,  # 1 hour
                "enable_consolidation": True,
                "max_short_term_items": 500
            },
            prompt_templates=["concept_planner"]  # Use concept planner template
        )
    
    def _initialize_agent(self):
        """Agent-specific initialization"""
        self.logger.info("Initializing Enhanced Concept Planner Agent")
        
        # Store agent configuration in memory
        asyncio.create_task(self.store_memory(
            content={
                "agent_type": "concept_planner",
                "version": "2.0",
                "capabilities": [
                    "creative_planning",
                    "theme_analysis", 
                    "visual_direction",
                    "narrative_structure"
                ]
            },
            tags=["agent_config", "initialization"],
            importance="high"
        ))
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """
        Enhanced execution with tool and memory integration
        """
        try:
            # Store the task input in memory
            await self.store_memory(
                content=input_data,
                tags=["task_input", "concept_planning"],
                importance="high",
                metadata={"task_id": str(task.task_id)}
            )
            
            # Update progress
            await self._update_progress(execution, 10, "Analyzing input", db)
            
            # Retrieve relevant memories from previous tasks
            previous_concepts = await self.retrieve_memories(
                query="concept planning video creative",
                tags=["concept_planning"],
                limit=5
            )
            
            # Update progress
            await self._update_progress(execution, 20, "Loading context", db)
            
            # Prepare variables for prompt template
            template_variables = {
                "user_description": input_data.get("description", ""),
                "video_style": input_data.get("style", "modern"),
                "target_duration": input_data.get("duration", 30),
                "target_audience": input_data.get("target_audience", "general")
            }
            
            # Add context from previous memories if available
            if previous_concepts:
                template_variables["previous_context"] = {
                    "similar_projects": previous_concepts[:3],
                    "lessons_learned": self._extract_lessons_learned(previous_concepts)
                }
            
            # Update progress
            await self._update_progress(execution, 30, "Rendering prompt", db)
            
            # Render the prompt template
            rendered_prompt = self.render_prompt(
                "concept_planner",
                **template_variables
            )
            
            # Update progress
            await self._update_progress(execution, 50, "Generating concept", db)
            
            # Use OpenAI tool to generate concept
            concept_result = await self.use_tool(
                tool_name="openai_client",
                action="chat_completion",
                parameters={
                    "messages": [
                        {
                            "role": "user",
                            "content": rendered_prompt
                        }
                    ],
                    "model": "gpt-4",
                    "temperature": 0.8,
                    "max_tokens": 2000
                }
            )
            
            # Update progress
            await self._update_progress(execution, 70, "Processing response", db)
            
            # Parse the AI response
            concept_content = concept_result.get("content", "")
            
            try:
                # Try to parse as JSON
                concept_data = json.loads(concept_content)
            except json.JSONDecodeError:
                # Fallback: create structured data from text
                concept_data = {
                    "concept_summary": concept_content[:200] + "...",
                    "raw_content": concept_content,
                    "parsing_error": True
                }
            
            # Update progress
            await self._update_progress(execution, 80, "Storing results", db)
            
            # Store the concept in memory with detailed tags
            concept_memory_id = await self.store_memory(
                content=concept_data,
                tags=[
                    "concept_result",
                    "generated_content", 
                    template_variables["video_style"],
                    f"duration_{template_variables['target_duration']}s"
                ],
                importance="high",
                metadata={
                    "task_id": str(task.task_id),
                    "generation_model": "gpt-4",
                    "template_used": "concept_planner",
                    "input_hash": self._hash_input(input_data)
                }
            )
            
            # Update progress
            await self._update_progress(execution, 90, "Finalizing output", db)
            
            # Prepare output with enhanced metadata
            output_data = {
                "concept": concept_data,
                "metadata": {
                    "agent_version": "2.0",
                    "memory_id": concept_memory_id,
                    "processing_time": execution.execution_time,
                    "template_used": "concept_planner",
                    "tool_used": "openai_client",
                    "context_sources": len(previous_concepts)
                }
            }
            
            # Update progress
            await self._update_progress(execution, 100, "Complete", db)
            
            return output_data
            
        except Exception as e:
            # Store error in memory for learning
            await self.store_memory(
                content={
                    "error": str(e),
                    "input_data": input_data,
                    "error_type": type(e).__name__
                },
                tags=["error", "concept_planning", "failure"],
                importance="high",
                metadata={"task_id": str(task.task_id)}
            )
            
            raise
    
    def _extract_lessons_learned(self, previous_concepts: List[Any]) -> List[str]:
        """Extract lessons learned from previous concept planning sessions"""
        lessons = []
        
        for concept in previous_concepts:
            if isinstance(concept, dict):
                # Look for patterns in successful concepts
                if concept.get("metadata", {}).get("success_rating", 0) > 0.8:
                    lessons.append(f"Successful pattern: {concept.get('summary', 'N/A')}")
                
                # Look for common issues
                if "issues" in concept:
                    lessons.append(f"Avoid: {concept['issues']}")
        
        return lessons[:3]  # Return top 3 lessons
    
    def _hash_input(self, input_data: Dict[str, Any]) -> str:
        """Create a hash of input data for deduplication"""
        import hashlib
        import json
        
        # Create a stable string representation
        stable_str = json.dumps(input_data, sort_keys=True)
        return hashlib.md5(stable_str.encode()).hexdigest()
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """Get comprehensive agent status"""
        base_status = {
            "agent_name": self.agent_name,
            "agent_type": self.agent_type.value,
            "available_tools": self.get_available_tools(),
            "prompt_templates": self.get_prompt_templates()
        }
        
        # Add memory statistics
        memory_stats = await self.get_memory_stats()
        base_status["memory_stats"] = memory_stats
        
        # Add tool capabilities
        tool_capabilities = {}
        for tool_name in self.get_available_tools():
            tool_capabilities[tool_name] = self.get_tool_capabilities(tool_name)
        base_status["tool_capabilities"] = tool_capabilities
        
        return base_status