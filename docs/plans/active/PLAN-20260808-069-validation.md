# PLAN-20260808-069 Validation

- Plan ID: PLAN-20260808-069
- Recorded At: 2026-08-08T03:03:21Z
- Status: in_progress (narrative mirror only; lifecycle truth in PLAN_INDEX.json)

## Purpose
- Record sprint-by-sprint verification for the anti-agentic 审查修复 plan.
- Link audit evidence, targeted tests, and regression surfaces without replacing their authoritative owner.

## Validation Matrix

### Amendment A1 — Root-owned anti-agentic/fallback closure
- Status: negative-first design registered; implementation not started
- Contract checks:
  - canonical partial/failed report parses without implying success
  - no-gate and empty-standby non-success reports still reach LLM disposition
  - `completed` alone enters ordinary success finalization; partial promotion requires explicit `accept_with_gaps` plus non-empty gaps; failed cannot be accepted
  - disposition action/target/budget types are exact and malformed LLM output fails closed
  - Agent/tool execution failure enters typed observation; exception-name substring retry no longer exists
- Fallback/semantic checks:
  - active scene analysis/continuity/script paths contain no keyword-owned semantic decision or success-shaped fabricated fallback
  - every reviewed LLM JSON call requests `json_object`, parses once, and raises a typed failure instead of regex extraction
  - unallocated parameter optimization is not production-registered/exposed
  - QualityChecker subjective assessment changes with the LLM result; LLM failure yields partial + typed gap and no fabricated score
- Authority/SoT checks:
  - VideoGenerator without shared authority binding raises `scene_output_authority_unbound` and cannot report completed
  - noncanonical runtime node values are rejected rather than trimmed/case-folded
  - producers do not emit `reflection.completion_state`; continuation/execution contracts keep one exact schema per module boundary
  - non-authoritative completion events do not create/advance Task lifecycle state
  - final-video read-model visibility cannot precede terminal attempt authority, including a simulated interruption between candidate publication and completion
- Scope checks:
  - no frontend enum, API placement, character-identity redesign, Docker, launcher, authentication, packaging, or unrelated cleanup enters A1 commits
- Baseline evidence:
  - 2026-08-15 current architecture + A6 contract selection: `171 passed, 2 warnings`
  - review found the existing partial-rejection test locks an obsolete protocol policy and found no tests for missing scene authority binding or noncanonical runtime node SoT
- Results:
  - pending negative-first implementation

### Historical S1 — Superseded by Amendment A1
- Status: historical inventory only
- Planned checks (S1-4/S1-5 增补):
  - scene_continuity_analysis_tool 异常路径不再返回成功形态伪造决策（raise 或显式 fallback_reason）单测
  - script_generation_tool 三处 JSON 失败路径行为统一（与 :423 raise 对齐）单测
  - zhipu/kimi json_completion 注入 response_format、解析失败 raise 的单测；全仓 grep 确认无 `re.search(r'\{.*\}')` 贪婪兜底残留
- Planned checks:
  - S1-3 前置考证记录（orchestration_protocol completed-only 校验的引入提交与 PLAN-068/A6 关联结论）
  - build_subagent_report 放行 partial/failed 的单测；终态 finalization 拒绝非 completed 的单测
  - bgm 失败 → partial 上报 → LLM 裁决（非硬失败）端到端用例
  - quality_checker LLM 评估参与审批单测；LLM 失败降级信号（封顶 + requires_human_review + reported_gaps）断言
  - Historical expectation invalidated by A1: parameter_optimization fallback is removed/de-registered rather than asserted via `fallback_method=True`
  - 回归：orchestration/continuation contract/A6 既有用例全绿
- Evidence:
  - S1-3 考证（2026-08-09）：git blame 确认 L107-120 出自 048a338（A3/A4/A5 合并提交 "orchestration thin contracts"）；PLAN-068 log 2026-07-25T17:44（A4 "reject failed/partial ... before output or attempt success"）、2026-07-26T10:03（A5 "explicit report status is the sole orchestration outcome"）、2026-07-26T10:22（四提交映射：4385e22/5660f4e/048a338/ceffacd）
  - 调用点语境：orchestrator.py:1754（execute 后立即 parse，partial 在此被击毙）、:2064（open_runtime_decision 路径，partial 的天然去处）
- Results:
  - S1-3 考证 PASS：确定采用拆分方案（Option A），A4/A5 不变量（非 completed 不得进入发布/attempt success）保留在 `_finalize_successful_agent_runtime_boundary`，partial/failed 路由到 runtime decision；实现须 negative-first（先加反例测试）

### Historical S2 — Superseded by Amendment A1 scope
- Status: historical inventory only
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

### Historical S3 — Deferred cleanup inventory
- Status: not an A1 completion gate except for directly exposed fallback/SoT risk
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
- 2026-08-15 Amendment A1 superseded the prior execution ordering and removed the stale fallback-method acceptance expectation.
