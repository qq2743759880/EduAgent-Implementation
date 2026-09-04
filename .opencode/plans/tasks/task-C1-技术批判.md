# task-C1 验收批判（强制技术批判）

> 对象：task-C1 上下文动态压缩（Trae，commit 0974c8a）
> 结论：**验收通过**（AC1~AC5 全绿、P4 批判点闭环、向后兼容设计正确）。

## 实证结果
- commit `0974c8a`（5 文件 +1748）；compaction.py BudgetAllocator/anchor_gate/llm_select_fragments 交付。
- 契测 **66 passed 1 skipped**（C1 14 + task26/96 回归 33 + task97 19）实跑确认，无回归。
- AC1 预算 Σ=1.0；AC2 A/B：固定 6 轮召回 0→动态召回 1、token 3672→658（P4 批判闭环）；AC3 规则回退 4 键逐键兼容；AC4 锚定闸门前字节零改动；AC5 默认路径逐字节兼容旧版。

## 批判 1（P2）：真实 LLM 动态选片段未实测（窗口外，mock 验证）
- **问题**：llm_select_fragments 用 mock，真实 make_fast_llm（火山 ark deepseek-v4-flash）选片段未在窗口内补测。
- **方案**：18:00-9:00 窗口内跑 compact_messages(llm=make_fast_llm(), anchor_round=3) 补证 keep_round_ids 质量。

## 批判 2（P2）：graph.compact_node 未装配 feature flag（锚定/LLM 默认关闭）
- **问题**：为保零回归，compact_node 零改动，锚定+LLM 选片段未在真实对话链路启用（报告明确"由上层装配"）。
- **方案**：编排层在 apply_context_strategy/compact_node 注入 anchor_round=settings.ANCHOR_ROUND + llm=make_fast_llm() 后灰度观察。

## 批判 3（P2）：锚定冻结区超阈值时兜底收缩有限
- **问题**：极端场景（冻结区本身超阈值）frozen 不可收缩，只能收缩选中轮与 summary。
- **方案**：实际生产中监测冻结区 token 占比，超阈值时告警或动态降 ANCHOR_ROUND。

**结论**：三条为后续验证/装配项，不阻塞 task-C1。

> ✅ **2026-08-28 已实测闭环**（真实 LLM 选片段 真实 LLM 验证通过，见 session-memory 九十三节）
