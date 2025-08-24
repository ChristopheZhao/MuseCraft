#!/usr/bin/env python3
"""
第二阶段开发文件清理脚本
将开发过程中的临时文件移动到archive目录，保持主分支清洁
"""

import os
import shutil
from pathlib import Path

def cleanup_stage2_files():
    """清理第二阶段开发临时文件"""
    
    backend_dir = Path(__file__).parent.parent
    archive_dir = backend_dir / "archive" / "stage2_development_files"
    
    # 确保存档目录存在
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # 需要移动到存档的测试文件（保留重要的测试目录结构）
    temp_test_files = [
        "test_all_agents_prompts.py",
        "test_all_scene_data_fixes.py", 
        "test_architecture_fix.py",
        "test_atomic_tool_decoupling.py",
        "test_concept_planner_fc.py",
        "test_concept_planner_simple.py",
        "test_fc_status.py",
        "test_final_image_generator_templates.py",
        "test_golden_core_continuity.py",
        "test_image_generator_complete.py",
        "test_image_generator_prompts.py",
        "test_improved_continuity_analysis.py",
        "test_intelligent_style_design.py",
        "test_mas_fixes.py",
        "test_mas_intelligent_style.py",
        "test_memory_system_activation.py",
        "test_narrative_structure_fix.py",
        "test_prompt_system.py",
        "test_refactored_video_generator.py",
        "test_response_format.py",
        "test_response_format2.py", 
        "test_response_format3.py",
        "test_same_call.py",
        "test_scene_continuity_analysis.py",
        "test_simple_prompt.py",
        "test_simple_scene_continuity.py",
        "test_tool_decoupling.py",
        "test_tooloutput_fix.py",
        "test_video_generator_fix.py",
        "test_zhipu_json.py",
        "test_zhipu_json_simple.py"
    ]
    
    # 需要保留的重要测试文件（提交到git）
    important_test_files = [
        "test_llm_driven_system.py",
        "test_mas_integration.py", 
        "test_api_workflow.py",
        "test_complete_scene_continuity_system.py",
        "test_mas_memory_integration.py",
        "final_workflow_test.py"
    ]
    
    print("🗂️ 开始清理第二阶段开发文件...")
    
    # 移动临时测试文件
    moved_count = 0
    for test_file in temp_test_files:
        test_path = backend_dir / test_file
        if test_path.exists():
            archive_path = archive_dir / test_file
            shutil.move(str(test_path), str(archive_path))
            print(f"📦 已移动: {test_file} -> archive/stage2_development_files/")
            moved_count += 1
    
    # 创建说明文件
    readme_content = f"""# 第二阶段开发文件存档

这个目录包含第二阶段开发过程中产生的临时测试文件和调试脚本。

## 移动的文件 ({moved_count}个)

### 临时测试文件
这些文件是开发过程中的调试和验证工具，已移动到存档以保持主分支清洁：

{chr(10).join(f"- {f}" for f in temp_test_files if (archive_dir / f).exists())}

## 保留在主分支的重要文件

以下测试文件因为重要性被保留在主分支：

{chr(10).join(f"- {f}" for f in important_test_files)}

## 说明

- 这些存档文件在需要时可以恢复到主分支
- 存档不影响系统功能，只是为了保持代码库整洁
- 重要的集成测试和工作流测试保留在主分支

## 清理时间

清理时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
清理脚本: scripts/cleanup_stage2_dev_files.py
"""
    
    readme_path = archive_dir / "README.md"
    readme_path.write_text(readme_content, encoding='utf-8')
    
    print(f"✅ 清理完成！移动了 {moved_count} 个文件到存档目录")
    print(f"📝 创建了说明文件: {readme_path}")
    
    return moved_count

if __name__ == "__main__":
    cleanup_stage2_files()