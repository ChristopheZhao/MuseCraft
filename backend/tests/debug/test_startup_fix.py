#!/usr/bin/env python3
"""
测试启动修复是否成功
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_startup_fix():
    """测试启动修复"""
    
    print("🧪 测试启动修复")
    print("=" * 60)
    
    # 测试工具注册
    print("\n📋 测试工具注册初始化")
    print("-" * 40)
    
    try:
        from app.agents.tools import register_default_tools
        
        print("🔧 开始注册默认工具...")
        register_default_tools()
        print("✅ 默认工具注册成功！")
        
        # 检查工具注册表
        from app.agents.tools.tool_registry import get_tool_registry
        
        tool_registry = get_tool_registry()
        all_tools = tool_registry.list_tools()
        
        print(f"\n📊 工具注册统计:")
        print(f"   - 注册的工具数量: {len(all_tools)}")
        
        # 显示所有注册的工具
        print(f"\n📋 已注册的工具:")
        for tool_name in sorted(all_tools):
            try:
                tool = tool_registry.get_tool(tool_name)
                tool_type = type(tool).__name__
                print(f"   ✅ {tool_name}: {tool_type}")
            except Exception as e:
                print(f"   ❌ {tool_name}: 获取失败 ({e})")
        
        # 测试关键工具
        key_tools = ["zhipu_client", "openai_client", "image_generation_client", "jimeng_image", "kimi_client"]
        
        print(f"\n🔑 关键工具检查:")
        for tool_name in key_tools:
            if tool_name in all_tools:
                try:
                    tool = tool_registry.get_tool(tool_name)
                    print(f"   ✅ {tool_name}: 可用")
                except Exception as e:
                    print(f"   ⚠️ {tool_name}: 注册但不可用 ({e})")
            else:
                print(f"   ❌ {tool_name}: 未注册")
        
        print(f"\n🎊 工具注册测试成功！")
        return True
        
    except Exception as e:
        print(f"❌ 工具注册测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_startup_fix()
    if success:
        print("\n🚀 启动修复验证成功！系统可以正常启动了。")
    else:
        print("\n💥 启动修复验证失败！需要进一步调试。")