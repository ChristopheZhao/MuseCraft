# 2026-03-25 Vibe Coding Architecture Drift Thread

## Problem
- 本轮讨论围绕一个反复出现的模式展开：
  - vibe coding 的新增实现没有从 canonical architecture 出发设计
  - helper、adapter、summary surface、wrapper 被持续当成扩展宿主
  - 最终代码表现为并列主路、旁路兼容链路和语义漂移累积
- 讨论结论是：
  - 表面问题是“屎山代码堆积”
  - 根因是 canonical architecture、authority object 和宿主归属没有先冻结为实现前提
  - 在这种环境下，coding agent 会自然选择最小阻力的增量扩展路径

## Why It Expands
- LLM/agent 默认偏向加法：更容易包一层、兼容一层、绕一层，而不是迁移 ownership、删除旧路径、做 breaking change。
- 只要仓库里已有旧 helper、compat adapter、summary surface，它们就会被模式匹配成“可继续挂逻辑的合法位置”。
- 如果 review 只看“功能通了没有”，不看“是否属于正确层级和宿主”，架构漂移就会被持续奖励。
- 如果新增过渡层没有明确退役计划，它们就会从短期 seam 演变为长期并列主路。

## Decision Rules
- 任何实现前必须先回答四个问题：
  - 这段逻辑回答什么业务问题
  - 该问题的 authoritative object 是什么
  - 它属于哪一层
  - 它的正式宿主是谁
- 一个业务问题只能有一个 authoritative surface；其他对象只能是 projection、diagnostics 或受控过渡态。
- 发现越层时优先回迁 ownership，不用新 wrapper、adapter 或 fallback 去掩盖旧设计问题。
- 新增 helper/adapter 必须附带退役计划；没有退役计划的兼容层默认是风险，而不是默认接受。
- 评审时先看 belongs，再看 works：
  - belongs -> authority -> contract -> behavior

## Reuse
- 适合作为后续 architecture review、coding-agent 提示模板、以及“是否允许新增 adapter/helper”的门禁依据。
- 也可作为多轮 vibe coding 结束后的复盘模板，用于识别哪些问题其实不是实现细节，而是 authority / ownership / contract 没被冻结。
