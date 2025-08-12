@echo off
echo 🎬 短视频生成平台 - Windows uv环境设置
echo ================================================

REM 检查是否已安装uv
uv --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 📦 安装uv包管理器...
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    if %errorlevel% neq 0 (
        echo ❌ uv安装失败
        echo 请手动访问: https://github.com/astral-sh/uv
        pause
        exit /b 1
    )
    echo ✓ uv安装成功
) else (
    echo ✓ uv已安装
)

REM 切换到backend目录
cd /d "%~dp0.."

REM 创建虚拟环境
echo 🐍 创建Python虚拟环境...
uv venv
if %errorlevel% neq 0 (
    echo ❌ 虚拟环境创建失败
    pause
    exit /b 1
)

REM 安装依赖
echo 📦 安装项目依赖...
uv pip install -e .
if %errorlevel% neq 0 (
    echo ❌ 依赖安装失败
    pause
    exit /b 1
)

REM 安装开发依赖
echo 🛠️ 安装开发依赖...
uv pip install -e ".[dev]"
if %errorlevel% neq 0 (
    echo ❌ 开发依赖安装失败
    pause
    exit /b 1
)

REM 创建激活脚本
echo 📝 创建激活脚本...
echo @echo off > scripts\activate_uv.bat
echo echo 🚀 激活uv环境... >> scripts\activate_uv.bat
echo call .venv\Scripts\activate >> scripts\activate_uv.bat
echo echo ✓ uv环境已激活 >> scripts\activate_uv.bat
echo echo. >> scripts\activate_uv.bat
echo echo 📋 可用命令: >> scripts\activate_uv.bat
echo echo   uv pip install ^<package^>     - 安装包 >> scripts\activate_uv.bat
echo echo   uv pip list                  - 列出已安装包 >> scripts\activate_uv.bat
echo echo   python scripts/start_dev_uv.py - 启动开发服务器 >> scripts\activate_uv.bat
echo echo   uv run pytest               - 运行测试 >> scripts\activate_uv.bat
echo echo   uv run black .              - 代码格式化 >> scripts\activate_uv.bat
echo echo. >> scripts\activate_uv.bat

REM 创建开发启动脚本
echo 🛠️ 创建开发脚本...
echo @echo off > scripts\dev.bat
echo echo 🚀 启动开发环境... >> scripts\dev.bat
echo uv run python scripts/start_dev_uv.py >> scripts\dev.bat

REM 创建测试脚本
echo @echo off > scripts\test.bat
echo echo 🧪 运行测试... >> scripts\test.bat
echo uv run pytest -v --cov=app --cov-report=html >> scripts\test.bat
echo echo. >> scripts\test.bat
echo echo 📊 测试报告: htmlcov\index.html >> scripts\test.bat

REM 验证安装
echo 🔍 验证安装...
uv pip list >nul
if %errorlevel% neq 0 (
    echo ❌ 安装验证失败
    pause
    exit /b 1
)

echo.
echo 🎉 环境设置完成!
echo ================================================
echo 📋 下一步:
echo 1. 配置环境变量 (复制 .env.example 到 .env)
echo 2. 启动开发服务器: scripts\dev.bat
echo.
echo 🛠️ 常用命令:
echo   scripts\activate_uv.bat      - 激活环境
echo   scripts\dev.bat              - 启动开发服务器
echo   scripts\test.bat             - 运行测试
echo   uv pip install ^<package^>     - 安装新包
echo   uv pip list                  - 查看已安装包
echo.
pause