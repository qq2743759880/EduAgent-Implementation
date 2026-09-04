# task-P1C: Neo4j/Redis 断连熔断（快速失败 + 半开探测）

> **类型**：backend（容灾加固）｜**执行工具**：Trae｜**阶段**：收尾专项｜**工作量**：M
> **来源**：task39 批判②（P0 遗留）+ task33 批判②（半开并发/Redis 原子）
> **依据**：task39 实测 Neo4j 断连 RAG 2.8s→29.4s、AI 问答 22s→52.4s（能降级但慢到不可用）

## 1. 背景（真实数据）
- task39 故障注入：neo4j 断连 RAG 检索 2.8s→**29.4s**、AI 问答 22s→**52.4s**；redis 断连同样显著劣化
- 根因：Neo4j/Redis 断连时无 circuit breaker，每次请求等满超时再降级（task33 已有 per-server MCP 熔断，但 Neo4j/Redis 数据链路无）

## 2. 优化方向（竞品对标）
| 方向 | 竞品实证 | 落点 |
|---|---|---|
| **Circuit Breaker 三态** | 通用熔断（closed/open/half-open）+ 连续失败快速失败 | core/breaker.py（复用 task33 per-server 熔断模式）|
| **快速失败 + 半开探测** | Codex auto-review 拒绝熔断 + Polaris 模型 | Neo4j/Redis 连接层接入 |
| **降级不拖死** | Gremlin Chaos Engineering（最小爆炸半径）| 断连快速返回降级结果，不等超时 |

## 3. 实现规划要点
- Neo4j driver / Redis client 外层加 circuit breaker：连续 N 次失败→OPEN 快速失败（毫秒返回降级），30s 后半开放行探针
- 复用 core/breaker.py（task33 已实现连续失败模式 + CircuitOpenError）
- 降级结果带 degraded_reason + edu_degraded_total 计数（task39 已埋点）
- 注意：与 task39 批判①（LLM 延迟）独立，本任务专注 Neo4j/Redis 断连快速失败

## 4. 验收标准（Given/When/Then）
- Given Neo4j/Redis 断连，When 请求到达，Then 熔断 OPEN 后毫秒级返回降级（非等 30s 超时）
- Given 30s 后依赖恢复，When 探针，Then 半开放行成功→CLOSED 恢复
- Given 断连场景，When 压测，Then RAG 检索/AI 问答延迟回到 <5s（快速失败）

## 5. 交接
- 完工：test-reports\task-P1C-completion-report.md（断连延迟对比 + 熔断状态机实测）→ 停下等验收
- 测试窗口：无需 LLM，随时可测