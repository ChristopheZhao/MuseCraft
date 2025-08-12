#!/usr/bin/env python3
"""
测试工具注册是否正常工作
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_tool_registration():
    """测试Agent工具注册"""
    
    print("🔧 测试Agent工具注册")
    print("=" * 60)
    
    # 首先注册默认工具
    print("\n📋 预先注册工具")
    print("-" * 40)
    
    try:
        from app.agents.tools import register_default_tools
        register_default_tools()
        print("✅ 默认工具注册完成")
    except Exception as e:
        print(f"❌ 工具注册失败: {e}")
    
    # 测试ImageGenerator工具注册
    print("\n📋 测试ImageGenerator工具注册")
    print("-" * 40)
    
    try:
        from app.agents.image_generator import ImageGeneratorAgent
        
        image_generator = ImageGeneratorAgent()
        print(f"✅ ImageGenerator初始化成功")
        
        # 检查工具是否加载
        available_tools = list(image_generator._available_tools.keys())
        print(f"✅ 可用工具: {available_tools}")
        
        # 检查关键工具
        required_tools = ["zhipu_client", "openai_client", "image_generation_client"]
        missing_tools = [tool for tool in required_tools if tool not in available_tools]
        
        if missing_tools:
            print(f"❌ 缺少工具: {missing_tools}")
        else:
            print(f"✅ 所有必需工具已加载")
            
        # 测试是否可以访问zhipu_client
        if "zhipu_client" in image_generator._available_tools:
            zhipu_tool = image_generator._available_tools["zhipu_client"]
            print(f"✅ zhipu_client工具可用: {type(zhipu_tool).__name__}")
        else:
            print(f"❌ zhipu_client工具不可用")
        
    except Exception as e:
        print(f"❌ ImageGenerator测试失败: {e}")
    
    # 测试VideoGenerator工具注册
    print("\n📋 测试VideoGenerator工具注册")
    print("-" * 40)
    
    try:
        from app.agents.video_generator import VideoGeneratorAgent
        
        video_generator = VideoGeneratorAgent()
        print(f"✅ VideoGenerator初始化成功")
        
        # 检查工具是否加载
        available_tools = list(video_generator._available_tools.keys())
        print(f"✅ 可用工具: {available_tools}")
        
        # 检查关键工具
        if "zhipu_client" in video_generator._available_tools:
            zhipu_tool = video_generator._available_tools["zhipu_client"]
            print(f"✅ zhipu_client工具可用: {type(zhipu_tool).__name__}")
        else:
            print(f"❌ zhipu_client工具不可用")
        
    except Exception as e:
        print(f"❌ VideoGenerator测试失败: {e}")
    
    # 测试工具注册表
    print("\n📋 测试工具注册表")
    print("-" * 40)
    
    try:
        from app.agents.tools.tool_registry import get_tool_registry
        from app.agents.tools import register_default_tools
        
        # 先注册默认工具
        register_default_tools()
        print("✅ 默认工具注册完成")
        
        tool_registry = get_tool_registry()
        all_tools = tool_registry.list_tools()
        
        print(f"✅ 工具注册表可用")
        print(f"✅ 注册的工具数量: {len(all_tools)}")
        
        # 显示所有可用工具
        for tool_name in all_tools:
            try:
                tool = tool_registry.get_tool(tool_name)
                print(f"   - {tool_name}: {type(tool).__name__}")
            except Exception as e:
                print(f"   - {tool_name}: 加载失败 ({e})")
        
        # 检查核心工具
        core_tools = ["zhipu_client", "openai_client", "image_generation_client"]
        for tool_name in core_tools:
            if tool_name in all_tools:
                print(f"✅ {tool_name} 已注册")
            else:
                print(f"❌ {tool_name} 未注册")
    
    except Exception as e:
        print(f"❌ 工具注册表测试失败: {e}")
    
    print("\n🎊 工具注册测试完成!")

async def main():
    await test_tool_registration()

if __name__ == "__main__":
    asyncio.run(main())