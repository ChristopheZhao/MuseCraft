#!/usr/bin/env python3
"""
启动本地HTTP服务器来查看商业计划书
解决浏览器无法直接访问本地文件的问题
"""

import http.server
import socketserver
import webbrowser
import os
import sys
import threading
import time

def start_server():
    """启动本地HTTP服务器"""
    PORT = 8080
    
    # 确保在正确的目录中启动服务器
    if not os.path.exists('MuseCraft_Business_Plan_Standalone.html'):
        print("❌ 未找到MuseCraft_Business_Plan_Standalone.html文件")
        print("请确保在正确的目录中运行此脚本")
        sys.exit(1)
    
    Handler = http.server.SimpleHTTPRequestHandler
    
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            print(f"🚀 正在启动本地服务器...")
            print(f"📡 服务器地址: http://localhost:{PORT}")
            print(f"📄 商业计划书地址: http://localhost:{PORT}/MuseCraft_Business_Plan_Standalone.html")
            print(f"🔄 按 Ctrl+C 停止服务器")
            
            # 延迟1秒后自动打开浏览器
            def open_browser():
                time.sleep(1)
                webbrowser.open(f'http://localhost:{PORT}/MuseCraft_Business_Plan_Standalone.html')
            
            threading.Thread(target=open_browser, daemon=True).start()
            
            # 启动服务器
            httpd.serve_forever()
            
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"❌ 端口 {PORT} 已被占用")
            print("请尝试以下解决方案：")
            print("1. 关闭占用该端口的程序")
            print("2. 直接在浏览器中打开: MuseCraft_Business_Plan_Standalone.html")
            print("3. 使用其他端口运行服务器")
        else:
            print(f"❌ 启动服务器失败: {e}")

def create_quick_start_guide():
    """创建快速启动指南"""
    guide = """# 商业计划书查看指南

## 🎯 最简单的方法（推荐）

1. **直接打开完整版**：
   双击 `MuseCraft_Business_Plan_Standalone.html` 文件即可
   - 这是一个完全自包含的HTML文件
   - 包含所有内容和样式
   - 无需网络连接

## 🌐 本地服务器方法

如果直接打开有问题，使用本地服务器：

### 方法1：Python服务器
```bash
python3 start_local_server.py
```

### 方法2：手动启动服务器
```bash
# Python 3
python3 -m http.server 8080

# 然后在浏览器中打开
# http://localhost:8080/MuseCraft_Business_Plan_Standalone.html
```

## 📄 PDF转换方法

### 浏览器转PDF（推荐）：
1. 打开 `MuseCraft_Business_Plan_Standalone.html`
2. 按 `Ctrl+P` (Windows/Linux) 或 `Cmd+P` (Mac)
3. 选择"另存为PDF"或"Save as PDF"
4. 设置：
   - 页面：全部
   - 布局：纵向
   - 页边距：最小值
   - 比例：适合页面宽度
   - 背景图形：启用
5. 保存

### 高级PDF设置：
- 纸张大小：A4
- 页眉/页脚：可选择性关闭
- 彩色：启用彩色打印
- 质量：高质量

## 🛠️ 故障排除

### 问题1：文件无法打开
- **解决**：确保使用现代浏览器（Chrome、Firefox、Safari、Edge）

### 问题2：样式显示异常
- **解决**：清除浏览器缓存，刷新页面

### 问题3：图表显示为占位符
- **解决**：这是正常的，图表内容以文本形式描述

### 问题4：PDF导出格式问题
- **解决**：调整浏览器打印设置中的缩放比例

## 📱 移动设备查看

该HTML文件支持响应式设计，可以在手机和平板上正常查看。

## 🔗 在线查看选项

如果本地查看有问题，可以：
1. 将HTML文件上传到GitHub Pages
2. 使用在线HTML预览工具
3. 发送给其他人查看

推荐直接使用 `MuseCraft_Business_Plan_Standalone.html`，这是最可靠的方法！
"""
    
    with open('VIEWING_GUIDE.md', 'w', encoding='utf-8') as f:
        f.write(guide)
    
    print("✅ 已生成查看指南: VIEWING_GUIDE.md")

if __name__ == "__main__":
    print("🎨 MuseCraft商业计划书本地服务器")
    print("=" * 50)
    
    # 创建查看指南
    create_quick_start_guide()
    
    print("\n💡 使用建议:")
    print("1. 最简单：直接双击 MuseCraft_Business_Plan_Standalone.html")
    print("2. 如有问题：使用下面的本地服务器")
    print("3. 转PDF：在浏览器中按 Ctrl+P")
    
    print("\n🚀 正在启动本地服务器...")
    start_server()