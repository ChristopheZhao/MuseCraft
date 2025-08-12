"""
Usage examples for the enhanced agent architecture
"""

import asyncio
import json
from typing import Dict, Any

from ..tools.tool_registry import get_tool_registry
from ..memory.memory_manager import MemoryManager
from ..prompts.template_manager import get_template_manager
from .enhanced_concept_planner import EnhancedConceptPlannerAgent


async def demonstrate_tool_usage():
    """Demonstrate standalone tool usage"""
    print("=== Tool Usage Example ===")
    
    # Get tool registry
    tool_registry = get_tool_registry()
    
    # List available tools
    available_tools = tool_registry.list_tools()
    print(f"Available tools: {available_tools}")
    
    # Get a specific tool
    if "openai_client" in available_tools:
        openai_tool = tool_registry.get_tool("openai_client")
        
        # Show tool capabilities
        capabilities = openai_tool.get_available_actions()
        print(f"OpenAI tool capabilities: {capabilities}")
        
        # Use the tool
        from ..tools.base_tool import ToolInput
        tool_input = ToolInput(
            action="chat_completion",
            parameters={
                "messages": [
                    {"role": "user", "content": "Hello, how are you?"}
                ],
                "model": "gpt-3.5-turbo",
                "max_tokens": 50
            }
        )
        
        try:
            result = await openai_tool.execute(tool_input)
            print(f"Tool result: {result.get('content', 'No content')[:100]}...")
        except Exception as e:
            print(f"Tool execution failed: {e}")


async def demonstrate_memory_usage():
    """Demonstrate memory management"""
    print("\n=== Memory Usage Example ===")
    
    # Create memory manager
    memory_manager = MemoryManager(config={
        "short_term_ttl": 3600,
        "enable_consolidation": False  # Disable for demo
    })
    
    # Store some memories
    memory_id1 = await memory_manager.store_memory(
        content="This is a test memory about video generation",
        tags=["test", "video", "generation"],
        agent_id="demo_agent"
    )
    print(f"Stored memory 1: {memory_id1}")
    
    memory_id2 = await memory_manager.store_memory(
        content="Another memory about creative concepts",
        tags=["test", "creative", "concepts"],
        agent_id="demo_agent",
        importance="high"
    )
    print(f"Stored memory 2: {memory_id2}")
    
    # Search memories
    memories = await memory_manager.search_memories(
        query="video creative",
        agent_id="demo_agent",
        limit=5
    )
    print(f"Found {len(memories)} memories")
    for memory in memories:
        print(f"  - {memory.content[:50]}... (tags: {memory.tags})")
    
    # Get statistics
    stats = await memory_manager.get_memory_stats()
    print(f"Memory stats: {stats}")


async def demonstrate_prompt_templates():
    """Demonstrate prompt template usage"""
    print("\n=== Prompt Template Example ===")
    
    # Get template manager
    template_manager = get_template_manager()
    
    # List available templates
    templates = template_manager.list_templates()
    print(f"Available templates: {templates}")
    
    # Use concept planner template
    if "concept_planner" in templates:
        variables = {
            "user_description": "Create a tech product demonstration video",
            "video_style": "modern",
            "target_duration": 30,
            "target_audience": "tech professionals"
        }
        
        rendered_prompt = template_manager.render_template(
            "concept_planner", 
            variables
        )
        print(f"Rendered prompt length: {len(rendered_prompt)} characters")
        print(f"First 200 chars: {rendered_prompt[:200]}...")
    
    # Show template metadata
    if "concept_planner" in templates:
        metadata = template_manager.get_template_metadata("concept_planner")
        print(f"Template metadata: {metadata.name} v{metadata.version}")
        print(f"Description: {metadata.description}")
        print(f"Required variables: {metadata.variables}")


async def demonstrate_enhanced_agent():
    """Demonstrate enhanced agent usage"""
    print("\n=== Enhanced Agent Example ===")
    
    # Create enhanced agent
    agent = EnhancedConceptPlannerAgent()
    
    # Show agent status
    status = await agent.get_agent_status()
    print(f"Agent: {status['agent_name']}")
    print(f"Tools: {status['available_tools']}")
    print(f"Templates: {status['prompt_templates']}")
    
    # Test memory operations
    memory_id = await agent.store_memory(
        content="Test concept: futuristic city visualization",
        tags=["concept", "futuristic", "city"],
        importance="medium"
    )
    print(f"Stored concept memory: {memory_id}")
    
    # Retrieve memories
    retrieved = await agent.retrieve_memories(
        query="concept futuristic",
        limit=3
    )
    print(f"Retrieved {len(retrieved)} memories")
    
    # Test prompt rendering
    try:
        prompt = await agent.render_prompt(
            "concept_planner",
            {
                "user_description": "Sci-fi short film about AI",
                "video_style": "cinematic",
                "target_duration": 60,
                "target_audience": "sci-fi enthusiasts"
            }
        )
        print(f"Rendered prompt: {len(prompt)} characters")
    except Exception as e:
        print(f"Prompt rendering error: {e}")


async def demonstrate_integration():
    """Demonstrate full integration example"""
    print("\n=== Full Integration Example ===")
    
    # This would normally be called in a real task execution
    # Here we simulate the key components working together
    
    agent = EnhancedConceptPlannerAgent()
    
    # Simulate task input
    task_input = {
        "description": "Create an engaging video about sustainable technology",
        "style": "professional",
        "duration": 45,
        "target_audience": "business professionals"
    }
    
    print("Simulating enhanced concept planning process...")
    
    # 1. Store input in memory
    input_memory_id = await agent.store_memory(
        content=task_input,
        tags=["task_input", "sustainable_tech"],
        importance="high"
    )
    print(f"1. Stored input: {input_memory_id}")
    
    # 2. Retrieve relevant context
    context_memories = await agent.retrieve_memories(
        query="technology professional video",
        tags=["concept_planning"],
        limit=3
    )
    print(f"2. Retrieved context: {len(context_memories)} memories")
    
    # 3. Render prompt template
    template_vars = {
        **task_input,
        "user_description": task_input["description"],
        "video_style": task_input["style"],
        "target_duration": task_input["duration"]
    }
    
    prompt = await agent.render_prompt("concept_planner", template_vars)
    print(f"3. Rendered prompt: {len(prompt)} characters")
    
    # 4. Simulate tool usage (without actual API call)
    print("4. Would use OpenAI tool to generate concept")
    
    # 5. Store result
    result_memory_id = await agent.store_memory(
        content={
            "concept_summary": "Professional sustainable technology showcase",
            "visual_style": "clean, modern, green-focused",
            "key_messages": ["innovation", "sustainability", "future"]
        },
        tags=["concept_result", "sustainable_tech", "professional"],
        importance="high"
    )
    print(f"5. Stored result: {result_memory_id}")
    
    print("Integration example completed successfully!")


async def main():
    """Run all examples"""
    print("🚀 Agent Architecture Examples\n")
    
    try:
        await demonstrate_tool_usage()
        await demonstrate_memory_usage()
        await demonstrate_prompt_templates()
        await demonstrate_enhanced_agent()
        await demonstrate_integration()
        
        print("\n✅ All examples completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())