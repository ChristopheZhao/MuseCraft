#!/usr/bin/env python3
"""
测试环境变量加载是否正常
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_env_loading():
    """测试环境变量加载"""
    
    print("🧪 测试环境变量加载")
    print("=" * 60)
    
    # 测试直接从环境变量读取
    print("\n📋 直接环境变量检查")
    print("-" * 40)
    
    env_vars = [
        "GLM_API_KEY",
        "OPENAI_API_KEY", 
        "STABILITY_API_KEY",
        "KIMI_API_KEY"
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # 只显示前几个字符以保护隐私
            masked_value = f"{value[:8]}..." if len(value) > 8 else "短密钥"
            print(f"✅ {var}: {masked_value}")
        else:
            print(f"❌ {var}: 未设置")
    
    # 测试通过settings加载
    print("\n📋 通过Settings配置加载")
    print("-" * 40)
    
    try:
        from app.core.config import settings
        
        api_keys = {
            "GLM_API_KEY": settings.GLM_API_KEY,
            "OPENAI_API_KEY": settings.OPENAI_API_KEY,
            "STABILITY_API_KEY": settings.STABILITY_API_KEY,
            "KIMI_API_KEY": settings.KIMI_API_KEY
        }
        
        for key_name, key_value in api_keys.items():
            if key_value:
                masked_value = f"{key_value[:8]}..." if len(key_value) > 8 else "短密钥"
                print(f"✅ {key_name}: {masked_value}")
            else:
                print(f"❌ {key_name}: 未设置")
        
        print("\n📋 设置加载成功")
        
    except Exception as e:
        print(f"❌ Settings加载失败: {e}")
    
    print("\n🎊 环境变量测试完成!")

if __name__ == "__main__":
    test_env_loading()