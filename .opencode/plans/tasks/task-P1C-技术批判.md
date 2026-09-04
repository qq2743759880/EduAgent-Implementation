# task-P1C 验收批判（强制技术批判）

> 对象：task-P1C Neo4j/Redis 断连熔断（Trae，commit f1c5d37）
> 结论：**验收通过**（GWT①~④ 全绿、断连延迟 ms 级、竞品对标完整）。

## 实证结果
- commit `f1c5d37`（6 文件 +831/-50）；db_resilience.py + breaker 加固 交付。
- 契测 **29 passed**（P1C 7 + task39 回归 22）实跑确认。
- GWT① 三路径接线（graph_expand/get_or_load/vector Redis）；GWT② 状态机 CLOSED→OPEN(<1ms)→半开→CLOSED；GWT③ 降级埋点复用；GWT④ 断连 29.4s/52.4s→<5ms。
- 加固：breaker Redis 自残容错 + lambda 协程未 await bug 修复。

## 批判 1（P2）：检测窗口内仍有原失败成本（默认 5 连失败才开路）
- **问题**：socket 超时尾（非连接拒绝）时窗口内单次仍慢（报告诚实披露）。
- **方案**：生产按依赖超时类型调 NEO4J_REDIS_BREAKER_FAILURES，或对超时尾场景用更快失败阈值。

## 批判 2（P2）：graph_builder 写路径未接线（后台导入）
- **问题**：知识库后台导入的 Neo4j 写路径未熔断（报告披露待评估）。
- **方案**：导入场景断连时评估是否需快速失败或队列重试。

## 批判 3（P3）：共享状态多实例一致性依赖 Redis backing（已加固本地回退）
- **问题**：多实例熔断状态经 Redis 共享，Redis 自身故障时本地回退（状态分片）。
- **方案**：接受回退语义（各实例独立熔断），或后续评估分布式熔断协调。

**结论**：三条为后续调优/评估项，不阻塞 task-P1C。