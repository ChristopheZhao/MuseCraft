#!/usr/bin/env python3
"""
直接测试智谱AI图像分析功能，不经过Agent
"""
import asyncio
import os
import sys
import base64
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_direct_image_analysis():
    """直接调用智谱AI图像分析工具"""
    
    print("🔍 直接测试智谱AI图像分析功能")
    print("=" * 50)
    
    # 图片路径
    image_path = "./storage/generated/scene_5_first_frame.jpg"
    
    # 检查文件
    if not os.path.exists(image_path):
        print(f"❌ 图片不存在: {image_path}")
        return
    
    print(f"✅ 图片存在: {image_path}")
    
    # 读取图片并转换为base64
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{image_base64}"
        print(f"📁 图片大小: {len(image_data)} bytes")
    except Exception as e:
        print(f"❌ 读取图片失败: {str(e)}")
        return
    
    # 分析提示词 - 专门针对切菜场景的关键实体定位
    analysis_prompt = """这是一个切西瓜的厨房场景图片。请作为视频制作助手，精确描述关键实体的位置和状态：

**关键任务：寻找和定位刀具**
1. 图中有几把刀？每把刀的具体位置在哪里？
2. 刀是在西瓜的左边、右边、上方、下方，还是直接放在西瓜上？
3. 刀与西瓜的距离：紧挨着、稍微分开、相距较远？
4. 刀的状态：平放在台面、插在西瓜里、悬空、还是被手握着？

**西瓜状态描述**
5. 西瓜是完整的，还是已经被切开？如果切开了，切成几块？
6. 西瓜块的排列方式和位置？

**输出格式**：
请用"刀在西瓜的[具体位置]，距离[具体距离]，状态是[具体状态]"的格式回答。

这是为了避免视频中出现重复的刀具，需要准确知道现有刀具的位置。"""
    
    print(f"📝 分析提示词: {analysis_prompt[:100]}...")
    
    try:
        # 直接导入并使用工具
        from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
        from app.agents.tools.base_tool import ToolInput
        
        # 创建工具实例
        tool = ZhipuClientTool()
        print("✅ 智谱AI工具创建成功")
        
        # 创建工具输入 - 尝试不同参数
        tool_input = ToolInput(
            action="analyze_image",
            parameters={
                "image_url": image_url,
                "prompt": analysis_prompt,
                "temperature": 0.7,  # 提高creativity
                "model": "glm-4v"   # 明确指定模型
            }
        )
        
        print("\n🔍 开始图像分析...")
        print("-" * 40)
        
        # 执行分析
        result = await tool.execute(tool_input)
        
        print("✅ 图像分析完成！")
        print()
        
        # 详细调试结果
        print(f"📋 结果类型: {type(result)}")
        print(f"📋 结果属性: {dir(result) if hasattr(result, '__dict__') else 'No __dict__'}")
        
        if hasattr(result, 'result'):
            print(f"📋 result.result 类型: {type(result.result)}")
            print(f"📋 result.result 内容: {result.result}")
        
        if hasattr(result, 'content'):
            print(f"📋 result.content 类型: {type(result.content)}")
            print(f"📋 result.content 内容: {result.content}")
        
        if hasattr(result, 'success'):
            print(f"📋 result.success: {result.success}")
        
        if hasattr(result, 'error'):
            print(f"📋 result.error: {result.error}")
        
        # 处理结果 - 正确提取analysis字段
        if hasattr(result, 'result') and isinstance(result.result, dict):
            content = result.result.get("analysis", "")
            if not content:
                content = result.result.get("content", "")
            print("📋 提取的分析结果：")
            print(content)
        elif hasattr(result, 'content'):
            print("📋 提取的分析结果：")
            print(result.content)
        else:
            print(f"📋 原始结果：{result}")
        
        print()
        print("-" * 50)
        
    except Exception as e:
        print(f"❌ 图像分析失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct_image_analysis())