#!/usr/bin/env python3
"""
简单测试智谱AI的JSON格式支持
"""
import asyncio
import json
import os
import sys

# 添加项目路径
sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput

async def test_zhipu_json_simple():
    """简单测试智谱AI的JSON格式支持"""
    
    print("🧪 Testing Zhipu AI JSON format support (simple)...")
    
    # 初始化工具
    zhipu_tool = ZhipuClientTool()
    
    # 测试提示词
    test_prompt = """请分析以下场景的连续性，并以JSON格式返回结果：

前一场景：修士盘坐，金丹稳定
当前场景：金丹破碎，元婴成形

请返回以下格式的JSON：
{
    "strategy": "continue_from_previous",
    "reasoning": "这是状态演进，金丹破碎到元婴成形是直接的修炼过程",
    "confidence_score": 0.9
}"""
    
    try:
        print("🔄 Testing with response_format: json_object...")
        
        # 创建工具输入
        tool_input = ToolInput(
            action="generate_text",
            parameters={
                "prompt": test_prompt,
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            }
        )
        
        # 执行工具
        result = await zhipu_tool.execute(tool_input)
        
        print(f"✅ Raw result type: {type(result)}")
        print(f"✅ Raw result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")
        
        # 处理 ToolOutput 对象
        if hasattr(result, 'result') and isinstance(result.result, dict):
            content = result.result.get("content", "")
            print(f"✅ ToolOutput.result found with content")
        elif isinstance(result, dict) and "content" in result:
            content = result["content"]
            print(f"✅ Content: {content}")
            print(f"✅ Content type: {type(content)}")
            print(f"✅ Content length: {len(content)}")
            
            # 尝试解析JSON
            try:
                parsed_json = json.loads(content)
                print(f"✅ Successfully parsed JSON!")
                print(f"✅ Parsed data: {json.dumps(parsed_json, indent=2, ensure_ascii=False)}")
                
                # 验证必要字段
                required_fields = ["strategy", "reasoning", "confidence_score"]
                for field in required_fields:
                    if field in parsed_json:
                        print(f"✅ Field '{field}' found: {parsed_json[field]}")
                    else:
                        print(f"❌ Field '{field}' missing")
                        
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing failed: {e}")
                print(f"❌ Content that failed to parse: '{content}'")
                print(f"❌ First 200 chars: '{content[:200]}'")
        else:
            print(f"❌ Unexpected result format: {result}")
            
        if 'content' in locals():
            print(f"✅ Content: {content}")
            print(f"✅ Content type: {type(content)}")
            print(f"✅ Content length: {len(content)}")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_zhipu_json_simple())