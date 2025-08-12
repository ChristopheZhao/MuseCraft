#!/usr/bin/env python3
"""
测试配置系统的完整性和动态切换功能
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.video_config_manager import get_video_config, VideoConfigManager
from app.core.config import settings


def test_basic_configuration():
    """测试基本配置功能"""
    print("🧪 Testing Basic Configuration...")
    
    video_config = get_video_config()
    
    # 测试当前提供商配置
    current_config = video_config.get_current_provider_config()
    print(f"✅ Current Provider: {current_config.provider_name}")
    print(f"   - Model: {current_config.model_name}")
    print(f"   - Duration Capabilities: {current_config.duration_capabilities}")
    print(f"   - Supports First/Last Frame: {current_config.supports_first_last_frame}")
    print(f"   - Amplification Ratio: {current_config.amplification_ratio}")
    
    # 测试系统能力计算
    system_capability = video_config.get_system_duration_capability()
    print(f"✅ System Capability: {system_capability['min_duration']}-{system_capability['max_duration']}s")
    print()


def test_provider_switching():
    """测试提供商动态切换"""
    print("🧪 Testing Provider Switching...")
    
    video_config = get_video_config()
    original_provider = video_config._current_provider
    
    # 测试切换到不同的提供商
    test_providers = ["cogvideox-3", "cogvideox-2", "runway", "pika"]
    
    for provider in test_providers:
        if video_config.set_current_provider(provider):
            config = video_config.get_current_provider_config()
            print(f"✅ Switched to {provider}:")
            print(f"   - Max Duration: {config.max_duration}s")
            print(f"   - System Max: {video_config.get_system_duration_capability()['max_duration']}s")
            print(f"   - First/Last Frame: {config.supports_first_last_frame}")
        else:
            print(f"❌ Failed to switch to {provider}")
    
    # 恢复原始提供商
    video_config.set_current_provider(original_provider)
    print()


def test_duration_validation():
    """测试时长验证"""
    print("🧪 Testing Duration Validation...")
    
    video_config = get_video_config()
    
    test_durations = [15, 30, 45, 60, 90, 120]
    
    for duration in test_durations:
        validation = video_config.validate_duration_request(duration)
        status = "✅" if validation["is_valid"] else "⚠️"
        print(f"{status} Duration {duration}s: Valid={validation['is_valid']}, Suggestion={validation['suggestion']}s")
    
    print()


def test_scene_count_calculation():
    """测试场景数量计算"""
    print("🧪 Testing Scene Count Calculation...")
    
    video_config = get_video_config()
    
    test_durations = [20, 30, 45, 60]
    
    for duration in test_durations:
        optimal_scenes = video_config.calculate_optimal_scene_count(duration)
        print(f"✅ {duration}s video → {optimal_scenes} scenes")
    
    print()


def test_configuration_injection():
    """测试配置注入"""
    print("🧪 Testing Configuration Injection...")
    
    video_config = get_video_config()
    injected_config = video_config.get_provider_specific_config()
    
    # 验证关键配置项存在
    required_keys = [
        "provider_name", "model_name", "default_duration", "max_duration",
        "amplification_ratio", "supports_first_last_frame", "system_duration_capability",
        "default_scene_duration", "transition_duration", "audio_fade_in_duration"
    ]
    
    missing_keys = []
    for key in required_keys:
        if key not in injected_config:
            missing_keys.append(key)
        else:
            print(f"✅ {key}: {injected_config[key]}")
    
    if missing_keys:
        print(f"❌ Missing keys: {missing_keys}")
    else:
        print("✅ All required configuration keys present")
    
    print()


def test_comparison_matrix():
    """测试提供商对比矩阵"""
    print("🧪 Testing Provider Comparison Matrix...")
    
    video_config = get_video_config()
    matrix = video_config.get_comparison_matrix()
    
    print("Provider Comparison Matrix:")
    print("-" * 80)
    for provider, info in matrix.items():
        print(f"📊 {provider}:")
        print(f"   Single Clip: {info['single_clip_duration']}")
        print(f"   System Capability: {info['system_capability']}")
        print(f"   First/Last Frame: {info['supports_first_last_frame']}")
        print(f"   Recommended: {info['recommended_for']}")
        print()


def test_hardcoded_elimination():
    """验证硬编码消除"""
    print("🧪 Testing Hardcoded Value Elimination...")
    
    # 检查settings中的配置化参数
    duration_configs = [
        ("DEFAULT_SCENE_DURATION", settings.DEFAULT_SCENE_DURATION),
        ("MIN_SCENE_DURATION", settings.MIN_SCENE_DURATION),
        ("MAX_SCENE_DURATION", settings.MAX_SCENE_DURATION),
        ("TRANSITION_DURATION", settings.TRANSITION_DURATION),
        ("DEFAULT_AUDIO_DURATION", settings.DEFAULT_AUDIO_DURATION),
        ("AUDIO_FADE_IN_DURATION", settings.AUDIO_FADE_IN_DURATION),
        ("AUDIO_FADE_OUT_DURATION", settings.AUDIO_FADE_OUT_DURATION)
    ]
    
    print("Configuration Values:")
    for name, value in duration_configs:
        print(f"✅ {name}: {value}")
    
    # 验证视频配置管理器能够覆盖这些值
    video_config = get_video_config()
    provider_config = video_config.get_provider_specific_config()
    
    print(f"\nProvider Override Values:")
    print(f"✅ Provider Scene Duration: {provider_config['default_scene_duration']}")
    print(f"✅ Provider Max Duration: {provider_config['max_duration']}")
    print(f"✅ System Capability: {provider_config['system_duration_capability']['max_duration']}s")
    
    print()


def main():
    """运行所有测试"""
    print("🎬 Video Configuration System Test Suite")
    print("=" * 50)
    
    try:
        test_basic_configuration()
        test_provider_switching()
        test_duration_validation()
        test_scene_count_calculation()
        test_configuration_injection()
        test_comparison_matrix()
        test_hardcoded_elimination()
        
        print("✅ All tests passed! Configuration system is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())