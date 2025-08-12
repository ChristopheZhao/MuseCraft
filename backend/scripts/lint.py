#!/usr/bin/env python3
"""
使用uv环境进行代码质量检查
"""
import subprocess
import sys
from pathlib import Path

def main():
    project_root = Path(__file__).parent.parent
    
    print("🔍 代码质量检查...")
    print("=" * 50)
    
    checks = [
        ("代码格式化", ["uv", "run", "black", "app", "scripts"]),
        ("导入排序", ["uv", "run", "isort", "app", "scripts"]),
        ("语法检查", ["uv", "run", "flake8", "app"]),
        ("类型检查", ["uv", "run", "mypy", "app"]),
    ]
    
    failed = []
    
    for name, cmd in checks:
        print(f"\n🔍 {name}...")
        try:
            subprocess.run(cmd, cwd=project_root, check=True)
            print(f"✓ {name}通过")
        except subprocess.CalledProcessError:
            print(f"❌ {name}失败")
            failed.append(name)
    
    if failed:
        print(f"\n❌ 以下检查失败: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("\n🎉 所有代码质量检查通过!")

if __name__ == "__main__":
    main()
