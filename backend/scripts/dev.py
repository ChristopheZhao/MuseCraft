#!/usr/bin/env python3
"""
使用uv环境启动开发服务器
"""
import subprocess
import sys
from pathlib import Path

def main():
    # 确保在项目根目录
    project_root = Path(__file__).parent.parent
    
    print("🚀 启动开发环境...")
    print("=" * 50)
    
    # 使用uv运行开发服务器
    try:
        subprocess.run([
            "uv", "run", "python", "scripts/start_dev.py"
        ], cwd=project_root, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n🛑 开发服务器已停止")

if __name__ == "__main__":
    main()
