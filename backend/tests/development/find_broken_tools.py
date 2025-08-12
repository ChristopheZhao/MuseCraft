#!/usr/bin/env python3
"""
找出所有缺少@classmethod get_metadata()的工具
"""

import sys
import ast
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def find_broken_tools():
    """找出所有需要修复的工具"""
    
    print("🔍 查找需要修复的工具")
    print("=" * 60)
    
    tools_dir = project_root / "app" / "agents" / "tools"
    broken_tools = []
    
    # 递归查找所有Python文件
    for py_file in tools_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
            
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析AST
            tree = ast.parse(content)
            
            # 查找类定义
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_name = node.name
                    
                    # 检查是否继承自AsyncTool或BaseTool
                    is_tool_class = False
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            if base.id in ['AsyncTool', 'BaseTool']:
                                is_tool_class = True
                                break
                    
                    if not is_tool_class:
                        continue
                    
                    # 检查是否有@classmethod get_metadata
                    has_classmethod_metadata = False
                    has_init_with_metadata = False
                    
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            if item.name == 'get_metadata':
                                # 检查是否有@classmethod装饰器
                                for decorator in item.decorator_list:
                                    if isinstance(decorator, ast.Name) and decorator.id == 'classmethod':
                                        has_classmethod_metadata = True
                                        break
                            elif item.name == '__init__':
                                # 检查__init__是否有metadata参数
                                for arg in item.args.args:
                                    if arg.arg == 'metadata':
                                        has_init_with_metadata = True
                                        break
                    
                    # 如果既没有@classmethod get_metadata，也没有在__init__中处理metadata，就是有问题的
                    if not has_classmethod_metadata and not has_init_with_metadata:
                        broken_tools.append({
                            'file': str(py_file.relative_to(project_root)),
                            'class': class_name,
                            'type': 'missing_metadata_method'
                        })
                    elif has_init_with_metadata and not has_classmethod_metadata:
                        broken_tools.append({
                            'file': str(py_file.relative_to(project_root)), 
                            'class': class_name,
                            'type': 'old_style_init'
                        })
                        
        except Exception as e:
            print(f"⚠️ 解析文件 {py_file} 时出错: {e}")
    
    # 显示结果
    print(f"\n📊 找到 {len(broken_tools)} 个需要修复的工具:")
    print("-" * 40)
    
    for tool in broken_tools:
        print(f"❌ {tool['class']} ({tool['file']})")
        print(f"   问题类型: {tool['type']}")
        print()
    
    return broken_tools

if __name__ == "__main__":
    broken_tools = find_broken_tools()
    
    if broken_tools:
        print("🔧 需要修复这些工具:")
        for tool in broken_tools:
            if tool['type'] == 'missing_metadata_method':
                print(f"   - {tool['class']}: 需要添加 @classmethod get_metadata() 方法")
            elif tool['type'] == 'old_style_init':
                print(f"   - {tool['class']}: 需要将__init__中的metadata改为@classmethod get_metadata()")
    else:
        print("🎉 所有工具都正确实现了metadata方法!")