"""
DEPRECATION NOTICE (archived)
This example is archived. Do not import in production.
"""
import warnings as _warnings
raise ImportError(
    "Archived example module 'function_call_agent_example'. Do not import in production."
)

import json
import logging
from typing import Dict, Any, List, Optional

from .tools.ai_services.service_interfaces import get_llm_service
from .tools.tool_registry import get_tool_registry


class FunctionCallAgentExample:
    """
    Function Call Agent示例
    
    演示如何正确使用GLM-4-plus的原生Function Call能力：
    1. Agent获取所有可用工具的schema
    2. LLM根据tools列表自主选择工具和参数
    3. Agent执行LLM选择的工具调用
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.llm_service = get_llm_service()
        self.tool_registry = get_tool_registry()
        
        # 注册可用工具
        self.available_tools = [
            "video_generation",
            "scene_analysis", 
            "image_generation"
        ]
    
    async def process_video_scene(self, scene_data: Dict[str, Any], user_requirements: str) -> Dict[str, Any]:
        """
        处理视频场景 - 使用Function Call让LLM选择最佳工具和参数
        """
        
        # Step 1: 构建工具schema列表
        tools_schema = self._build_tools_schema()
        
        # Step 2: 构建上下文消息
        messages = [
            {
                "role": "system",
                "content": """你是视频生成专家，负责根据场景内容和用户需求选择最合适的工具和参数。

可用工具说明：
- video_generation: 生成视频，需要prompt和duration参数
- scene_analysis: 分析场景复杂度和特征
- image_generation: 生成图像

请根据场景内容智能选择工具调用顺序和参数。"""
            },
            {
                "role": "user",
                "content": f"""
场景数据：
脚本：{scene_data.get('script_text', '')}
视觉描述：{scene_data.get('visual_description', '')}
叙事描述：{scene_data.get('narrative_description', '')}

用户需求：{user_requirements}

请分析这个场景并选择合适的工具来处理。
"""
            }
        ]
        
        # Step 3: 使用GLM-4-plus的Function Call
        try:
            llm_response = await self.llm_service.function_call(
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                model="glm-4-plus",
                temperature=0.3
            )
            
            # Step 4: 解析和执行Function Call
            if llm_response.get("has_function_call") and llm_response.get("tool_calls"):
                results = []
                
                for tool_call in llm_response["tool_calls"]:
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"]["arguments"])
                    
                    self.logger.info(f"🤖 LLM选择调用工具: {function_name}")
                    self.logger.info(f"📋 参数: {function_args}")
                    
                    # 执行工具调用
                    tool_result = await self._execute_tool_call(function_name, function_args)
                    results.append({
                        "tool": function_name,
                        "args": function_args,
                        "result": tool_result
                    })
                
                return {
                    "success": True,
                    "llm_reasoning": "LLM通过Function Call智能选择了工具",
                    "tool_calls": results,
                    "model_used": llm_response.get("model"),
                    "usage": llm_response.get("usage", {})
                }
            
            else:
                # LLM没有选择工具调用，返回文本响应
                return {
                    "success": False,
                    "message": "LLM没有选择工具调用",
                    "llm_response": llm_response.get("content", ""),
                    "model_used": llm_response.get("model")
                }
        
        except Exception as e:
            self.logger.error(f"Function Call failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_tools_schema(self) -> List[Dict[str, Any]]:
        """构建工具schema列表 - 供LLM进行Function Call"""
        
        tools_schema = []
        
        for tool_name in self.available_tools:
            try:
                # 获取工具实例
                tool = self.tool_registry.get_tool(tool_name)
                if tool is None:
                    continue
                
                # 获取工具的所有action schema
                actions = tool.get_available_actions()
                
                for action in actions:
                    action_schema = tool.get_action_schema(action)
                    if action_schema:
                        # 转换为标准Function Call格式
                        function_schema = {
                            "type": "function",
                            "function": {
                                "name": f"{tool_name}_{action}",
                                "description": f"{tool.get_metadata().description} - {action}",
                                "parameters": action_schema
                            }
                        }
                        tools_schema.append(function_schema)
                
            except Exception as e:
                self.logger.warning(f"Failed to build schema for tool {tool_name}: {e}")
        
        return tools_schema
    
    async def _execute_tool_call(self, function_name: str, function_args: Dict[str, Any]) -> Dict[str, Any]:
        """执行LLM选择的工具调用"""
        
        # 解析工具名称和action
        if "_" in function_name:
            tool_name, action = function_name.rsplit("_", 1)
        else:
            raise ValueError(f"Invalid function name format: {function_name}")
        
        # 获取工具实例
        tool = self.tool_registry.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool {tool_name} not found")
        
        # 执行工具
        from .tools.base_tool import ToolInput
        tool_input = ToolInput(
            action=action,
            parameters=function_args
        )
        
        result = await tool.execute(tool_input)
        return result
    
    async def demo_scenario_analysis(self) -> Dict[str, Any]:
        """演示场景：让LLM分析一个复杂场景并选择合适的处理方式"""
        
        demo_scene = {
            "script_text": "主角在雨夜中快速奔跑，追逐着前方的神秘身影。雷声轰鸣，闪电照亮了狭窄的巷道。",
            "visual_description": "昏暗的雨夜，湿润的街道反射着霓虹灯光。主角身影在雨中穿梭，动作敏捷而紧张。",
            "narrative_description": "这是故事的高潮部分，主角即将揭开重要的谜团。节奏紧张，气氛压抑。"
        }
        
        user_requirements = "生成一个紧张刺激的追逐场景视频，时长要足够展现动作的精彩"
        
        result = await self.process_video_scene(demo_scene, user_requirements)
        
        print("🎬 Function Call Demo结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        return result


# 使用示例
async def demo_function_call():
    """演示Function Call的使用"""
    
    agent = FunctionCallAgentExample()
    result = await agent.demo_scenario_analysis()
    
    if result["success"]:
        print("✅ Function Call成功执行")
        for tool_call in result["tool_calls"]:
            print(f"🔧 工具: {tool_call['tool']}")
            print(f"📋 参数: {tool_call['args']}")
            print(f"📊 结果: {tool_call['result']}")
    else:
        print("❌ Function Call执行失败")
        print(f"错误: {result.get('error', result.get('message'))}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_function_call())
