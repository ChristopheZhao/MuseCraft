#!/usr/bin/env python3
"""
使用uv环境运行测试
"""
import subprocess
import sys
from pathlib import Path

def main():
    project_root = Path(__file__).parent.parent
    
    print("🧪 运行测试...")
    print("=" * 50)
    
    # 使用uv运行测试
    try:
        subprocess.run([
            "uv", "run", "pytest", "-v", "--cov=app", "--cov-report=html"
        ], cwd=project_root, check=True)
        
        print("\n📊 测试报告生成在 htmlcov/index.html")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
