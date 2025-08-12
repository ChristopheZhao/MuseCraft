@echo off
echo 🚀 激活Python环境...
call .venv\Scripts\activate
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
