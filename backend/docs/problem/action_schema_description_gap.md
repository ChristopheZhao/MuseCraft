# 动作 Schema 缺少 Description 说明

## 问题概述
- 部分工具在 `get_action_schema` 返回的动作 Schema 中缺少顶层 `description`。
- 结果是模型只能从参数名和字段描述推断动作意图，工具选择与参数构造更容易偏离。
- 该问题不影响工具本身执行，但会削弱可审计性与可解释性。

## 触发与发现原因
- 在梳理 `composition_tool` 的 `synchronize_audio/compose_story_video` 可用性时，发现动作 Schema 只有参数说明，缺少动作级描述，模型需要“猜”动作语义。
- 为确认是否为单点问题，扩展扫描所有 `get_action_schema` 的实现，发现多个工具存在同类缺失。

## 发现记录
- 扫描范围：`backend/app/agents/tools/**` 中包含 `get_action_schema` 的工具。
- 发现：23 个文件返回的动作 Schema 未包含顶层 `description`（仅有参数描述或无描述）。
- 缺失文件列表：
  - `backend/app/agents/tools/base_tool.py`
  - `backend/app/agents/tools/consistency_tool.py`
  - `backend/app/agents/tools/memory_tool.py`
  - `backend/app/agents/tools/ai_services/image_generation_client.py`
  - `backend/app/agents/tools/ai_services/intelligent_scene_planning_tool.py`
  - `backend/app/agents/tools/ai_services/jimeng_image_tool.py`
  - `backend/app/agents/tools/ai_services/kimi_client.py`
  - `backend/app/agents/tools/ai_services/openai_client.py`
  - `backend/app/agents/tools/ai_services/parameter_optimization_tool.py`
  - `backend/app/agents/tools/ai_services/scene_analysis_tool.py`
  - `backend/app/agents/tools/ai_services/scene_planning_tool.py`
  - `backend/app/agents/tools/ai_services/script_generation_tool.py`
  - `backend/app/agents/tools/ai_services/suno_client.py`
  - `backend/app/agents/tools/ai_services/video_generation_tool.py`
  - `backend/app/agents/tools/ai_services/video_generation_tool_v2.py`
  - `backend/app/agents/tools/ai_services/zhipu_client.py`
  - `backend/app/agents/tools/media_processing/audio_processor.py`
  - `backend/app/agents/tools/storage/file_storage_tool.py`
  - `backend/app/agents/tools/storage/oss_storage_tool.py`
  - `backend/app/agents/tools/video_composition/video_composer_tool.py`
  - `backend/app/agents/tools/video_processing/ffmpeg_tool.py`
  - `backend/app/agents/tools/video_processing/final_frame_tool.py`
  - `backend/app/agents/tools/video_processing/minimax_video_tool.py`

## 问题存在的分析
- **能力表达不足**：工具能力只能通过 Schema 暴露，缺少动作级 `description` 时，模型难以区分相邻动作（如“单段混流”与“多场景合成”）。
- **可审计性弱化**：日志仅能看到动作名和参数，动作意图只能靠参数反推，审计成本上升。
- **一致性缺失**：部分工具已提供动作描述，但没有统一约束/规范，导致能力声明不一致。
- **缺少约束/校验**：当前没有 lint 或运行时校验去强制动作 Schema 必须包含 `description`，缺陷会长期存在并扩散。

## 影响范围
- LLM 规划阶段：动作意图不清晰，可能导致选择错误工具或误用参数。
- 维护与培训：新同事理解工具动作语义成本增加。
- 自动化评审：难以基于 Schema 做一致性检查或自动化验证。

## 后续建议（方向）
- 建立动作 Schema 规范：要求每个动作包含顶层 `description`，并在 Code Review 中检查。
- 结合 lint 或 CI 检查：扫描 `get_action_schema` 输出，若缺失描述则提示。
