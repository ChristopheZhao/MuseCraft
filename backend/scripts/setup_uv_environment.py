#!/usr/bin/env python3
"""
使用uv设置Python开发环境
uv是一个极快的Python包管理器和项目管理器
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def check_uv_installed():
    """检查uv是否已安装"""
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ uv已安装: {result.stdout.strip()}")
            return True
        else:
            return False
    except FileNotFoundError:
        return False

def install_uv():
    """安装uv包管理器"""
    print("📦 安装uv包管理器...")
    
    system = platform.system().lower()
    
    if system == "windows":
        # Windows安装
        install_cmd = [
            "powershell", "-c", 
            "irm https://astral.sh/uv/install.ps1 | iex"
        ]
    else:
        # Unix-like系统安装
        install_cmd = [
            "curl", "-LsSf", "https://astral.sh/uv/install.sh", "|", "sh"
        ]
    
    try:
        if system == "windows":
            subprocess.run(install_cmd, check=True)
        else:
            # 对于Unix系统，使用shell执行
            subprocess.run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True, check=True)
            
        print("✓ uv安装成功")
        
        # 提醒用户重新加载shell或添加到PATH
        if system != "windows":
            print("⚠️  请运行以下命令或重启终端以使uv可用:")
            print("   source $HOME/.cargo/env")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ uv安装失败: {e}")
        return False

def setup_python_environment():
    """设置Python环境"""
    print("🐍 设置Python环境...")
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    try:
        # 使用uv创建虚拟环境并安装依赖
        print("创建虚拟环境...")
        subprocess.run(["uv", "venv"], check=True)
        
        print("安装生产依赖...")
        subprocess.run(["uv", "pip", "install", "-e", "."], check=True)
        
        print("安装开发依赖...")
        subprocess.run(["uv", "pip", "install", "-e", ".[dev]"], check=True)
        
        print("✓ Python环境设置完成")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Python环境设置失败: {e}")
        return False

def create_activation_scripts():
    """创建环境激活脚本"""
    print("📝 创建环境激活脚本...")
    
    project_root = Path(__file__).parent.parent
    scripts_dir = project_root / "scripts"
    
    # Windows激活脚本
    windows_script = scripts_dir / "activate.bat"
    with open(windows_script, 'w') as f:
        f.write("""@echo off
echo 🚀 激活Python环境...
call .venv\\Scripts\\activate
echo ✓ 环境已激活
echo.
echo 📋 可用命令:
echo   uv pip install <package>     - 安装包
echo   uv pip list                  - 列出已安装包
echo   python scripts/start_dev.py  - 启动开发服务器
echo   pytest                       - 运行测试
echo   black .                      - 代码格式化
echo   mypy app                     - 类型检查
echo.
""")
    
    # Unix激活脚本
    unix_script = scripts_dir / "activate.sh"
    with open(unix_script, 'w') as f:
        f.write("""#!/bin/bash
echo "🚀 激活Python环境..."
source .venv/bin/activate
echo "✓ 环境已激活"
echo ""
echo "📋 可用命令:"
echo "  uv pip install <package>     - 安装包"
echo "  uv pip list                  - 列出已安装包"
echo "  python scripts/start_dev.py  - 启动开发服务器"  
echo "  pytest                       - 运行测试"
echo "  black .                      - 代码格式化"
echo "  mypy app                     - 类型检查"
echo ""
""")
    
    # 设置执行权限
    if platform.system() != "Windows":
        os.chmod(unix_script, 0o755)
    
    print("✓ 激活脚本创建完成")

def create_dev_scripts():
    """创建开发脚本"""
    print("🛠️ 创建开发脚本...")
    
    project_root = Path(__file__).parent.parent
    scripts_dir = project_root / "scripts"
    
    # 开发服务器启动脚本
    dev_script = scripts_dir / "dev.py"
    with open(dev_script, 'w') as f:
        f.write("""#!/usr/bin/env python3
\"\"\"
使用uv环境启动开发服务器
\"\"\"
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
        print("\\n🛑 开发服务器已停止")

if __name__ == "__main__":
    main()
""")
    
    # 测试运行脚本
    test_script = scripts_dir / "test.py"
    with open(test_script, 'w') as f:
        f.write("""#!/usr/bin/env python3
\"\"\"
使用uv环境运行测试
\"\"\"
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
        
        print("\\n📊 测试报告生成在 htmlcov/index.html")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
""")
    
    # 代码质量检查脚本
    lint_script = scripts_dir / "lint.py"
    with open(lint_script, 'w') as f:
        f.write("""#!/usr/bin/env python3
\"\"\"
使用uv环境进行代码质量检查
\"\"\"
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
        print(f"\\n🔍 {name}...")
        try:
            subprocess.run(cmd, cwd=project_root, check=True)
            print(f"✓ {name}通过")
        except subprocess.CalledProcessError:
            print(f"❌ {name}失败")
            failed.append(name)
    
    if failed:
        print(f"\\n❌ 以下检查失败: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("\\n🎉 所有代码质量检查通过!")

if __name__ == "__main__":
    main()
""")
    
    # 设置执行权限
    if platform.system() != "Windows":
        for script in [dev_script, test_script, lint_script]:
            os.chmod(script, 0o755)
    
    print("✓ 开发脚本创建完成")

def verify_installation():
    """验证安装"""
    print("🔍 验证安装...")
    
    project_root = Path(__file__).parent.parent
    
    checks = [
        ("uv可用", ["uv", "--version"]),
        ("虚拟环境", ["uv", "venv", "--help"]),  
        ("包管理", ["uv", "pip", "--help"]),
        ("项目依赖", ["uv", "pip", "list"]),
    ]
    
    all_passed = True
    
    for name, cmd in checks:
        try:
            result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✓ {name}")
            else:
                print(f"❌ {name}: {result.stderr}")
                all_passed = False
        except Exception as e:
            print(f"❌ {name}: {e}")
            all_passed = False
    
    return all_passed

def main():
    """主函数"""
    print("🎬 短视频生成平台 - uv环境设置")
    print("=" * 50)
    
    # 1. 检查并安装uv
    if not check_uv_installed():
        print("uv未安装，开始安装...")
        if not install_uv():
            print("❌ uv安装失败，请手动安装")
            print("   访问: https://github.com/astral-sh/uv")
            sys.exit(1)
    
    # 2. 设置Python环境
    if not setup_python_environment():
        print("❌ Python环境设置失败")
        sys.exit(1)
    
    # 3. 创建辅助脚本
    create_activation_scripts()
    create_dev_scripts()
    
    # 4. 验证安装
    if not verify_installation():
        print("❌ 安装验证失败")
        sys.exit(1)
    
    print("\n🎉 环境设置完成!")
    print("=" * 50)
    print("📋 下一步:")
    print("1. 配置环境变量 (复制 .env.example 到 .env)")
    print("2. 启动开发服务器:")
    print("   python scripts/dev.py")
    print("")
    print("🛠️ 常用命令:")
    print("   uv pip install <package>     - 安装新包")
    print("   uv pip list                  - 查看已安装包")
    print("   python scripts/test.py       - 运行测试")
    print("   python scripts/lint.py       - 代码质量检查")
    print("")
    print("💡 激活环境:")
    
    if platform.system() == "Windows":
        print("   scripts\\activate.bat")
    else:
        print("   source scripts/activate.sh")

if __name__ == "__main__":
    main()