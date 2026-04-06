标题: 视频合成与配音混音链路修复计划
状态: 草案
范围: orchestrator + video_composer + composition_tool + ffmpeg_tool + memory_views

## 问题表述
- composer 现被编排为“先合片、再 add_voiceover、再 add_bgm”，出现重入与上下文缺失，触发 `mix_type_mismatch`。
- composer 仍会选择 `download_from_url` 拉取视频，即使已有本地落盘路径，重复下载且导致路径混乱。
- `merge_videos` 使用 `-an` 直接剥离音轨，导致“先给场景加旁白、再合片”这条路径音轨被清空。
- compose 输出路径出现拼接错误（如 `./storage/temp/video_output/storage/outputs/...`），导致找不到文件。
- agent 内部直接写入 `project.final_video` / `project.final_video_mix`，破坏统一的记忆写入与审计路径。

## 偏差分析
- 编排层用多个布尔标志驱动 composer，语义不够强，导致重复调用与验收逻辑不稳定。
- composer 未收到“场景视频 + 场景旁白”的结构化输入，只能依赖 LLM 自行拼参。
- 工具层与路径层存在双重拼接：composition_tool 与 ffmpeg_tool 对 output 路径处理不一致。
- 混音策略与合片策略割裂：现有 `merge_videos` 默认无音轨，和“先混音后合片”的目标冲突。
- 记忆写入分散在 agent 内部与 orchestrator，造成多源写入风险。

## 解决思路
1) 统一编排规则（明确意图，不强耦合步骤）
   - 基础合片：scene_videos 就绪时触发。
   - 旁白可选：若 scene_voiceovers 就绪，则同一次合片中完成逐场景配音混音。
   - BGM 混音：仅在 audio_agent 产出 bgm 后单独触发一次（在已有视频上混）。

2) 结构化输入（降低 LLM 自行拼参的负担）
   - 由 memory_views 构建 `scene_media_ref`（JSON 文件），包含每个场景的 `video_file` + `audio_file` + `duration`。
   - composer 通过工具读取清单（或 composition_tool 直接支持 `scene_media_ref`）完成一次合成。

3) 工具链一致化（保音轨、路径可控）
   - `compose_story_video` 支持场景级 `audio_file`，先单场景混音，再合片。
   - `merge_videos` 保留音轨（去掉 `-an`，必要时改为显式重编码）。
   - output 路径仅允许 basename；由工具层统一拼接，确保目录存在。

4) 记忆写入收敛（可审计）
   - 产物路径由工具返回，orchestrator 统一写入 MAS WM。
   - 移除 video_composer 内部对 `project.final_video/_mix` 的写入。

## 行动计划清单（含优先级）
P0
- 调整 orchestrator 调度逻辑：只要有旁白就“合片+旁白”一次完成；BGM 单独混音一次。
- 修改 `ffmpeg_tool.merge_videos`：保留音轨（去掉 `-an`），确保音频不被清空。
- 修复 compose 输出路径拼接：禁止把完整路径当作 filename；确保目录存在。
- 移除 video_composer 内部写入 `project.final_video/_mix` 的逻辑，改为 orchestrator 接收工具产物再写入。

P1
- 在 `memory_views.build_video_composer_context` 生成 `scene_media_ref` 文件（含视频/旁白路径与时长）。
- 让 `composition_tool.compose_story_video` 支持 `scene_media_ref` 参数（工具层读取并构建 scenes）。
- 从 video_composer 工具暴露中移除 `download_from_url`（保持本地路径优先）。
- 更新 video_composer 提示词：抽象引导“有旁白则一并合片”，不露工具名/参数名。

P2
- 回归测试：最小流程覆盖“有旁白 + 无 BGM”、“无旁白 + 有 BGM”。
- 增加日志：明确 mix_type、输入来源（scene_media_ref vs inline scenes）、最终产物路径。

## 输出验证
- 产物路径在 MAS WM 中只由 orchestrator 写入，且可追溯到工具输出。
- 合片视频包含音轨（旁白已混入），BGM 混音不影响旁白。
- composer 不再重复重入 add_voiceover；无 `mix_type_mismatch`。
