# 文档维护规则

- Document Status: current
- Owner: documentation / architecture / plan lifecycle owners by scope
- Reviewed At: 2026-09-06

## 职责与入口

[文档中心](README.md)按语义范围指向现行约束。根/目录 AGENTS 规定开发原则，架构合同规定所有权，计划规定该任务的执行和替代范围。不存在“最新文档自动覆盖全部规则”的全局优先级。

修正一个合同必须同步其入口、直接冲突的 AGENTS/指南以及明确的替代关系。历史正文保留，页首写 `Document Status: historical`、`Superseded Scope` 和可点击的 `Replacement`；局部替代要说明仍有效的原则。提案必须标明尚未成为执行指令。禁止将历史计划的复选框当作当前待办。

## 计划与附件

[PLAN_INDEX.json](plans/PLAN_INDEX.json)独占生命周期状态，计划正文 `- Status:` 只是镜像。常规生命周期更新由 sdd-plan-maintainer 的 plan_ops 管理。镜像同步不表示重新运行测试或重新验收。

计划正文通过索引注册。验证附录、边界清单、设计补充只声明 `Document Type: plan-attachment` 和 `Parent Plan: PLAN-...`；正文中的旧状态属于该时点证据，不是另一份生命周期记录。父计划存在不代表附件自动具备当前架构权威。

历史记录错位必须保存 Git 证据、旧值、新值和修复理由。恢复已发生的归档与宣布新归档要分开记录；不能凭目录名或“测试通过”补造用户确认。完成和新归档继续遵循原有验收规则。

## 验证证据

每次 checkpoint 保留日期、代码 commit 或明确 WIP 锚点、命令、结果及覆盖限制。后续版本通过新的证据链接建立追溯；不修改旧测试数量，使其看起来覆盖了新代码。区分本地验证、已提交、hosted CI、用户验收。

[Deferred 索引](deferred-plans/DEFERRED_PLAN_INDEX.json)管理长期护栏；复审只说明与当前设计的关系，不以复审代替迁移完成。

## 本地和 CI 检查

```bash
python3 scripts/check_doc_governance.py
python3 -m unittest discover -s scripts/tests -p 'test_doc_governance.py'
```

检查所有注册计划的 ID、状态镜像、路径及附件父归属，Deferred 状态/日期镜像和 CURRENT 引用，以及维护入口与历史替代声明中的本地 Markdown 链接。入口范围是根 AGENTS、后端 AGENTS、docs/README、本文和 PLAN-070 证据记录；不宣称扫描整个历史档案中的所有旧链接。发现问题直接报错，不自动修复状态或创建计划。

旧版全局 `plan_ops doctor` 会把 active/archive 下所有未注册文件视为孤立计划，因此会报告已声明父归属的附件。它仍可提供状态/路径诊断，但其附件发现结果不能当作新计划注册指令。本仓库检查器读取同一索引，不维护第二份生命周期状态。

机器检查不裁决语义冲突。修改所有权、完成规则或 fallback 语义时，审阅必须比较同一边界的现行合同及受影响指令。
