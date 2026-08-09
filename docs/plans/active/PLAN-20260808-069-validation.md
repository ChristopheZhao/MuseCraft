# PLAN-20260808-069 Validation

- Plan ID: PLAN-20260808-069
- Recorded At: 2026-08-08T03:03:21Z
- Status: draft (narrative mirror only; lifecycle truth in PLAN_INDEX.json)

## Purpose
- Record sprint-by-sprint verification for the anti-agentic 审查修复 plan.
- Link audit evidence, targeted tests, and regression surfaces without replacing their authoritative owner.

## Validation Matrix

### S1 — High 级修复
- Status: not started
- Planned checks (S1-4/S1-5 增补):
  - scene_continuity_analysis_tool 异常路径不再返回成功形态伪造决策（raise 或显式 fallback_reason）单测
  - script_generation_tool 三处 JSON 失败路径行为统一（与 :423 raise 对齐）单测
  - zhipu/kimi json_completion 注入 response_format、解析失败 raise 的单测；全仓 grep 确认无 `re.search(r'\{.*\}')` 贪婪兜底残留
- Planned checks:
  - S1-3 前置考证记录（orchestration_protocol completed-only 校验的引入提交与 PLAN-068/A6 关联结论）
  - build_subagent_report 放行 partial/failed 的单测；终态 finalization 拒绝非 completed 的单测
  - bgm 失败 → partial 上报 → LLM 裁决（非硬失败）端到端用例
  - quality_checker LLM 评估参与审批单测；LLM 失败降级信号（封顶 + requires_human_review + reported_gaps）断言
  - parameter_optimization_tool LLM 消费分支恢复单测；fallback 仅失败触发且 fallback_method=True
  - 回归：orchestration/continuation contract/A6 既有用例全绿
- Evidence:
  - (待补)
- Results:
  - (待补)

### S2 — Medium 级修复
- Status: not started
- Planned checks:
  - 每条目 targeted 单测（S2-1 至 S2-8）
  - 枚举映射快照测试：domain/enums.py AgentType 全成员在前端映射齐全、无折叠
  - data_persistence PERSISTING_DATA 枚举修正回归
  - 场景尾帧 workflow 隔离：跨 workflow 陈旧帧不泄漏用例
  - 前端 tsc + jest 全绿
- Evidence:
  - (待补)
- Results:
  - (待补)

### S3 — 死代码清理
- Status: not started
- Planned checks:
  - 清理后全仓 grep 无残余引用（quality_control / error_recovery / _perform_image_based_quality_check / intelligent_scene_planning / 情绪映射 / placeholder audio / build_dispatch）
  - `pytest backend/tests` 全绿（含被修正 mock 的 test_ai_service_integration）
- Evidence:
  - (待补)
- Results:
  - (待补)

## Audit Provenance
- 2026-08-08 anti-agentic workflow 审查：5 维度 / 29 findings / 13 confirmed（对抗验证）
- 完整发现与验证推理：session workflow run wf_caea6ecc-173 journal
- 被验证驳回的定性（不纳入本计划）：agents↔services import 方向、memory 两层归属、scene_contract freeze-only 注解——均有 docs/architecture/orchestration_context_memory_boundary_freeze_20260330.md 等冻结文档背书

## Notes
- 2026-08-08T03:03:21Z validation ledger created alongside draft plan
