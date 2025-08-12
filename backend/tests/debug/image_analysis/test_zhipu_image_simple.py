#!/usr/bin/env python3
"""
简单测试智谱AI的图像分析功能
"""

import asyncio
import os
import sys
import base64
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool

async def test_zhipu_image_analysis():
    """直接测试智谱AI的图像分析"""
    
    # 图片文件路径
    image_path = "/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/storage/generated/scene_5_first_frame.jpg"
    
    # 检查文件是否存在
    if not os.path.exists(image_path):
        print(f"❌ 图片文件不存在: {image_path}")
        return
    
    # 将图片转换为base64
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{image_base64}"
        print(f"🔍 图片已读取，大小: {len(image_data)} bytes")
    except Exception as e:
        print(f"❌ 读取图片失败: {str(e)}")
        return
    
    # 创建工具实例
    try:
        tool = ZhipuClientTool()
        print("✅ 智谱AI工具创建成功")
    except Exception as e:
        print(f"❌ 创建智谱AI工具失败: {str(e)}")
        return
    
    # 准备分析提示词
    analysis_prompt = """
请详细描述这张图像中的内容，特别关注：

1. 物体位置和状态：所有物体（特别是刀具、水果）的具体位置和当前状态
2. 准备状态：是否有任何物体处于"即将进行某动作"的状态
3. 空间关系：各个元素之间的相对位置关系
4. 视觉细节：光线、背景、材质等环境细节

这是关于"切西瓜场景"的视频首帧图像。

请用一段话描述图像的实际内容，重点说明刀具和待切物体的当前确切状态和位置。
"""
    
    # 构建输入参数
    from app.agents.tools.base_tool import ToolInput
    
    tool_input = ToolInput(
        action="analyze_image",
        parameters={
            "image_url": image_url,
            "prompt": analysis_prompt,
            "temperature": 0.3
        }
    )
    
    print("-" * 60)
    print("🔍 开始调用智谱AI进行图像分析...")
    
    try:
        # 执行图像分析
        result = await tool.execute(tool_input)
        
        print("✅ 图像分析完成！")
        print()
        print("📋 分析结果：")
        
        # 处理结果
        if hasattr(result, 'result') and isinstance(result.result, dict):
            content = result.result.get("content", "")
            print(content)
        elif hasattr(result, 'content'):
            print(result.content)
        else:
            print(f"结果格式: {type(result)}")
            print(f"结果内容: {result}")
            
        print()
        print("-" * 60)
        
    except Exception as e:
        print(f"❌ 图像分析失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_zhipu_image_analysis())