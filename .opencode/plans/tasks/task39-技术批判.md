# task39 验收批判（强制技术批判）

> 对象：task39 性能压测 + 容灾演练（Trae，commit 6d19d69→a635baf）
> 结论：**验收通过**（GWT①~⑤ 覆盖，5 项达标，LLM 档位超标诚实披露）。

## 实证结果
- commit 链 6d19d69→9a9dc6e→a635baf，HEAD=a635baf。
- GWT① 缓存链路 P95 22/21ms ✅（Redis 命中 99.03%）；LLM 档位 P95 25~32s/TTFT 17~21s ❌ 超标（根因：链路深度 5 次串行 LLM）。
- GWT② 六依赖降级无 5xx ✅ + escalation 幂等（T1/T2 20 并发=1/T3 skipped=2688/T4 字段全对）✅ 复跑归档。
- GWT③ 预热 1816ms ✅；GWT④ checkpointer 并发 100/100 P95 56ms（修 3 根因：IPv6/锁表/ULID）✅；GWT⑤ 令牌桶 2.00×→1.00× ✅。
- **发现修复 P0 缺陷**：/api/series/{id}/cohorts 无条件 500。
- 竞品对标真实 URL（Locust/Chaos Monkey/Gremlin/Prometheus/Anthropic）。

## 批判 1（P0，遗留）：LLM P95/TTFT 严重超标（25~32s vs 8s，TTFT 17~21s vs 3s）
- **问题**：主链路 5 次串行 LLM 调用，task29 批判② 未彻底治理。
- **方案**：单开任务：削减链路深度/引入 prompt cache/流式分段返回（超出 task39 边界，报告明确）。

## 批判 2（P0，遗留）：Neo4j/Redis 断连无熔断（RAG 2.8s→29.4s）
- **问题**：能降级但慢到不可用。
- **方案**：加 circuit breaker（快速失败+半开探测）。

## 批判 3（P1，遗留）：MinIO 上传静默延迟失败（200+pending 后台失败）
- **问题**：不符合 §6.4「明确报错」契约。
- **方案**：后台失败可查询状态 + edu_degraded_total{component="minio"}。

## 批判 4（P2，环境）：checkpoint 复跑归档待 Redis 恢复；baseline 对照待 VM 恢复
- **问题**：环境事故（VM 不可达+Redis WSL 禁）导致两项未复跑归档。
- **方案**：环境恢复后复跑。

## 批判 5（P2）：test_contract_task94 硬编码 124 vs 实际 178 持续失败
- **问题**：LIVE skill 断言绝对数量，增删文件即红。
- **方案**：改≥下限或校验自洽性。

**结论**：批判①②为 P0 遗留（单开任务），③④为环境/后续，⑤为测试更新；task39 本体验收通过。