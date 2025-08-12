#!/usr/bin/env python3
"""
测试ZhipuClientTool的metadata获取
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_zhipu_metadata():
    """测试ZhipuClientTool元数据"""
    
    print("🧪 测试ZhipuClientTool元数据获取")
    print("=" * 60)
    
    try:
        from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
        
        print("✅ ZhipuClientTool导入成功")
        
        # 测试类方法get_metadata
        print("\n📋 测试get_metadata类方法")
        print("-" * 40)
        
        metadata = ZhipuClientTool.get_metadata()
        print(f"✅ 元数据获取成功")
        print(f"   - 名称: {metadata.name}")
        print(f"   - 版本: {metadata.version}")
        print(f"   - 类型: {metadata.tool_type}")
        print(f"   - 描述: {metadata.description}")
        
        # 测试工具注册
        print("\n📋 测试工具注册")
        print("-" * 40)
        
        from app.agents.tools.tool_registry import get_tool_registry
        
        tool_registry = get_tool_registry()
        
        # 手动注册
        registered_name = tool_registry.register_tool(ZhipuClientTool)
        print(f"✅ 工具注册成功: {registered_name}")
        
        # 检查是否在注册表中
        all_tools = tool_registry.list_tools()
        if "zhipu_client" in all_tools:
            print(f"✅ zhipu_client在工具列表中")
        else:
            print(f"❌ zhipu_client不在工具列表中")
            print(f"   可用工具: {all_tools}")
        
        # 尝试获取工具
        try:
            tool = tool_registry.get_tool("zhipu_client")
            print(f"✅ 工具获取成功: {type(tool).__name__}")
        except Exception as e:
            print(f"❌ 工具获取失败: {e}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_zhipu_metadata()