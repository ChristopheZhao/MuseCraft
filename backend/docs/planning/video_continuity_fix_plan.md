标题: 视频连续性与图生路径修复计划
状态: 草案
范围: video_generator + video_generation_tool_v2 + prompts + tool_policies

## 问题表述
- 连续性场景实际走文生视频，未使用上一场景尾帧或当前场景关键图。
- `generate_with_continuity` 的 schema 支持 `previous_video_url`，但实现未兑现该语义，导致参数可达但无效。
- 独立场景具备 `image_url` 但 LLM 未显式传入，导致图生能力未使用。
- 提示词缺少“抽象指导”，未引导 LLM 选择连续性/起始图的策略。

## 偏差分析
- 架构约束要求工具不读共享记忆，`continuity_frame` 需要显式输入；当前实现只检查 `continuity_frame`，未处理 `previous_video_url` → 尾帧转换。
- schema 与实现不一致：对外暴露 `previous_video_url`，对内未消费，造成“看似支持但实际无效”的行为。
- 计划提示词强调连续性，但未给出“依赖场景应携带上一场景视频/独立场景应携带起始图”的抽象指引，LLM 规划缺少稳定锚点。
- 工具列表仍暴露连续性准备工具，易导致 LLM 进行不必要的步骤选择，与“确定性前置”理念冲突。

## 解决思路
1) 工具层契约对齐
   - 在 `_generate_with_continuity` 内部将 `previous_video_url` 确定性转换为 `continuity_frame`，但不重新实现抽帧逻辑：
     - 通过工具注册表调用 `scene_continuity_preparation.prepare_scene_input`；
     - 入参使用 `scene_number` + `previous_scene_video_url`（必要时补充 `fallback_image_url`）；
     - 读取返回的 `image_url` 作为 `continuity_frame`；
     - 仅依赖显式参数，不读取记忆。
   - 若无 `previous_video_url`，则使用 `image_url` 作为参考图；两者都无则退回文生。

2) 提示词优化（抽象指导，不露工具名/参数名）
   - 为视频生成规划提示加入高层指导：
     - 依赖场景应携带上一场景视觉衔接参考；
     - 独立场景应携带当前场景起始视觉参考；
   - 强调“可用视觉参考优先于纯文本”，但不硬编码流程或工具。

3) 工具暴露策略收敛
   - 将连续性准备工具从 video_generator 的可见工具列表中移除，避免 LLM 决策前置步骤。
   - 保留内部工具可用性（仅供工具层调用）。

## 行动计划清单
1. 工具层修正（优先级：P0）
   - 修改 `backend/app/agents/tools/ai_services/video_generation_tool_v2.py`：
     - 在 `_generate_with_continuity` 中调用 `scene_continuity_preparation.prepare_scene_input`；
     - `previous_video_url` 有值时优先走该路径；用返回 `image_url` 设置 `continuity_frame`；
     - 保持不读取共享记忆，失败时降级到 `image_url`/文生。
   - 补充日志：明确连续性来源（previous_video_url / image_url / none）。
   - 前置检查：确认 `previous_video_url` 与 `image_url` 在上下文中可达（如 `build_video_generation_context` 是否包含已完成场景的视频 URL，供依赖场景引用）。

2. 提示词优化（优先级：P1）
   - 更新 `backend/app/config/prompts/agents/video_generator.yaml` 的计划/执行提示：
     - 加入“依赖场景/独立场景”的抽象视觉参考策略。
     - 避免出现工具名/参数名，遵守 Prompt Neutrality。

3. 工具列表调整（优先级：P1）
   - 更新 `backend/app/agents/config/tool_policies.yaml`：
     - 对 video_generator 移除 `scene_continuity_preparation` 暴露项。

4. 验证与回归（优先级：P2）
   - 复现最小流程，确认日志出现 `image_origin=continuity_frame` 或 `image_origin=reference_image`。
   - 验证连续性场景走图生，独立场景使用起始图；无图场景保持文生。
   - 如需自动化，补充最小集成用例（仅验证分支与日志/产物字段）。

## 已完成与偏差说明
- 已完成: 工具层已按计划改为通过 `scene_continuity_preparation` 获取连续性帧（待验证日志与产物）。
- 已完成: `build_video_generation_context` 为依赖场景补齐上一场景视频链接字段，便于 LLM 取用（待验证上下文可达性）。
- 已完成: 提示词已加入“连续性/独立场景视觉参考”的抽象指引。
- 已完成: `scene_continuity_preparation` 已从 video_generator 工具暴露中移除。
- 偏差记录: 曾出现直接调用 `final_frame_tool` 的实现（与“复用既有连续性准备工具”目标不一致），已按当前计划修正。
