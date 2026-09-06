# 文档治理记录（2026-09-06）

- Document Type: plan-attachment
- Parent Plan: PLAN-20260906-070
- Baseline implementation: b612963 (WIP)
- Baseline evidence: 78ff0a4
- Authority-entrypoint change: db74b6d
- Scope: document governance; no new business-plan acceptance

## Git 证据与历史修复

| 计划 | 修复前索引 / 正文 | 本次处理 | 依据 |
| --- | --- | --- | --- |
| 001 | archived / completed，文件仍在 active，archived_at=null | 索引恢复 completed；保持原位置与既有确认记录 | a2af5c0 已是 completed；15c95fc 归档 026 时误改了 001 的 status，未产生 001 归档操作 |
| 026 | completed / archived，文件位于 archive | 索引恢复 archived；保留 2026-03-26T14:19:04Z 原归档时间 | 15c95fc 的文件位置、正文、archived_at 与归档 note 一致，唯独 status 留错 |
| 003 | completed / blocked | 正文镜像同步 completed | 当前生命周期索引与既有结项 notes；不新增验收 |
| 007 / 008 / 009 / 036 / 038 | completed / in_progress | 正文镜像同步 completed | 当前生命周期索引与历史 notes；不复写旧验证结果 |
| 043 | draft / completed | 正文镜像同步 draft，附显式历史解释 | c193704 同一提交引入 completed 正文却保留 draft 索引；无充分生命周期确认依据，不能补造 completed |

001/026 使用 plan_ops 的索引读写接口恢复错位历史记录，而非执行新的完成/归档转换。该脚本常规 status/archive 命令不支持“恢复误写记录”；没有为通过状态机而临时搬文件、重开计划或伪造确认。

58 份验证/设计附件添加 Document Type 与 Parent Plan，正文及历史状态保留，不创建新生命周期条目。原全局 doctor 的 69 条报告分为 9 个状态不一致、2 个路径不一致和 58 个附件识别问题；仓库检查器按显式父归属区分附件。

## 有效规则入口与替代关系

- [文档中心](../../../README.md)指向各职责合同。
- [根指令](../../../../AGENTS.md)与[后端指令](../../../../backend/AGENTS.md)区分内循环、交付验收、runtime 终态。
- 六份旧指南保留历史正文并声明失效范围、替代链接；不再作为当前执行队列。
- [DP-001 复核](../../../deferred-plans/reviews/DP-20260331-001-20260906.md)保留 obs-ledger 迁移护栏，不声明迁移完成。

## 验证范围与限制

- 新检查器只读取已有索引与文档，不写 lifecycle，不自动修复或注册计划。
- 检查注册计划状态/路径/ID、附件父归属、Deferred 镜像及复审日期、维护入口与历史 replacement 的本地链接。
- 历史正文中已退役代码的链接不作为当前入口校验；全仓语义正确性不由这个脚本证明。
- PLAN-069 历史 A5 结果仍是原时点本地证据。2026-09-06 两次重跑均在测试收集前无输出并被中止；没有本轮通过结论。
- Marketing PNG 的 SHA-256 为 387476919723cfcc71cfc61389788e8e83997fa889a2b078ba1378ba14a94640，383131 bytes，与 HEAD LFS 指针相同。当前机器缺 git-lfs，未将其作为图片修改提交。
- Hosted CI、远程分支状态刷新和业务用户验收均未在本轮执行。

## 本轮检查结果

- `python3 -m unittest discover -s scripts/tests -p 'test_doc_governance.py'`：10 tests passed。
- `python3 scripts/check_doc_governance.py`：0 issues。
- `anchor_ops.py --root . doctor`：0 issues。
- 外部 `plan_ops doctor`：仅剩 58 个已明确父归属的附件识别报告，状态/路径不一致均已消除。
- 新增 `.github/workflows/documentation.yml`，在相关 PR、main/develop push 和手动运行时执行上述检查；本地通过不代表 hosted CI 已运行。
