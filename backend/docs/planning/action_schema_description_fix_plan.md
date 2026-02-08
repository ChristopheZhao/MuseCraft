标题: Action Schema Description 规范化修复计划
状态: 草案
范围: backend/app/agents/tools/**

## 问题表述

### 核心问题
多数工具的 `get_action_schema` 返回的动作 Schema 缺少顶层 `description` 字段，导致 LLM 只能从函数名和参数描述"猜测"动作意图。

### 影响范围
- 扫描发现 23 个工具文件存在该问题（详见 `backend/docs/problem/action_schema_description_gap.md`）
- 已修复：`composition_tool.py`（包含顶层 description）
- 未修复：`zhipu_client.py`、`ffmpeg_tool.py`、`script_generation_tool.py` 等

### 问题示例
```python
# 缺少描述（当前状态）
"extract_last_frame": {
    "type": "object",
    "properties": {
        "video_path": {"type": "string", "description": "本地视频路径"}
    }
}

# 包含描述（期望状态）
"extract_last_frame": {
    "type": "object",
    "description": "从视频末尾提取最后一帧作为图片，用于视频连续性衔接",
    "properties": {
        "video_path": {"type": "string", "description": "本地视频路径"}
    }
}
```

## 偏差分析

### 与业界最佳实践的偏差

| 维度 | 业界标准 | 项目现状 | 偏差影响 |
|-----|---------|---------|---------|
| **Description 必要性** | OpenAI: "The description field tells the model when and how to use the function" | 多数 action 无顶层 description | LLM 决策依据不足，误用风险增加 |
| **Description 内容** | Anthropic: "Include example usage, edge cases, boundaries between tools" | 仅有参数级描述 | 相似动作难以区分 |
| **Schema 完整性** | OpenAI 推荐 `strict: true` + 完整描述 | Schema 结构不一致 | 工具间质量参差不齐 |

### 架构层面分析

项目采用 **Tool + Action 二层结构**：
- Tool 层：`ImageGenerationTool`、`FFmpegTool` 等
- Action 层：每个 Tool 下的具体操作

**转换机制**（`manager.py:149-168`）：
```python
for act in actions:
    action_schema = tool.get_action_schema(act)
    # 最终 LLM 看到: "image_generation.generate_image"
```

**问题本质**：
- Action 层是项目特有的抽象，业界标准是"一个 function = 一个操作"
- 这个抽象本身没问题，但 `get_action_schema` 返回的 schema 缺少描述字段
- `manager.py:169` 有 fallback 逻辑，但依赖工具级描述 + action 名拼接，语义不精确

### 单一 Action 工具的冗余性

部分工具只有一个 action，action 层显得冗余：
```python
video_prompt_builder_tool → ["build_prompt"]  # 单一操作
```

但考虑架构一致性，不建议为此重构，仅需确保 description 完整。

## 解决思路

### 原则
1. **最小改动**：仅补充缺失的 description，不重构 Tool+Action 架构
2. **内容规范**：description 应包含"做什么 + 何时用 + 边界"
3. **渐进式**：按优先级分批修复，优先修复高频调用工具
4. **可验证**：添加 CI 检查防止回归

### Description 内容规范

```python
"action_name": {
    "type": "object",
    "description": "[动作功能] + [适用场景] + [与相似动作的区分（可选）]",
    "properties": {...}
}
```

**示例**：
```python
# ffmpeg_tool
"merge_videos": {
    "description": "将多个视频片段按顺序拼接为单个视频；适用于多场景合片；不处理音频混流（需另用 add_audio）"
}

"add_audio": {
    "description": "为视频添加或替换音轨；支持音量调节和 ducking；适用于配音/背景音乐混入"
}

# zhipu_client
"chat_completion": {
    "description": "调用智谱 GLM 模型进行文本生成/对话；适用于脚本生成、内容优化等文本任务"
}

"generate_video": {
    "description": "调用 CogVideoX 生成视频片段；支持文生视频和图生视频两种模式"
}
```

## 行动计划清单

### Phase 1: 高优先级工具修复（P0）

核心生成链路工具，直接影响 LLM 决策质量。

| 文件 | 需补充 description 的 actions |
|-----|------------------------------|
| `ai_services/video_generation_tool_v2.py` | `generate_video`, `generate_with_continuity` |
| `ai_services/script_generation_tool.py` | `generate_scene_script`, `generate_scene_scripts_batch` |
| `ai_services/zhipu_client.py` | `chat_completion`, `analyze_image`, `generate_image`, `generate_video` 等 |
| `video_processing/ffmpeg_tool.py` | `merge_videos`, `add_audio`, `extract_last_frame`, `compose_video` 等 |

### Phase 2: 中优先级工具修复（P1）

辅助工具，影响规划和存储。

| 文件 | 需补充 description 的 actions |
|-----|------------------------------|
| `storage/oss_storage_tool.py` | `upload`, `download`, `delete`, `list`, `get_url` |
| `storage/file_storage_tool.py` | 所有 actions |
| `ai_services/voice_synth_tool.py` | 所有 actions |
| `consistency_tool.py` | `get_prompt_assets`, `register_reference` |
| `video_prompt_builder_tool.py` | `build_prompt` |

### Phase 3: 低优先级工具修复（P2）

内部工具或低频调用工具。

| 文件 | 需补充 description 的 actions |
|-----|------------------------------|
| `ai_services/kimi_client.py` | 所有 actions |
| `ai_services/openai_client.py` | 所有 actions |
| `ai_services/suno_client.py` | 所有 actions |
| `ai_services/scene_analysis_tool.py` | 所有 actions |
| `ai_services/parameter_optimization_tool.py` | 所有 actions |
| `media_processing/audio_processor.py` | 所有 actions |
| `video_processing/final_frame_tool.py` | 所有 actions |
| `video_processing/minimax_video_tool.py` | 所有 actions |

### Phase 4: CI 校验与防回归（P1）

1. **添加 lint 脚本**：扫描所有 `get_action_schema` 返回值，检查是否包含 `description`
2. **集成到 CI**：在 PR 检查中运行，缺失 description 则失败
3. **文档更新**：在 `CLAUDE.md` 或开发规范中明确要求

**Lint 脚本示例**：
```python
# scripts/lint_action_schema.py
def check_action_schema_description(tool_class):
    """检查工具的所有 action schema 是否包含 description"""
    tool = tool_class()
    for action in tool.get_available_actions():
        schema = tool.get_action_schema(action)
        if not schema.get("description"):
            raise ValueError(f"{tool_class.__name__}.{action} 缺少 description")
```

## 验收标准

1. **完整性**：所有 `get_action_schema` 返回的 schema 包含顶层 `description`
2. **语义性**：description 能让 LLM 区分相似动作（如 `merge_videos` vs `compose_video`）
3. **可维护性**：CI 检查通过，新增工具自动受约束
4. **兼容性**：不改变现有 Tool+Action 架构，仅补充字段

## 参考资料

- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [Anthropic: Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- 项目问题文档：`backend/docs/problem/action_schema_description_gap.md`
