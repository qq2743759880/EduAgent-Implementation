# task-G1 验收批判（强制技术批判）

> 对象：task-G1 token 级并发预算 + 用户分级队列（Trae，commit cd71ad5）
> 结论：**验收通过**（AC1~AC5 全绿、双层防御设计正确、竞品对标完整）。

## 实证结果
- commit `cd71ad5`（5 文件 +1156）；guard.py TokenBudgetGuard/retry.py 交付。
- 契测 **37 passed 1 skipped**（G1 18 + task26 回归 19）实跑确认，无回归。
- AC1 速率超排队不拒绝（queued_token_rate）；AC2 L3 先出队（[L3,L2,L1]）；AC3 用户配额友好拒绝（user_token_quota_exceeded 不 500）；AC4 智能退避表驱动；AC5 请求数闸保留为第二道防线。
- 双层防御：token 配额→token 速率→请求数并发闸。

## 批判 1（P2）：retry.py 未接入实际重试调用点（联动 task-T1）
- **问题**：智能退避策略交付，但 generator.py/agent.py 实际重试路径未接入（报告明确"联动 task-T1"，避免回归）。
- **方案**：task-T1（工具闭环）接入 classify_error + next_backoff 到真实重试路径。

## 批判 2（P2）：token 速率窗口为 60s 固定窗口，瞬时突发可超
- **问题**：非严格滑动窗口，窗口边界可能短暂超额（报告披露）。
- **方案**：task39 压测复测时评估换令牌桶平滑。

## 批判 3（P2）：预估 token 依赖 request_meta，缺失时兜底 2000 可能虚高/虚低
- **问题**：ESTIMATE_DEFAULT_TOKENS=2000 兜底，若调用方未传 request_meta，预估不精确影响排队公平。
- **方案**：task-T1 或后续强制 request_meta 传入，降低兜底依赖。

**结论**：三条为后续联动/改进项，不阻塞 task-G1。