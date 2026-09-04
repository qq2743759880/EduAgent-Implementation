# task39 性能压测 / P95 治理 — 完工报告

- 任务：EduAgent task39 性能压测 / P95 治理（P3 优先级）
- 执行 agent：task39 压测执行 agent（后端 T2 链，独立实证）
- 完成日期：2026-09-04
- 状态：**可实证部分已独立实证；真 Redis 项登记 gap（环境不可达）**

> 纪律声明：本报告所有压测数据为对后端 **127.0.0.1:8000 真实 HTTP 并发**的独立实测，非 mock、非推断。

---

## 1. 资产消费证据

按 tt 工作流 §5.2「资产消费证据」硬约束，如实列出消费资产与实际用途（读了什么 → 自检发现并修掉什么 / 无发现）。

| 资产 | 路径 | 用途 / 实际调用 | 消费证据 |
|------|------|----------------|----------|
| ponytail | `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md` | 压测器最小实现：复用 requests+ThreadPoolExecutor，不引 locust/额外依赖；复用已有 `scripts/eval/stress.py` 的 `_p95` 口径与「不 mock」纪律；逐 op 判断是否值得改产品代码 → 结论「报告为准、不强改」 | 不再新建抽象；压测脚本仅 1 个文件；改进仅登记不盲改（见 §5 论证） |
| tt 方法论 | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` **§5.2** | 完工回传机制（只传文件路径/报告落 test-reports/）；验收须独立实证（真实 HTTP）；完工前自查三视角 | 压测=真实 HTTP 并发取数；报告含资产锚点 + 内核词 `assetConsumed` |
| review 批判内核 | `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` | 完工前按批判三视角过自己的压测设计与结论 | 见下「逐批判记录」 |

**自检发现并修掉的问题**：压测脚本首轮 `RW` 被解析为 float 导致 `range()` 崩（`TypeError: 'float' object cannot be interpreted`）——已修为 `int(os.environ.get(...))` 后重跑出数。属脚本自身缺陷，与后端无关，已修。

**assetConsumed 锚点**：`ponytail`（最小实现/报告为准）+ `tt §5.2`（独立实证/回传报告）+ `review`（批判三视角）。

### agent × skill × workflow 矩阵

| agent 角色 | skill / 资产 | workflow | 本任务落点 |
|-----------|--------------|----------|-----------|
| 压测执行 agent（本 agent） | ponytail（最小压测实现） | 独立实证：真实 HTTP 并发取 P95/吞吐 | `test-reports/task39_stress.py`（1 个文件） |
| 压测执行 agent | tt §5.2（回传/验收纪律） | 只传报告路径、验收独立实证 | 本报告 `test-reports/task39-perf-completion-report.md` |
| 压测执行 agent | review skill（批判三视角） | 完工前自查 | 结论双应力证（见 §4/§5），不摸黑改产品 |

> 编排者注：本任务为单 agent 独立实证（N=1 模式，tt §5.0），不派独立子 agent 做二次开发；验收由测试 agent 复跑 `tests/test_contract_task39.py`（22 passed）+ 复核本报告 P95 数字。

### 逐批判记录（完工前自查）

1. **批判（交互态/阈值是否达标可证）**：P95 超标判定必须有客观阈值。→ 采用容忍阈值 5s（任务语义「如 >5s」），concurrency 50 与 100 两档对拍。结论可机验。
2. **批判（边界/并发档位是否覆盖真实负载）**：单点浏览负载通常在个位~数十并发。→ 用 50/100 两档覆盖「偏高并发」，并实测 100 档退化路径，供治理参考。
3. **批判（错误处理/压测结果是否可信）**：不能把冷启动首包混进样本。→ 脚本先 `warmup()`（4 次）再计样本；每请求 HTTP 状态与异常单独归集，确认 0 err、100% 200。压测无失败请求，数据纯净。
4. **批判（是否有「看似达标实则空断言」）**：不能只报 p95<5s 就完事。→ 同时报 p50/p90/p95/p99/mean/max/rps，暴露高并发下的恶化趋势，指导治理。

---

## 2. 既有压测 / 性能治理定位

- **既有压测**：`edu-agent/scripts/eval/stress.py` —— 这是 task29 的 **LLM 端到端压测 + 成本测算器**（L1~L3 各档 6 节点并发 → p95，含 `_p95()` 工具函数、流式 TTFT、rerank sidecar vs 同进程吞吐对比）。**可复用**：其 `_p95()` 实现口径（排序后取 0.95×(n-1) 位）与「不 mock、真实并发」纪律，本任务沿用。但它是 LLM/向量导向，**不覆盖**纯读型 HTTP 并发 P95——因此本任务独立新增读型压测器。
- **既有治理**：
  - 课程域 service 已预埋缓存点 `app/core/cache.py::get_or_load`（详情/班次详情走 Redis 缓存；列表 `list_series` **未走缓存**，每请求直查 asyncmy MySQL）。
  - `app/config.py`：`MYSQL_POOL_SIZE=10`、`MYSQL_POOL_ACQUIRE_TIMEOUT=10`、`MYSQL_POOL_ACQUIRE_RETRIES=2`、`WORKERS=1`。
  - `app/database.py::_pool_acquire`：并发闸信号量（pool ≤ maxsize），防连接池占满挂死（task04 遗留修复）。
- **既有 task39 契约测试**：`edu-agent/tests/test_contract_task39.py` —— 纯单元回归（Redis 回环归一化、降级指标、预热后端感知、cohorts 分页壳 P0）。**真实状态已核实：`22 passed in 4.95s`**（无 MySQL/Redis 依赖，任何环境可跑，未因 Redis 环境性失败）。

---

## 3. 独立实证：真实并发压测 P95 / 吞吐（读型端点）

- 压测器：`test-reports/task39_stress.py`（新增，最小实现：requests.Session + ThreadPoolExecutor）。
- 端点：`GET http://127.0.0.1:8000/api/series`（列表，含分页筛选；真实 MySQL 查询路径）。`/api/courses` 为旧路由已 308 重定向（task11），故以 `/api/series` 为准。
- 鉴权：student token `user000001 / Test@123456`（登录成功 `code:0`，Bearer 头走鉴权读路径）。
- 预热：每档先 `warmup()` 4 次排冷启动；每请求 HTTP 状态单独归集，确认 **0 异常、100% 200**。

| 并发 | 总请求 | 墙钟(ms) | RPS | P50(ms) | P90(ms) | **P95(ms)** | P99(ms) | mean(ms) | max(ms) | err |
|------|-------:|---------:|----:|--------:|--------:|--------:|--------:|---------:|--------:|----:|
| 50 | 500 | 21118 | 23.7 | 1161 | 3586 | **4534** | 5814 | 1936 | 6355 | 0 |
| 100 | 1000 | 29174 | 34.3 | 1954 | 5923 | **7359** | 10357 | 2781 | 15678 | 0 |

**结论（可实证部分）**：
- 并发 50：**P95=4.53s（< 5s 容忍，达标）**。
- 并发 100：**P95=7.36s（> 5s 容忍，超标）**；RPS 只从 23.7 → 34.3（并发翻倍吞吐仅 +45%），P50 从 1.16s → 1.95s——**典型连接池饱和特征**。

`/api/series` 列表**不走 Redis 缓存**（无 `get_or_load` 包装，参见 `service.py::list_series`），故列表 P95 与 Redis 是否就绪无关，是纯 MySQL 读路径的真实测量。

---

## 4. P95 治理结论

**判定：并发 ≤ 50 达标（P95 4.5s）；并发 > 50 退化超标（P95 7.4s）。** 需改进，但根因定位为**配置/容量**，不是产品代码 bug——**本任务不改产品代码**（遵循「除非改动小而明确否则不强改，报告为准」）。

**瓶颈识别（读了实现后的证据链）**：
1. **后端单 worker**（`WORKERS=1`）承载所有并发，一条 asyncio 事件循环 + 单一 MySQL 连接池。
2. **MySQL 连接池很小**（`MYSQL_POOL_SIZE=10`）：并发 100 时 100 个请求争 10 个连接，`_pool_acquire` 并发闸信号量把多出的请求排进等待（10s 超时 + 2 次重试 + 200ms 退避）——延迟主要耗在**等待连接槽**，而非 DB 查询本身。这正是「并发翻倍、吞吐仅 +45%、P50 翻倍」的指纹。
3. 列表每请求 2 次顺序查询（`list_series` + `list_category_names_bulk` 批量分类名），单请求内串行；非瓶颈主因，但属可优化点。

**改进建议（登记，供运维/后续任务落地，需 Redis 就绪 + 复跑压测验收）**：
- **连接池扩容**（`MYSQL_POOL_SIZE` 10 → 更高）或引入**独立只读池**（`_mysql_ro_pool` 已声明未用，Phase 2 读写分离留口）承载读型端点。**注意**：直接调大共享 `MYSQL_POOL_SIZE` 会削弱 task04 #2 的防占满挂死保护，故建议只在已识别为读多写少的端点走只读池，避免弱化写路径防护——不作为本 P3 任务盲改默认值的理由。
- **多 worker**（`WORKERS` 1 → 4）：多核承载；但叠加 LLM worker 时须沿用 task39 已有的「预热后端感知 + sidecar 回落」策略，防显存重复占用（见 `test_contract_task39.py` 用例 3）。
- **列表缓存**：`list_series` 首页/热门等热点页走既有 `get_or_load`（task23 已预留缓存点注释）。**当前 Redis 不可达，加了也仍走 DB，无法降本 P95——列为「Redis 就绪后再落」**。
- 可选小优化：列表 N+1 已批量，可进一步缓存分类名映射（非必须）。

---

## 5. 真 Redis 项 —— 登记 gap

**环境实测（socket 1s 超时）**：
- `127.0.0.1:6379` → **CLOSED（TimeoutError）**
- `192.168.85.101:6379` → **CLOSED（TimeoutError）**

**登记结论**：task39 tracker 的「真 Redis / 缓存命中 / 削峰 / 跨实例」项，在 Redis 未就绪前提下**不可实证**——**不伪造命中/削峰数字**。

- 现状可确证：`get_or_load` 在 Redis 断连时经 `redis_run` 熔断**毫秒级直通 DB**（功能可用、性能下降），且 `_record_degraded("redis",...)` 打点；详情/班次详情因此每一读都落 MySQL（命中率 0）。这是**真实的行为观察**（代码路径 + 任务39既有修复），但**不是缓存命中率/削峰百分比**——那些需要 Redis 就绪后单独验收。
- **需 Redis 就绪后单独验收**：缓存命中率（详情/班次详情 `course:series:detail:*` / `course:cohort:detail:*`）、并发下削峰（清单 P0 条目）、跨实例一致性与写后精确 DEL。
- 不制造假数字：本报告任何「命中率/削峰」字段均未填数。

---

## 6. 产物

- 完工报告：`test-reports/task39-perf-completion-report.md`（本文件）
- 压测器：`test-reports/task39_stress.py`（可重跑；env：`EDU_BASE` / `EDU_ACCOUNT` / `EDU_PASSWORD` / concurrency-total 在脚本内调整）
- 既有契约测试真实状态：`edu-agent/tests/test_contract_task39.py` → **22 passed**（未 commit；验收可复跑）

## 7. 批判承接核对 / 待办

- 无既有批判 backlog 承接项与之重叠（本任务为独立压测/登记任务）。
- 后续待 Redis 就绪：单独任务验收「缓存命中/削峰/跨实例」，并复跑本压测（连接池扩容后）对拍 P95。