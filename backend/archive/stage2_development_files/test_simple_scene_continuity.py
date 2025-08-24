#!/usr/bin/env python3
"""
简单测试场景连续性分析的JSON解析功能
"""
import asyncio
import json
import os
import sys

# 添加项目路径
sys.path.append('/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend')

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.base_tool import ToolInput

async def test_scene_continuity_json_parsing():
    """直接测试场景连续性分析的JSON解析"""
    
    print("🧪 Testing Scene Continuity JSON Parsing...")
    
    # 初始化智谱AI工具
    zhipu_tool = ZhipuClientTool()
    
    # 构建场景连续性分析提示词(模拟ImageGenerator中的模板)
    analysis_prompt = """你是一个专业的视频制作助手。请分析以下两个场景之间的视觉连续性，并决定应该采用什么图像生成策略。

前一场景 (Scene 3):
- 标题: 金丹稳定
- 描述: 修士盘坐，金丹在丹田中稳定运转，元婴即将成形但尚未完全显现
- 最终状态: 金丹稳定运转，元婴即将成形

当前场景 (Scene 4):
- 标题: 元婴显现  
- 描述: 金丹破碎，元婴完全显现，修士突破到元婴境界
- 初始状态: 金丹破碎，元婴成形

分析维度:
1. 空间连续性：场景是否发生在同一地点？
2. 时间连续性：这是连续的时间进程吗？
3. 主体连续性：是否涉及相同的角色/对象？
4. 叙事连续性：这是同一个故事情节的延续吗？
5. 视觉连续性：视觉元素是否应该保持一致？

请返回以下JSON格式：
{
    "strategy": "continue_from_previous",
    "reasoning": "这是同一修士的突破过程，金丹破碎到元婴显现是直接的状态转换",
    "confidence_score": 0.9,
    "analysis_dimensions": {
        "spatial_continuity": {"consistent": true, "reasoning": "同一修士，同一地点"},
        "temporal_continuity": {"consistent": true, "reasoning": "连续的突破过程"},
        "subject_continuity": {"consistent": true, "reasoning": "同一修士角色"},
        "narrative_continuity": {"consistent": true, "reasoning": "修仙突破的关键时刻"},
        "visual_continuity": {"consistent": true, "reasoning": "应该显示状态转换过程"}
    }
}"""
    
    try:
        print("🔄 测试智谱AI场景连续性分析...")
        
        # 创建工具输入
        tool_input = ToolInput(
            action="generate_text",
            parameters={
                "prompt": analysis_prompt,
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            }
        )
        
        # 执行分析
        result = await zhipu_tool.execute(tool_input)
        
        print(f"✅ 原始结果类型: {type(result)}")
        
        # 模拟ImageGenerator中的解析逻辑
        import json
        
        # 获取内容
        if hasattr(result, 'result') and isinstance(result.result, dict):
            content = result.result.get("content", "")
        elif hasattr(result, 'content'):
            content = result.content
        elif isinstance(result, dict):
            content = result.get("content", "")
        else:
            content = str(result)
        
        print(f"✅ 提取的内容: {content[:200]}...")
        print(f"✅ 内容长度: {len(content)}")
        
        # 使用更新的JSON解析逻辑
        try:
            analysis_data = json.loads(content.strip())
            print("✅ 直接JSON解析成功")
        except json.JSONDecodeError:
            # 降级：尝试提取 ```json``` 包装的JSON
            if "```json" in content and "```" in content:
                import re
                json_match = re.search(r'```json\s*({.*?})\s*```', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    analysis_data = json.loads(json_str)
                    print("✅ 从markdown代码块解析JSON成功")
                else:
                    raise ValueError("Cannot extract JSON from markdown code block")
            else:
                raise ValueError(f"Unable to parse JSON from content: {content[:100]}")
        
        # 验证分析结果
        print(f"\n🎯 场景连续性分析结果:")
        print(f"   策略: {analysis_data.get('strategy')}")
        print(f"   推理: {analysis_data.get('reasoning')}")
        print(f"   置信度: {analysis_data.get('confidence_score')}")
        
        if 'analysis_dimensions' in analysis_data:
            print(f"   分析维度:")
            for dimension, details in analysis_data['analysis_dimensions'].items():
                consistent = details.get('consistent', False)
                reasoning = details.get('reasoning', 'No reasoning provided')
                print(f"     - {dimension}: {'一致' if consistent else '不一致'} ({reasoning})")
        
        # 验证必需字段
        required_fields = ["strategy", "reasoning", "confidence_score"]
        for field in required_fields:
            if field in analysis_data:
                print(f"✅ 字段 '{field}' 存在: {analysis_data[field]}")
            else:
                print(f"❌ 字段 '{field}' 缺失")
        
        print(f"\n✅ JSON解析和场景连续性分析测试成功!")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_scene_continuity_json_parsing())