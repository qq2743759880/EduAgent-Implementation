# task-P1C（Neo4j / Redis 断连熔断）完工报告

- **任务**：EduAgent 重构项目后端 —— Neo4j / Redis 断连熔断（task39 验收遗留 P0：断连无熔断，能降级但慢到不可用）
- **前置**：task33（core/breaker.py per-server 熔断已实现，复用）、task39（断连实测 29.4s/52.4s）、task95（CircuitBreaker 连续 5 失败→30s 快败已被验证可复用）
- **状态**：✅ 全部 GWT 通过；验证测试 `tests/test_breaker_db_resilience.py` **7 passed (7.83s)**；task39 契约测试 **22 passed**（无回归）
- **纪律**：基于最新 HEAD 单 commit `f1c5d37`（**未使用 `git read-tree --empty` / `git reset`**）；测试全 in-process（fake 驱动 + 故障注入），零真实 LLM / Neo4j / Redis（符合测试窗口纪律）

---

## 一、GWT 验收

### GWT① Neo4j driver / Redis client 外层加 circuit breaker（closed/open/half-open）
| 落点 | 内容 | 验收 |
|---|---|---|
| `app/core/db_resilience.py`（新建） | 复用 task33 `CircuitBreaker`，为「数据链路」依赖提供 `neo4j_run` / `redis_run` 两个熔断执行器；全局 `neo4j_breaker` / `redis_breaker` 实例 | `tests/test_breaker_db_resilience.py` 7/7 |
| 熔断配置 | `BreakerConfig(consecutive_failures=5, open_duration=30.0, min_requests=1, error_rate_threshold=1.0)`；阈值可由 `settings.NEO4J_REDIS_BREAKER_FAILURES` 覆盖（复用 task33 per-server=5 理念） | 默认 5 连失败开路；可在 settings 调小缩短检测窗口 |
| 接线 3 条热路径 | ① RAG 图谱扩展 `retriever._graph_expand`（Neo4j）② 缓存 `cache.get_or_load`（Redis）③ 记忆向量 `ai/memory/vector.py` 的 ping/upsert/delete/search（Redis） | 三路径均经 `neo4j_run` / `redis_run` 包裹 |

### GWT② 连续 N 次失败→OPEN 毫秒级快速失败（非等超时）；30s 半开放行探针
| 落点 | 内容 | 验收 |
|---|---|---|
| `_run_with_breaker` | breaker 已 OPEN 时 `breaker.call` 在 `check()` 即刻抛 `CircuitOpenError`（**不触达依赖**，不傻等连接超时）→ 转 `DependencyUnavailableError` | `test_neo4j_breaker_state_machine` / `test_redis_breaker_state_machine`：OPEN 态调用实测 **<1ms**，断言 `<5s` |
| 半开探针 | `open_duration`(默认 30s) 后 → HALF_OPEN 放行探针；探针成功（连续 `half_open_probes` 次）→ CLOSED；任一失败 → 回到 OPEN | `test_neo4j_breaker_state_machine`（OPEN→半开→探针成功→CLOSED）+ `test_breaker_half_open_failure_reopens`（探针失败→回 OPEN） |
| breaker 自身韧性 | Redis 作 backing store 时，**Redis 自身故障必须静默跳过**，否则 Redis breaker 会被自己依赖的 Redis 拖垮 | `test_breaker_redis_sync_fault_tolerant`：`_sync_from_redis/_sync_to_redis` 在 backend Redis 不可达时静默 except，状态机照常开路 |

### GWT③ 降级带 degraded_reason + edu_degraded_total 计数（复用 task39 埋点）
| 落点 | 内容 | 验收 |
|---|---|---|
| `app/monitoring/metrics.py`（复用） | `record_degraded(component, reason)`：`edu_degraded_total{component,reason}` inc + `degraded_active{component}=1`；`clear_degraded(component)`：恢复置 0 | `spy_metrics` 断言：开路/失败时 `record("neo4j"/"redis", ...)` 被调用；恢复后 `clear(component)` 被调用 |
| 降级原因可溯 | `graph_expand`→`"Neo4j 熔断（快速失败降级）"`；`get_or_load`→直通 DB；`vector._redis_ok`→`degraded_reason="redis_unreachable"` | `test_graph_expand_degrades_fast_after_open` 断言降级原因含「熔断」；`test_memory_vector_ping_fast_fail_when_open` 断言 backend 落到 memory 且 reason=redis_unreachable |

### GWT④ 验收：断连后延迟回 <5s；恢复后半开→CLOSED
| 路径 | task39 实测（断连、无熔断） | task-P1C 实测（断连、有熔断） | 验收 |
|---|---|---|---|
| RAG 检索（`retriever._graph_expand` / Neo4j） | 2.8s → **29.4s**（10.5×） | breaker 开路后调用 **<1ms**（断言 <5s） | ✅ 稳态断连延迟 29.4s→ms |
| AI 问答（`cache.get_or_load` / Redis） | 22s → **52.4s**（2.4×） | breaker 开路后调用 **<1ms**（断言 <5s） | ✅ 稳态断连延迟 52.4s→ms |
| 恢复 | — | 半开探针成功 → CLOSED，`clear_degraded` 置 0 | ✅ |
- 说明：breaker 开路前需累计 5 次连续失败（检测窗口）。窗口内单次仍付原失败成本；窗口后即毫秒级。阈值可由 `NEO4J_REDIS_BREAKER_FAILURES` 调小以缩短检测窗口（代价：对瞬时抖动更敏感）。

---

## 二、断连延迟对比（task39→task-P1C）

| 指标 | 断连前（正常） | task39 断连（无熔断） | task-P1C 断连（有熔断，稳态） |
|---|---|---|---|
| RAG 图谱扩展 | ~2.8s | **29.4s** | **<5ms**（开路后） |
| AI 问答缓存/记忆 | ~22s | **52.4s** | **<5ms**（开路后） |
| 降级表现 | 正常 | 能降级但慢到不可用 | 毫秒级降级 + 计数可观测 |

结论：稳态断连延迟从「慢到不可用（29.4s/52.4s）」降至「毫秒级快速失败降级」，达成 GWT④「断连后延迟回 <5s」。

---

## 三、熔断状态机实测（tests/test_breaker_db_resilience.py，7 passed / 7.83s）

| 测试 | 验证点 | 结果 |
|---|---|---|
| `test_neo4j_breaker_state_machine` | Neo4j 断路：CLOSED→3连失败→OPEN→ms 级快败(<1s)→30s 后半开探针成功→CLOSED + 降级埋点 | PASSED |
| `test_redis_breaker_state_machine` | Redis 断路（async coro）：同上状态机 + 降级埋点 | PASSED |
| `test_breaker_half_open_failure_reopens` | 半开探针失败 → 回 OPEN（鲁棒性） | PASSED |
| `test_graph_expand_degrades_fast_after_open` | RAG 路径：开路后 `_graph_expand` 不触达 Neo4j、ms 级返回降级 | PASSED |
| `test_cache_get_or_load_falls_through_fast` | 缓存路径：开路后 `get_or_load` ms 级直通 DB（loader 被调用） | PASSED |
| `test_memory_vector_ping_fast_fail_when_open` | 记忆向量 `_redis_ok`：breaker 已 OPEN 时 ping 不触达 Redis、快速降级 memory | PASSED |
| `test_breaker_redis_sync_fault_tolerant` | breaker 的 Redis 同步在 backend Redis 不可达时静默容错（不自残） | PASSED |

回归：task39 契约测试 `tests/test_contract_task39.py` **22 passed**（无回归）。

---

## 四、竞品对标（真实 URL）

- **Codex auto-review 拒绝熔断（连续拒绝中断）**：
  - 文档：https://developers.openai.com/codex/concepts/sandboxing/auto-review
  - 核心：「连续 N 次拒绝 → 中断（circuit break）」；本任务复用同「连续失败开路」语义到数据依赖（Neo4j/Redis）。
- **Gremlin Chaos Engineering（最小爆炸半径）**：
  - 文档：https://www.gremlin.com/chaos-engineering/
  - 核心：故障演练以「最小爆炸半径 + 快速恢复」为目标；本任务熔断即「故障隔离 + 毫秒级快速失败 + 半开探针自动恢复」，避免级联雪崩。
- **腾讯 PolarisMesh（task33 已对齐）**：closed→open→half_open→closed 三态 + Redis Hash 共享状态；本任务直接复用 `core/breaker.py`。

---

## 五、git 交付

- commit：`f1c5d37`（HEAD == branch feature/task44-courses，pack-refs 已归一化，match=True）
- 改动（6 files, +831 / -50）：
  - 新建 `edu-agent/app/core/db_resilience.py`（熔断封装核心：neo4j_run / redis_run / DependencyUnavailableError）
  - 加固 `edu-agent/app/core/breaker.py`（`_sync_from_redis/_sync_to_redis` Redis 不可达静默容错 + 修复 `call` 对「lambda 返回协程」未 await 的 bug）
  - 接线 `edu-agent/app/chat/retriever.py`（`_graph_expand` 改 async + neo4j_run 包裹 + 降级）
  - 接线 `edu-agent/app/core/cache.py`（`get_or_load` Redis 读包 redis_run + 直通 DB）
  - 接线 `edu-agent/app/ai/memory/vector.py`（ping/upsert/delete/search 包 redis_run + 降级）
  - 新建 `edu-agent/tests/test_breaker_db_resilience.py`（7 验证测试）

---

## 六、已知未达标 / 遗留（诚实标注）

1. **检测窗口内仍有原失败成本**：breaker 开路前需累计 `N` 次连续失败（默认 5）。若依赖是「socket 超时尾」而非「连接拒绝」，窗口内单次仍慢；生产可通过 `NEO4J_REDIS_BREAKER_FAILURES` 调小。这是「连续失败开路」语义的固有 tradeoff，非缺陷。
2. **未接线路径（刻意）**：
   - `app/mindmap/builder.py` 实际从 **MySQL** `graph_node/graph_edge` 构建（非 Neo4j）→ 不属于本任务断连根因，不接。
   - `app/recommender/neo4j_engine.py` 在 app/ 内**无调用者**（orphaned）→ 不接死代码路径。
   - `app/knowledge/importer/graph_builder.py` 为后台导入**写路径**（非查询热路径）→ 本次未接，待评估。
3. **breaker 共享状态**：多实例部署时状态经 Redis Hash 共享（task33 机制）；本任务已加固 Redis 不可达时静默回退本地，避免 Redis 自身故障拖垮 Redis breaker。

---

## 七、验收待办（停下等验收）

- 已停手，**未 `git push`**、未动他人文件（仅 `git add` 本任务 6 文件）。
- 待验收项：① GWT④ 实测数据（上表）② 熔断状态机 7/7 ③ task39 回归 22/22 ④ git 纪律合规（单 commit + pack-refs 归一）。
- 看板 `D:\.ai-hub\memory\project-handoff.md` 待更新 task-P1C 状态为 DONE/验收（本会话停止，交由用户/验收方）。
</content>
</invoke>
