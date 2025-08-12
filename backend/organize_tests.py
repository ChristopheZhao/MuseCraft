#!/usr/bin/env python3
"""
安全地整理测试文件 - 只移动明确的测试文件，不影响系统运行
"""
import os
import shutil
from pathlib import Path

# 定义安全移动的文件分类
SAFE_TO_MOVE = {
    'debug': [
        'debug_video_generation.py',
        'debug_zhipu_api.py', 
        'test_glm.py',
        'test_glm_uv.py',
        'simple_video_test.py',
        'quick_video_test.py',
        'direct_tool_test.py',
        'test_startup_fix.py',
    ],
    'integration': [
        'test_audio_for_dog_adventure.py',
        'test_memory_service_standalone.py', 
        'test_memory_service_updates.py',
        'test_image_generator_tools.py',
        'test_mas_collaboration.py',
        'test_script_writer_mas.py',
        'test_video_composer.py',
        'test_suno_callback.py',
        'test_suno_only.py',
    ],
    'development': [
        'test_agent_context.py',
        'test_narrative_frames.py', 
        'test_zhipu_metadata.py',
        'test_video_tool.py',
        'test_tool_like_agent.py',
        'mas_collaborative_design.py',
        'find_broken_tools.py',
    ]
}

def create_directories():
    """创建目标目录"""
    base_dir = Path('tests')
    for subdir in ['debug', 'integration', 'development']:
        (base_dir / subdir).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created directory: tests/{subdir}/")

def move_files():
    """安全地移动文件"""
    moved_count = 0
    
    for category, files in SAFE_TO_MOVE.items():
        target_dir = Path('tests') / category
        
        for filename in files:
            source = Path(filename)
            if source.exists():
                target = target_dir / filename
                try:
                    shutil.move(str(source), str(target))
                    print(f"✅ Moved {filename} → tests/{category}/")
                    moved_count += 1
                except Exception as e:
                    print(f"❌ Failed to move {filename}: {e}")
            else:
                print(f"⚠️  File not found: {filename}")
    
    return moved_count

def create_index_files():
    """为每个目录创建说明文件"""
    descriptions = {
        'debug': '# Debug Tests\n\n临时调试文件和开发测试，用于问题诊断和功能验证。',
        'integration': '# Integration Tests\n\n组件集成测试，测试Agent之间的协作和API集成。',
        'development': '# Development Tests\n\n开发过程中的实验性测试和原型验证。'
    }
    
    for category, desc in descriptions.items():
        readme_path = Path('tests') / category / 'README.md'
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(desc)
        print(f"📝 Created: tests/{category}/README.md")

def main():
    print("🗂️  开始整理测试文件...")
    print("📋 只移动安全的测试文件，不影响系统运行\n")
    
    # 创建目录结构
    create_directories()
    
    # 移动文件
    moved_count = move_files()
    
    # 创建说明文件
    create_index_files()
    
    print(f"\n📊 整理完成！")
    print(f"   移动文件数: {moved_count}")
    print(f"   目录结构: tests/{{debug,integration,development}}/")
    print(f"   保持不变: 所有系统关键文件")

if __name__ == "__main__":
    main()