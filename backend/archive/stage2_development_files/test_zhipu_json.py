#!/usr/bin/env python3
"""
测试智谱AI的JSON格式支持
"""
import asyncio
import json
import os
import sys

# 添加项目路径
sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool

async def test_zhipu_json_support():
    """测试智谱AI的JSON格式支持"""
    
    print("🧪 Testing Zhipu AI JSON format support...")
    
    # 初始化客户端
    zhipu_tool = ZhipuClientTool()
    
    # 测试提示词
    test_prompt = """
    请分析以下场景的连续性，并以JSON格式返回结果：
    
    前一场景：修士盘坐，金丹稳定
    当前场景：金丹破碎，元婴成形
    
    请返回以下格式的JSON：
    {
        "strategy": "continue_from_previous" 或 "new_image",
        "reasoning": "分析理由",
        "confidence_score": 0.8,
        "analysis_dimensions": {
            "narrative_continuity": {"consistent": true, "reasoning": "具体分析"}
        }
    }
    """
    
    try:
        print("🔄 Testing with response_format: json_object...")
        
        # 测试JSON格式请求
        result = await zhipu_tool.execute(
            action="generate_text",
            parameters={
                "prompt": test_prompt,
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            }
        )
        
        print(f"✅ Raw result type: {type(result)}")
        print(f"✅ Raw result: {result}")
        
        if "content" in result:
            content = result["content"]
            print(f"✅ Content type: {type(content)}")
            print(f"✅ Content: {content}")
            
            # 尝试解析JSON
            try:
                parsed_json = json.loads(content)
                print(f"✅ Successfully parsed JSON: {parsed_json}")
                
                # 验证必要字段
                if "strategy" in parsed_json:
                    print(f"✅ Strategy field found: {parsed_json['strategy']}")
                else:
                    print("⚠️  Strategy field missing")
                    
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing failed: {e}")
                print(f"❌ Content that failed to parse: '{content}'")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        
    # 对比测试：不使用JSON格式
    try:
        print("\n🔄 Testing without response_format (baseline)...")
        
        result_baseline = await zhipu_tool.execute(
            action="generate_text",
            parameters={
                "prompt": test_prompt,
                "temperature": 0.3
            }
        )
        
        print(f"✅ Baseline result: {result_baseline}")
        
    except Exception as e:
        print(f"❌ Baseline test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_zhipu_json_support())