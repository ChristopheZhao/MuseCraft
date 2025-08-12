# 测试文件重组说明

## 新的测试目录结构

```
tests/
├── unit/           # 单元测试 - 测试单个组件/函数
├── integration/    # 集成测试 - 测试组件间交互
├── e2e/           # 端到端测试 - 完整工作流测试
├── debug/         # 调试和开发测试 - 临时测试文件
├── performance/   # 性能测试 - 负载和基准测试
└── conftest.py    # pytest配置
```

## 文件重组分类

### Unit Tests (单元测试)
- `test_env_loading.py` → `tests/unit/`
- `test_tool_registration.py` → `tests/unit/`
- `test_config_system.py` → `tests/unit/`

### Integration Tests (集成测试)
- `test_audio_composition.py` → `tests/integration/`
- `test_video_composer.py` → `tests/integration/`
- `test_image_generator_tools.py` → `tests/integration/`
- `test_mas_collaboration.py` → `tests/integration/`
- `test_script_writer_mas.py` → `tests/integration/`
- `test_memory_service_*.py` → `tests/integration/`

### E2E Tests (端到端测试)
- `test_complete_mas_system.py` → `tests/e2e/`
- `test_full_audio_integration.py` → `tests/e2e/`
- `test_final_integration.py` → `tests/e2e/`
- `test_first_last_frame.py` → `tests/e2e/`

### Debug Tests (调试测试)
- `debug_*.py` → `tests/debug/`
- `simple_video_test.py` → `tests/debug/`
- `quick_video_test.py` → `tests/debug/`
- `direct_tool_test.py` → `tests/debug/`
- `test_glm.py` → `tests/debug/`
- `test_startup_fix.py` → `tests/debug/`

### Performance Tests (性能测试)
- `test_performance_*.py` → `tests/performance/`

## 使用说明

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定类型的测试
python -m pytest tests/unit/           # 单元测试
python -m pytest tests/integration/   # 集成测试
python -m pytest tests/e2e/          # 端到端测试
python -m pytest tests/debug/        # 调试测试
python -m pytest tests/performance/  # 性能测试

# 运行特定测试文件
python -m pytest tests/unit/test_env_loading.py
```

## 清理建议

1. **保留的文件** - 移动到对应目录
2. **可删除的文件** - 过时或重复的调试文件
3. **需要更新的文件** - 调整import路径
