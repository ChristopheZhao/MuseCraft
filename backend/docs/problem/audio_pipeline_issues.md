# 问题记录：音频生成与合成链路

## Audio Generator 音效误判（任务无法标记完成）

### 现象
- 背景音乐已成功生成，但音频代理在规划合同时判断“缺少音效/按场景拆分”，从而持续返回未完成状态。
- 当没有音效生成工具时，这一判断会导致流程卡在 audio_generator 阶段。

### 日志证据（关键片段）
- 已生成背景音乐：
  - `audio_generator` 工具执行成功：`suno_client.generate_background_music`，`artifact=https://musicfile.api.box/...`
  - 示例：`2025-12-20 22:28:33,836 - TOOL_END ... success=True ... artifact=https://musicfile.api.box/...`
- 规划合同仍判定未完成（要求音效/分场景背景音乐）：
  - `2025-12-20 22:29:02,450 - PLAN_CONTRACT ... task_complete=False ... plan_summary_preview=已生成整体背景音乐，但需要为5个不同场景分别生成专门的背景音乐...`
  - `2025-12-20 22:29:16,069 - PLAN_CONTRACT ... task_complete=False completed_reason=背景音乐已生成完成，但缺少音效部分`

### 根因分析
- `scene_scripts` 中包含 `sound_effects` 字段（由脚本生成阶段写入）。
- `audio_generator` 的上下文组装会携带 `scene_scripts`，模型在规划时把 `sound_effects` 当成必需交付物。
- 当前没有音效工具，导致模型无法完成“音效交付”，最终在合同阶段判定未完成。

### 关联代码/路径
- 脚本写入音效字段：`backend/app/agents/script_writer.py`
- 上下文注入脚本信息：`backend/app/agents/adapters/memory_views.py`
- 音频代理规划提示词：`backend/app/config/prompts/agents/audio_generator.yaml`

### 备注（面向未来）
- 后续若新增音效工具，**应由上游显式声明“需要音效”**，由此开启音效能力。
- 这样既避免当前误判阻塞流程，也避免未来能力上线后被“默认忽略音效”的提示词误伤。

### 修复建议
- **短期（无音效工具阶段）**：在 `audio_generator` 规划提示词中增加“音效默认不作为必需交付物”的约束，同时说明“当上游显式声明需要音效时才启用”。这能阻止模型把 `sound_effects` 视为必须交付。
- **中期（上下文侧兜底）**：在上下文构建时，加入明确标志位（如 `sfx_required=false`），让模型有结构化判断依据，避免因 `scene_scripts.sound_effects` 被动触发。
- **上线音效工具后**：由 orchestrator 或上游任务分解器在需要时将 `sfx_required=true` 写入事实，提示词只做解释，不做硬编码判断。

---

## Video Composer 单轮混音不完整（BGM 下载但未混入成片）

### 现象
- `audio_generator` 生成 BGM 后，编排器确实触发了“合成器加背景音乐”。
- 但 `video_composer` 只执行了 `download_from_url`，未继续调用 `synchronize_audio`，导致 BGM 未混入成片。

### 日志证据（关键片段）
- 编排器触发混音：
  - `2025-12-20 22:29:16,183 - 🎼 Scheduling composer to add background music`
- composer 实际只下载：
  - `2025-12-20 22:29:20,800 - FC计划: 1 calls -> file_storage_tool.download_from_url(...)`
  - `2025-12-20 22:30:05,798 - TOOL_END ... download_from_url ... success=True`
- 无 `composition_tool.synchronize_audio` 调用记录。

### 根因分析
- `video_composer` 当前为 BaseAgent 单轮执行模式：一次规划 → 一次执行 → 结束。
- 在只有 BGM URL 的情况下，模型往往只规划“下载”，但下载完成后**没有第二轮规划**去触发混音。
- 编排器仅验证 `project.final_video` 是否存在，没有验证“混音已应用”，导致该问题被掩盖。

### 关联代码/路径
- 编排器加 BGM 逻辑：`backend/app/agents/orchestrator.py`
- 合成器单轮规划执行：`backend/app/agents/video_composer.py`

### 影响
- 最终成片仍是“无背景音乐版本”，但流程表面显示成功，容易在 QA 或交付阶段才暴露。

### 修复建议
- **推荐方向（稳态）**：将 `video_composer` 迁移到 ReAct 多轮执行，使“下载 → 再规划 → 混音”成为自然闭环。
- **最小改动（仍单轮）**：在 `video_composer` 的规划提示词中强制同轮产出“下载 + 混音”的联动计划，并要求在仅有 BGM URL 时必须包含 `synchronize_audio` 调用。
- **验证补强**：编排器在 `add_bgm` 后增加“混音已应用”的事实校验（例如检查合成产物更新时间或混音标记），避免仅以 `project.final_video` 存在作为成功条件。
