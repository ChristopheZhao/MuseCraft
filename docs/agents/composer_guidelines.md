# 视频合成（Composer）Agent 指南（ReAct + Tools‑First）

本文约束并指导视频合成相关 Agent（如 `video_composer`）与工具的正确用法，确保：
- 自主化：由 ReAct 的 PLAN 决策工具与顺序，Agent 不硬编码流水线；
- Tools‑First：所有外部 I/O 通过 Function Call（FC）+ Base 执行器；
- Prompt Neutrality：提示仅提供“中立事实+目标/约束”，不写工具名/参数名；
- 记忆解耦：仅写“事实产物”，失败 fail‑fast，错误可观测；
- 策略守卫：参数注入与前缀/模板校验由 Tool Manager 策略统一执行。

## 1. 组合工具（Composition Tool）

- 工具：`composition_tool`
- 动作：
  - `synchronize_audio(video_file, audio_file, output_filename, audio_volume?, video_volume?, ducking?, ducking_params?)`
  - `compose_story_video(scenes[{video_file, duration?}], output_filename)`
- 行为：
  - 仅做媒体合成/混流，返回本地产物（`output_path` 等）；
  - 不做上传/发布（是否上传由 PLAN 决定，另行规划 `file_storage_tool` 或 `oss_storage`）。
- 目的：把“确定性顺序”的多步合成封装为高阶动作，降低 LLM 组合复杂度，避免在 Agent 中硬编码流程。

## 2. VideoComposer 的 ReAct 模式

- OBSERVE（仅事实 + Hints）
  - 事实：`final_video.path/url`、`voice_assets[{scene_number, local_path, audio_url, duration}]`、`background_music{path,url,duration,style}`、`voice_settings`、`ducking_config`。
  - Hints（非强制）：`requests.voiceover_requested`、`requests.bgm_requested`。
- PLAN（FC）
  - 消息只描述目标（如“如需，请在现有成片上添加配音或背景音乐；对齐时长与 ducking；直接函数调用，不要解释”）。
  - 由 LLM 自主选择使用 `composition_tool` 或原子工具（`ffmpeg_tool`、`audio_processor`、`file_storage_tool`、`oss_storage`）。
- ACT
  - 仅执行 PLAN 的 `tool_calls`（`BaseAgent.execute_tool_calls`）；
  - 产物统一归一化为 artifact 字段（`file_path/image_url/video_url/audio_url/duration_sec/prompt_text`）。
- REFLECT
  - 若未产出本地成片：返回 `partial`（如 `no_planned_output`），由上层编排器续派。

## 3. 工具策略与参数守卫

- YAML 策略在 `backend/app/agents/config/tool_policies.yaml`：
  - 对 `video_composer` 暴露 `composition_tool`、`ffmpeg_tool`、`audio_processor`、`file_storage_tool`、`oss_storage`；
  - 上传类工具的 `destination_key` 必须在 `workflows/{wf_id}/...` 前缀下；
  - `wf_id/scene_number/execution.id` 等必填由运行时注入（仅“缺参+有模板”时注入），越权/缺必填直接报错。

## 4. 错误处理与记忆写回

- Shared WM 写回失败需 fail‑fast：记录 `logger.error(..., exc_info=True)` 并 `raise AgentError`；
- 不吞异常，不做“继续完成”的隐式降级；
- 仅写事实（如 `final_video{path,url,storage,...}`）。

## 5. 禁止事项

- 禁止在 Agent 中：
  - 直连 `use_tool`（外部 I/O 必须走 FC）；
  - 在 ACT 内“兜底合成/程序化下载”；
  - 在 PLAN 提示里指名具体工具/动作名。
- 组合工具中：
  - 不做上传/发布；不在工具里“隐式”写 WM（保持纯函数式语义）。

## 6. 迁移指引（Legacy → 组合工具/PLAN）

- 移除 Agent 内部的：
  - 自建 FFmpeg 命令、滤镜图、场景时间线生成；
  - DB 资源写入与自定义 metadata/summary 构造。
- 需要这些能力时：
  - 在工具层封装为可控动作（原子或高阶），交给 LLM 规划；
  - 或放到离线处理/服务层，避免 Agent 侵入业务实现。

## 7. 示例（PLAN 意图表达，非工具名）

- 仅提供目标与约束（示意）：
  - “如需，请在现有成片上添加配音；配音轨道与场景时长匹配；直接函数调用，不要解释。”
  - “如需，请添加背景音乐；按 ducking 配置压制；直接函数调用，不要解释。”
- 由 LLM 自主在已暴露的 schema 里选择 `composition_tool.synchronize_audio` 或原子工具序列。

---

此指南与 `docs/agents/tool_system_best_practices_2025.md` 配套，约束视频合成相关 Agent 与工具的正确边界。后续如扩展组合工具功能（如可选发布），需先在策略侧与设计侧达成一致，再进入实现。
