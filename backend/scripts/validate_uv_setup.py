#!/usr/bin/env python3
"""
验证uv环境设置的完整性
"""

import subprocess
import sys
import os
from pathlib import Path
import importlib.util


def check_uv_installation():
    """检查uv是否正确安装"""
    print("🔍 检查uv安装...")
    
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ uv已安装: {result.stdout.strip()}")
            return True
        else:
            print("❌ uv安装有问题")
            return False
    except FileNotFoundError:
        print("❌ uv未找到，请先安装uv")
        print("   安装命令: curl -LsSf https://astral.sh/uv/install.sh | sh")
        return False


def check_virtual_environment():
    """检查虚拟环境"""
    print("\n🐍 检查虚拟环境...")
    
    project_root = Path(__file__).parent.parent
    venv_path = project_root / ".venv"
    
    if not venv_path.exists():
        print("❌ 虚拟环境不存在")
        print("   创建命令: uv venv")
        return False
    
    print("✓ 虚拟环境存在")
    
    # 检查Python解释器
    if os.name == 'nt':  # Windows
        python_path = venv_path / "Scripts" / "python.exe"
    else:  # Unix-like
        python_path = venv_path / "bin" / "python"
    
    if python_path.exists():
        print(f"✓ Python解释器: {python_path}")
        return True
    else:
        print("❌ Python解释器不存在")
        return False


def check_project_installation():
    """检查项目是否正确安装"""
    print("\n📦 检查项目安装...")
    
    project_root = Path(__file__).parent.parent
    
    try:
        # 检查是否能导入项目模块
        result = subprocess.run(
            ["uv", "run", "python", "-c", "import app; print('Project import successful')"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✓ 项目模块可以正常导入")
            return True
        else:
            print("❌ 项目模块导入失败")
            print(f"   错误: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 检查项目安装时出错: {e}")
        return False


def check_dependencies():
    """检查关键依赖是否安装"""
    print("\n📋 检查关键依赖...")
    
    project_root = Path(__file__).parent.parent
    critical_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy", 
        "redis",
        "celery",
        "openai",
        "jinja2",
        "pyyaml"
    ]
    
    missing_packages = []
    
    for package in critical_packages:
        try:
            result = subprocess.run(
                ["uv", "run", "python", "-c", f"import {package}; print('{package} OK')"],
                cwd=project_root,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✓ {package}")
            else:
                print(f"❌ {package} - 导入失败")
                missing_packages.append(package)
                
        except Exception as e:
            print(f"❌ {package} - 检查失败: {e}")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n❌ 缺失的包: {', '.join(missing_packages)}")
        print("   安装命令: uv pip install -e .")
        return False
    
    return True


def check_dev_dependencies():
    """检查开发依赖"""
    print("\n🛠️ 检查开发依赖...")
    
    project_root = Path(__file__).parent.parent
    dev_packages = [
        "pytest",
        "black", 
        "isort",
        "flake8",
        "mypy"
    ]
    
    missing_dev_packages = []
    
    for package in dev_packages:
        try:
            result = subprocess.run(
                ["uv", "run", "python", "-c", f"import {package}; print('{package} OK')"],
                cwd=project_root,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✓ {package}")
            else:
                print(f"❌ {package} - 导入失败")
                missing_dev_packages.append(package)
                
        except Exception as e:
            print(f"❌ {package} - 检查失败: {e}")
            missing_dev_packages.append(package)
    
    if missing_dev_packages:
        print(f"\n⚠️ 缺失的开发包: {', '.join(missing_dev_packages)}")
        print("   安装命令: uv pip install -e '.[dev]'")
        return False
    
    return True


def check_scripts():
    """检查关键脚本是否存在"""
    print("\n📜 检查脚本文件...")
    
    project_root = Path(__file__).parent.parent
    scripts_dir = project_root / "scripts"
    
    required_scripts = [
        "setup_uv_environment.py",
        "start_dev_uv.py",
        "setup_uv_windows.bat"
    ]
    
    missing_scripts = []
    
    for script in required_scripts:
        script_path = scripts_dir / script
        if script_path.exists():
            print(f"✓ {script}")
        else:
            print(f"❌ {script} - 文件不存在")
            missing_scripts.append(script)
    
    if missing_scripts:
        print(f"\n❌ 缺失的脚本: {', '.join(missing_scripts)}")
        return False
    
    return True


def check_pyproject_toml():
    """检查pyproject.toml配置"""
    print("\n⚙️ 检查pyproject.toml...")
    
    project_root = Path(__file__).parent.parent
    pyproject_path = project_root / "pyproject.toml"
    
    if not pyproject_path.exists():
        print("❌ pyproject.toml不存在")
        return False
    
    print("✓ pyproject.toml存在")
    
    # 检查关键配置项
    try:
        with open(pyproject_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        required_sections = [
            "[project]",
            "[project.optional-dependencies]",
            "[tool.black]",
            "[tool.mypy]"
        ]
        
        missing_sections = []
        for section in required_sections:
            if section in content:
                print(f"✓ {section}")
            else:
                print(f"❌ {section} - 配置节缺失")
                missing_sections.append(section)
        
        if missing_sections:
            print(f"\n❌ 缺失的配置节: {', '.join(missing_sections)}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ 读取pyproject.toml失败: {e}")
        return False


def run_basic_tests():
    """运行基本功能测试"""
    print("\n🧪 运行基本功能测试...")
    
    project_root = Path(__file__).parent.parent
    
    tests = [
        {
            "name": "导入FastAPI",
            "command": ["uv", "run", "python", "-c", "from fastapi import FastAPI; print('FastAPI OK')"]
        },
        {
            "name": "导入SQLAlchemy", 
            "command": ["uv", "run", "python", "-c", "from sqlalchemy import create_engine; print('SQLAlchemy OK')"]
        },
        {
            "name": "导入项目主模块",
            "command": ["uv", "run", "python", "-c", "from app.main import app; print('Main app OK')"]
        }
    ]
    
    failed_tests = []
    
    for test in tests:
        try:
            result = subprocess.run(
                test["command"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                print(f"✓ {test['name']}")
            else:
                print(f"❌ {test['name']} - 失败")
                print(f"   错误: {result.stderr}")
                failed_tests.append(test['name'])
                
        except subprocess.TimeoutExpired:
            print(f"❌ {test['name']} - 超时")
            failed_tests.append(test['name'])
        except Exception as e:
            print(f"❌ {test['name']} - 异常: {e}")
            failed_tests.append(test['name'])
    
    if failed_tests:
        print(f"\n❌ 失败的测试: {', '.join(failed_tests)}")
        return False
    
    return True


def display_environment_info():
    """显示环境信息"""
    print("\n📊 环境信息:")
    print("=" * 50)
    
    project_root = Path(__file__).parent.parent
    
    # uv版本
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        print(f"uv版本: {result.stdout.strip()}")
    except:
        print("uv版本: 未知")
    
    # Python版本
    try:
        result = subprocess.run(
            ["uv", "run", "python", "--version"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        print(f"Python版本: {result.stdout.strip()}")
    except:
        print("Python版本: 未知")
    
    # 已安装包数量
    try:
        result = subprocess.run(
            ["uv", "pip", "list"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        package_count = len(result.stdout.strip().split('\n')) - 2
        print(f"已安装包数量: {package_count}")
    except:
        print("已安装包数量: 未知")
    
    print("=" * 50)


def main():
    """主函数"""
    print("🎬 短视频生成平台 - uv环境验证")
    print("=" * 60)
    
    checks = [
        ("uv安装", check_uv_installation),
        ("虚拟环境", check_virtual_environment), 
        ("项目安装", check_project_installation),
        ("核心依赖", check_dependencies),
        ("开发依赖", check_dev_dependencies),
        ("脚本文件", check_scripts),
        ("pyproject.toml", check_pyproject_toml),
        ("基本功能", run_basic_tests)
    ]
    
    passed_checks = 0
    total_checks = len(checks)
    
    for name, check_func in checks:
        print(f"\n{'='*20} {name} {'='*20}")
        if check_func():
            passed_checks += 1
            print(f"✅ {name} - 通过")
        else:
            print(f"❌ {name} - 失败")
    
    # 显示环境信息
    display_environment_info()
    
    # 最终结果
    print(f"\n🏁 验证完成: {passed_checks}/{total_checks} 项检查通过")
    
    if passed_checks == total_checks:
        print("🎉 所有检查通过！uv环境设置完美！")
        print("\n🚀 下一步:")
        print("1. 配置环境变量 (.env文件)")
        print("2. 启动开发服务器: python scripts/start_dev_uv.py")
        return True
    else:
        print("⚠️ 部分检查失败，请根据上述错误信息进行修复")
        print("\n🔧 建议修复步骤:")
        print("1. 重新运行安装: python scripts/setup_uv_environment.py")
        print("2. 手动安装缺失依赖: uv pip install -e '.[dev]'")
        print("3. 检查项目配置文件")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)