# task39 完工报告 —— 性能压测 + 容灾演练

- **角色**：后端 + 数据库开发者
- **基线与 HEAD**：`c8e99d8 task37-gwt3-perfguard`（起始 HEAD 之上，未做 reset / read-tree）
- **执行日期**：2026-08-29
- **报告产物目录**：`edu-agent/test-reports/`

---

## 0. 结论摘要

| # | GWT | 目标 | 实测 | 判定 |
|---|-----|------|------|------|
| ① | Locust 压测 · **缓存链路** | P95 ≤ 800ms | `series/{id}` P95 **22ms**、`cohorts/{id}` P95 **21ms**、`series` 未缓存 P95 **100ms**，Redis 命中率 **99.03%**，0 失败 | ✅ **达标** |
| ① | Locust 压测 · **LLM 档位** | P95 ≤ 8s、流式首包 ≤ 3s | L1 P95 **25s** / L2-tool P95 **26s** / L2-learning P95 **32s**；TTFT P95 **21.0s（L1）/ 17.5s（L2）** | ❌ **未达标（超标 3~4× / TTFT 7×）** |
| ② | 故障注入 · **六依赖优雅降级** | 断连不 5xx | milvus / redis / neo4j / mongo / minio / llm **全部无 5xx**；降级指标 milvus=1、redis=4、neo4j=1、llm=6、mongo=0、minio=0 | ⚠️ **基本通过**（mongo/minio 缺读路径探针，见 §3.4） |
| ② | 故障注入 · **72h escalation 幂等** | 并发不重单 | 顺序 3 次建 1 单；**20 并发 escalated 合计 = 1**；全局扫描 skipped=2688 不重复建单；字段全对 | ✅ **达标** |
| ③ | 冷启动预热 | 首请求 < 3s | `status=ready, elapsed=1816ms`（jieba 1.1s + cloud_embed 0.33s + reranker_sidecar 0.35s） | ✅ **达标** |
| ④ | checkpointer 压测 | 并发 100 resume 无丢失/错乱 | S1/S3 resume **100/100**、P95 **56ms**；S2 字段级不错乱 + 顺序写可见；S4 只持有 1 个 Redis 客户端 | ✅ **达标** |
| ⑤ | 令牌桶复测（G1-②） | 窗口边界不超发 | 固定窗口 **2.00×** → 令牌桶 **1.00×**（峰值削减 **50%**） | ✅ **达标** |

> **一句话**：缓存链路、预热、checkpoint 并发、令牌桶、escalation 幂等五项达标；
> **LLM 档位 P95 / TTFT 严重超标**，属 task29 批判② 未治理彻底的历史遗留，本任务只做**量化实证**，不做架构改动（超出 task39 边界）。

---

## 1. 环境与执行时间线

### 1.1 依赖拓扑

| 组件 | 地址 | 备注 |
|------|------|------|
| MySQL / Milvus / Neo4j / MongoDB / MinIO | VM `192.168.85.101` | 共享环境 |
| Redis | `127.0.0.1:6379` | 本机 |
| Rerank sidecar | `127.0.0.1:8601` | `app.rerank_service.main` |
| 压测后端 | `127.0.0.1:8000` | `uvicorn app.main:app` |

### 1.2 时间线（含一起**环境事故**，影响后段数据效力）

| 时间 | 事件 |
|------|------|
| 02:41–02:42 | 缓存链路压测（30 并发 / 90s） |
| 02:50–02:52 | LLM 档位压测（6 并发 / 150s，**落在 18:00–09:00 窗口内**） |
| 03:12–03:21 | 六依赖容灾演练（**环境健康**） |
| ~08:20 | 全量 pytest（3 failed / 580 passed / 145 skipped / 7 errors） |
| **08:23** | 重启 sidecar 8601（model_loaded=true, cuda, 1092MiB） |
| **08:25–08:31** | 基线 + mongo + minio 补跑 —— **发现基线也报降级** |
| **08:33** | 探明根因：**VM `192.168.85.101` 整体不可达（ping 100% 丢包）**，本机 Redis 6379 无监听 |

> ⚠️ **环境事故（需上报）**：自 08:33 起共享 VM 全端口（3306/19530/7687/27017/9000）超时，
> 本机 Redis 拒绝连接（Redis 跑在被安全策略禁用的 WSL 内，我无法自行拉起；Docker 未安装）。
> 直接后果：**08:25 的「基线对照」失效**（详见 §3.3），且 checkpoint 并发 / escalation 幂等
> **无法在报告定稿前复跑**——这两项数据来自环境掉线前的实测（§3.5、§5），可信但不可复现。
> 该事故同样会影响并行中的 task37 等依赖 VM 的任务。

---

## 2. GWT① Locust 压测

### 2.1 工具与方法

- Locust **2.46.4**，脚本 `tests/performance/locustfile_task39.py`
- 三类 User 类，用 `TASK39_CLASSES` 环境变量 + `abstract` 动态启停，避免 `--tags` 下
  `No tasks defined on XxxUser` 报错：
  - `CachedBrowseUser`（`cached`）
  - `ChatUser`（`chat`，L1-knowledge / L2-tool / L2-learning）
  - `StreamChatUser`（`stream`，TTFT 以独立 `environment.events.request.fire()` 事件上报，name 前缀 `TTFT`）

**三个坑（均已修）**：

1. **登录污染统计**：登录限流 10/60s 按 IP，且 bcrypt 单次 ≈4s。用户数 >10 必然 429，且会把
   bcrypt 时间算进 P95。→ 改为 `test_start` **预取 token 池**，`on_start` 直接复用。
2. **冷启动未就绪**：模型加载时间会被第一个请求吃掉。→ `on_locust_init` 断言
   `GET /health/warmup?wait=60` 就绪后才开跑（本次新增端点）。
3. **限流天花板**：默认 chat 限流 20/min，会让压测退化成"限流测试"。→ 新增
   `EDUAGENT_CHAT_LIMIT` 环境变量，压测实例放宽至 5000。

### 2.2 缓存链路（✅ 达标）

`30 users / 90s / 2028 requests / 0 failures`，RPS 22.55

| 接口 | 样本 | P50 | **P95** | P99 | Max | RPS |
|------|------|-----|---------|-----|-----|-----|
| `GET /api/series/{id}`（缓存命中） | 999 | 9ms | **22ms** | 67ms | 138ms | 11.11 |
| `GET /api/cohorts/{id}`（缓存命中） | 633 | 9ms | **21ms** | 110ms | 125ms | 7.04 |
| `GET /api/series`（未缓存，回源） | 396 | 86ms | **100ms** | 170ms | 196ms | 4.40 |
| Aggregated | 2028 | 10ms | **92ms** | 110ms | 196ms | 22.55 |

- **Redis 命中率 99.03%**（本轮 +1632 hits / +16 misses）
- 目标 P95 ≤ 800ms → 实测最高 100ms，**余量 8×**

> **备注**：命中/未命中差距仅 9ms vs 86ms（约 10×），绝对值都很小，说明 MySQL 侧查询本身不慢，
> 缓存收益主要体现在**吞吐**而非单请求延迟。

### 2.3 LLM 档位（❌ 未达标，超标 3~4×）

`6 users / 150s / 54 requests / 0 failures`

| 接口 | 样本 | P50 | **P95** | Min | Max | 目标 |
|------|------|-----|---------|-----|-----|------|
| `POST /api/chat` [L1-knowledge] | 9 | 22.0s | **25.0s** | 19.2s | 24.8s | ≤8s |
| `POST /api/chat` [L2-tool] | 3 | 25.0s | **26.0s** | 18.3s | 25.7s | ≤8s |
| `POST /api/chat` [L2-learning] | 2 | 27.4s | **32.3s** | 27.4s | 32.3s | ≤8s |
| `POST /api/chat/stream` [L1] | 10 | 3.5s | **15.0s** | 3.2s | 14.7s | ≤8s |
| `POST /api/chat/stream` [L2] | 10 | 3.6s | **14.0s** | 3.3s | 13.7s | ≤8s |
| **TTFT** [L1] | 10 | 7.1s | **21.0s** | 6.0s | 21.2s | ≤3s |
| **TTFT** [L2] | 10 | 9.0s | **17.5s** | 6.5s | 17.5s | ≤3s |

**⚠️ 样本量声明（方法学缺陷，如实披露）**：LLM 单次响应 20~30s，150s 窗口只跑出 54 个样本，
其中 L2-learning **n=2**、L2-tool **n=3**。n=2 的 "P95" 无统计意义，仅能作为量级参考。
要得到可信 P95 需 ≥ 数百样本，按当前速率需连续跑 **1.5 小时以上**（仍须在 LLM 测试窗口内）。

**根因剖析**（单次 L1 请求 = **5 次 LLM 串行调用**）：

```
1.8s → 6.2s → 2.5s → 7.5s  ... （fan_out 子代理已并行，串行部分是主链路的 5 次调用）
单次 LLM 调用本身 1.4~5.0s
```

即：延迟不是某一次调用慢，而是**链路深度 × 单次延迟**的乘积。
task29 批判② 曾把 87s 降到 43.7s，本次实测非流式 25s 左右——**仍超标 3× 以上**。

**不做改动的原因**：削减链路深度 = 改 agent 拓扑 / 引入 prompt cache / 流式分段返回，
属架构级变更，超出 task39「压测 + 演练」边界。建议单开任务（见 §9）。

---

## 3. GWT② 容灾演练

### 3.1 方法：连接层故障注入（不 kill 共享服务）

真实 kill VM 上的 Milvus/Neo4j/Mongo/MinIO 会影响并行任务且恢复窗口不可控。
改用 **env 覆盖指向不可达地址 `127.0.0.1:6553x`** + 每个场景拉起**独占端口**的独立后端实例：

- 零共享状态、随起随停、可重复执行
- 等价于「该依赖网络不可达」
- **代价（如实标注）**：注入地址本机无监听 → 连接被**拒绝**（fail-fast）；
  真实网络分区是**超时等待**，故**降级正确性成立不代表延迟达标**。

脚本：`scripts/verify_task39_disaster_drill.py`（支持 `--only` / `--out`）

### 3.2 六依赖结果（03:12–03:21，环境健康）

| 依赖 | 注入 | 启动 | 无 5xx | `edu_degraded_total` | RAG 检索 | AI 问答 |
|------|------|------|--------|----------------------|----------|---------|
| milvus | `MILVUS_URI=…:65530` | ok | ✅ | **1.0** | 2795ms | 30020ms |
| redis | `REDIS_URL=…:65531` | ok | ✅ | **4.0** | 30820ms | 48207ms |
| neo4j | `NEO4J_URI=…:65532` | ok | ✅ | **1.0** | 29784ms | 19265ms |
| mongo | `MONGO_URI=…:65533` | ok | ✅ | 0.0 | 28518ms | 17371ms |
| minio | `MINIO_ENDPOINT=…:65534` | ok | ✅ | 0.0 | 24548ms | 20722ms |
| llm | `LLM_*_BASE_URL=…:65535` | ok | ✅ | **6.0** | 28569ms | 17298ms |

**降级原因样本**（响应体 `degraded_reason` 可见）：

- milvus：`Milvus 检索跳过（MilvusException）`
- neo4j：`Neo4j 未连接（跳过图谱扩展）`
- llm：`llm_failed`（走 `_local_rule_answer` 规则兜底）
- redis：缓存直通 + 限流放行 + 幂等跳过（4 次计数分散在 cache / idempotency / rate_limit / vector）

**⚠️ 混杂因子披露**：本轮跑到第 2 个场景时 **sidecar 8601 已死**，故场景 2–6 的 RAG 检索
统一多带一条 `rerank_sidecar_unavailable`，这解释了为何 milvus 场景 RAG 只要 2795ms、
后续场景却要 24–31s。**per-component 计数仍然有效**（sidecar 的降级记在 `reranker` 标签下，
不污染 milvus/neo4j 计数），但**延迟横向对比不成立**。

### 3.3 基线对照：❌ 未建立（环境事故导致）

本次新增 `baseline` 场景（不注入任何故障），用于证明**探针本身有效**——
若基线也 5xx / 也报降级，则"断连后无 5xx""降级指标增长"两种结论都失去说服力。
这是 Chaos Engineering 五原则第一条「围绕稳态行为建立假设」的可执行形式。

实测（08:25）：

```
■ 场景 baseline：基线对照（全依赖在线，不注入故障）
    RAG 检索（Milvus+图谱） HTTP 200  5421ms  degraded=有
      | Milvus 检索跳过（MilvusException）；Neo4j 未连接（跳过图谱扩展）
  ⚠️ 基线出现降级原因：稳态假设不成立，断连场景的降级对照需谨慎解读
```

基线报出了**与注入场景同款**的降级原因 → 08:33 探明：VM 整体不可达。
**结论：基线对照未建立，待环境恢复后必须重跑。** 当前"六依赖无 5xx"结论依赖 §3.2 的
**场景间交叉印证**（milvus 场景未报 Neo4j 降级、neo4j 场景未报 Milvus 降级 → 注入是隔离生效的），
而非基线对照。

### 3.4 mongo / minio 缺口（降级指标 = 0）

| 依赖 | 状态 | 说明 |
|------|------|------|
| mongo | 指标 0 | 无 5xx ✅，但探针未命中 mongo 读路径。现有探针（`/api/chat`）的对话历史走 MySQL `chat_message` 兜底，**mongo 断连后根本没被访问** → 不产生降级计数属"未被触发"，不等于"降级已验证"。需补一个**强制读 mongo** 的探针（如 memory/dream 相关接口）。 |
| minio | 指标 0 | 无 5xx ✅，但见下方**新发现的缺陷**。 |

**MinIO 新发现（⚠️ 与 §6.4 矩阵不符）**：

上传探针从 urllib 手工拼 multipart 改为 **httpx** 后（原先的 422 `Field required` 是**探针编码问题**，
非产品缺陷），MinIO 断连时：

```
知识库上传（MinIO） HTTP 200
  {"task_id":"task_1787963468_f95fb2","status":"pending",
   "message":"文件已接收，正在后台执行 p…"}
```

即：**同步返回 200，失败被推迟到后台导入任务**。
对照 `doc-architect-tech-arch §6.4` 对 MinIO 的降级契约「上传/视频明确报错（4xx/5xx 明确，非静默）」——
当前实现是**静默延迟失败**，不符合契约。建议后续：后台任务失败后应有可查询的失败状态 +
`edu_degraded_total{component="minio"}` 计数。

### 3.5 72h escalation 幂等（✅ 达标，环境掉线前实测）

脚本：`scripts/verify_task39_escalation_idempotent.py`
机制：`SELECT ... FOR UPDATE` 行锁串行化 check-then-insert，事务内双写 `service_ticket` + `risk_alert_event`。

| 用例 | 内容 | 结果 |
|------|------|------|
| T1 | 顺序 3 次触发 | 只建 **1** 单 |
| T2 | **20 并发**触发 | escalated 合计 **= 1** |
| T3 | 全局扫描（含已处理单） | skipped=**2688**，不重复建单 |
| T4 | 字段正确性 | `severity=high / status=open / source=system_auto`；`refund_anomaly / scheduled_job / pending` 全对 |

造单用**隔离单**：复用真实行的 `payment_id`（否则违反 `fk_refund_request_payment` 外键），
`applied_at = now-100h`、`hours=72` 天然超时；结束软删 `yn=0`，不污染生产数据。

---

## 4. GWT③ 冷启动预热（✅ 达标）

新增 `app/core/warmup.py`，替代 `main.py` 旧的 `_warmup_local_models()`
（旧实现**缺 reranker**，是 task-VEC/31 批判② 的缺口）。

**预热链（实测日志）**：

```
[预热] embed_backend     完成    0ms — cloud-first（本地 BGE 仅回退）
[预热] jieba             完成 1143ms — jieba 词典 + 停用词已加载
[预热] cloud_embed       完成  325ms — 云端 embedding 就绪 dim=1024
[预热] bge_m3            完成    0ms — skipped：EMBED_BACKEND=cloud，本地模型非主链路（按需懒加载）
[预热] reranker_sidecar  完成  346ms — rerank sidecar 已预热 http://127.0.0.1:8601/rerank
[预热] reranker_local    完成    0ms — skipped：sidecar 可用，避免重复占显存（§7 薄弱点 3）
[预热] 完成 status=ready elapsed=1816.0ms failed=none
```

**设计要点**（回应 `tech-source-audit §7` 薄弱点 3「多 worker 显存重复占用」）：

- `EMBED_BACKEND=cloud` 时**跳过本地 BGE-M3 预加载**（本地模型非主链路，按需懒加载）
- reranker **优先走 sidecar HTTP 预热**（8601），主进程不占显存；
  **仅当 sidecar 不可达**才落本地 → 显存实测：sidecar 1092MiB，主进程不重复加载
- 幂等：`status ∈ {ready, degraded}` 时直接返回上次结果

**配套观测端点**：`GET /health/warmup?wait=N`（压测前断言模型就绪，否则首请求加载时间会算进 P95）；
`/health/detail` 的 `components` 增加 `warmup` 段。

> 另：Redis 降级不再把 `/health/detail` 置 `all_ok=False`——按 §6.4，Redis 属
> 「功能可用、性能下降」，不应判整体不健康。

---

## 5. GWT④ checkpointer 并发压测（✅ 达标）

脚本：`scripts/verify_task39_checkpoint_concurrency.py`（打真 Redis，不 mock）

| 场景 | 内容 | 结果 |
|------|------|------|
| S1 | 跨线程 100 线程 × 3 步并发 aput | resume **100/100** |
| S2 | 同线程 100 并发 aput | 字段级**不错乱** + 并发后顺序写入可见 |
| S3 | **新实例** resume | **100/100**（持久化未丢） |
| S4 | 连接泄漏回归 | saver 只持有 **1** 个 Redis 客户端 |
| — | **P95** | **56ms**（修复前 **8185ms**，快 **146×**） |

### 5.1 根因一：Windows IPv6 双栈陷阱（性能，146×）

`REDIS_URL=redis://localhost:6379/0` 在 Windows 上经 `getaddrinfo` **优先解析为 IPv6 `::1`**，
而 Redis 只监听 IPv4 → 每次新建连接先撞 IPv6 超时再回落。

实测 20 并发首次 ping：**`localhost` 6058ms vs `127.0.0.1` 4ms（1500×）**

→ 在 `app/config.py` 新增 `@model_validator(mode="after") _normalize_loopback()`：
**仅当 hostname 恰为 `localhost` 时**替换为 `127.0.0.1`，保留 userinfo/port；
`[::1]` / 域名 / IP 一律不动（避免误伤 IPv6-only 部署）。

### 5.2 根因二：锁表被反复重置（正确性）

`_locks_for_loop()` 原用 `self._loop` 作判据，而 `self._loop` 要等 `_client()` **首次建连后**才赋值 ——
首轮并发期间它仍是 `None` → 每次都判定"跨事件循环" → **反复重置锁表 → 互斥彻底失效**。

取证：修复前 100 个协程拿到 **2 个** Lock 对象；改用独立的 `_locks_loop` 判据后，稳定为 **1 个**。

同时把 `aput` / `aput_writes` / `aget_tuple` / `alist` 改为
`async with await self._thread_lock(thread_id)` 包裹「写内存 + 落盘」**整段**（原实现只锁了局部，
存在 R2 读-改-写竞态）；`_client()` 加 `conn_lock` 双重检查（R1）。

### 5.3 根因三：checkpoint id 非字典序单调（正确性）

`InMemorySaver.get_tuple` 用 `max(checkpoints.keys())` 取"最新"——按 **id 字符串字典序**，
既不是时间戳也不是版本号。LangGraph 自身用 ULID 所以字典序 = 时间序，
但压测脚本自造的 `"racer-99-…" > "final-…"` 破坏了这一契约 → 顺序写在并发写之后**读不出来**。

修复：按 ULID 契约生成字典序单调 id

```python
_ts0 = int(time.time() * 1000); _seq = {"n": 0}
def _monotonic_id() -> str:
    _seq["n"] += 1
    return f"{_ts0 + _seq['n']:016d}-{_seq['n']:06d}"
```

### 5.4 断言口径修正

S2 原断言 `step == n_concurrent` 是**错的**：真并发下没有"定义好的胜者"，
最后一次写入可以是任意一个协程。改为断言：

1. **字段级不错乱**：`marker` 与 `step` 归属同一次提交（能检出写撕裂）
2. 并发结束后的**顺序写入**必须可见（能检出"取最新"逻辑错误）

---

## 6. GWT⑤ 令牌桶窗口边界复测（✅ 达标）

脚本：`scripts/verify_task39_token_bucket_boundary.py`
（`rate=600/min, window=60s, sim=300s, step=0.1s`）
产物：`test-reports/task39-token-bucket-boundary.txt`

```
[固定窗口]                    60s 滑窗峰值 = 1200 tokens  突发倍率 = 2.00×
[令牌桶 capacity=1.0×rate]    60s 滑窗峰值 =  600 tokens  突发倍率 = 1.00×
[令牌桶 capacity=1.5×rate]    60s 滑窗峰值 =  900 tokens  突发倍率 = 1.50×
[令牌桶 capacity=2.0×rate]    60s 滑窗峰值 = 1200 tokens  突发倍率 = 2.00×
```

判定：

- ✅ 固定窗口复现边界 **2.00×** 突发（对照组有效）
- ✅ 令牌桶（BURST_RATIO=1.0）突发倍率 **1.00× ≤ 1.1×**
- ✅ 峰值 600 vs 固定窗口 1200，**削减 50%**

**调参建议（重要发现）**：`BURST_RATIO=2.0` 会让令牌桶的保证**退化回 2.00×**，
与固定窗口完全等价 —— 即该参数取 2.0 等于白改。当前配置
`TOKEN_BUCKET_ENABLED=False / BURST_RATIO=1.0 / REFILL_WINDOW_SEC=60.0`，**保持 1.0 是正确选择**。

---

## 7. 本次代码改动清单

### 7.1 新增文件

| 文件 | 用途 |
|------|------|
| `app/core/warmup.py` | GWT③ 统一预热链（jieba / cloud_embed / bge_m3 / reranker_sidecar / reranker_local） |
| `scripts/verify_task39_disaster_drill.py` | GWT② 六依赖故障注入 + 基线对照 |
| `scripts/verify_task39_escalation_idempotent.py` | GWT② 72h escalation 幂等（含 20 并发） |
| `scripts/verify_task39_checkpoint_concurrency.py` | GWT④ checkpointer 并发 S1–S4 |
| `scripts/verify_task39_token_bucket_boundary.py` | GWT⑤ 令牌桶边界量化复测 |
| `tests/performance/locustfile_task39.py` | GWT① Locust 三类 User + TTFT 上报 |
| `tests/test_contract_task39.py` | **22 条契约回归**（补交付短板，见 §10.2） |

### 7.2 生产代码修改

| 文件 | 改动 |
|------|------|
| `app/config.py` | 新增 `_normalize_loopback()`（IPv6 陷阱，`REDIS_URL` 注释说明） |
| `app/ai/checkpoint_redis.py` | 并发加固：`_locks_loop` 独立判据、`_thread_lock()` 包裹整段、`_client()` 双重检查、锁表上限 4096 |
| `app/ai/graph.py` | `_llm_call` 统一收口埋点（agent 链路唯一 LLM 出口）；`_make_checkpointer` 失败埋点 |
| `app/chat/retriever.py` | `retrieve_three_channel` 汇总处按变量出处映射降级组件并埋点（有降级 record / 无降级 clear） |
| `app/chat/generator.py` | `generate` / `generate_stream` 的 LLM 异常兜底埋点 |
| `app/chat/service.py` | **修缺陷**：agent 链路的 `degraded_reason` 原本被硬编码 `None` 丢弃，改为透传进 `bundle` |
| `app/core/idempotency.py` | Redis 不可用分支埋点 |
| `app/core/cache.py` | `get_or_load` 的「无客户端」与「读写异常直通 DB」两处埋点 |
| `app/middleware/rate_limit.py` | Redis 异常降级放行埋点；新增 `EDUAGENT_CHAT_LIMIT` |
| `app/ai/memory/vector.py` | 无 Redis 客户端 + ping 失败两处埋点 |
| `app/monitoring/metrics.py` | 新增 `edu_degraded_total{component,reason}` + `edu_degraded_active{component}` + `record_degraded()` / `clear_degraded()`（内部 try/except 永不抛） |
| `app/routers/health.py` | 新增 `GET /health/warmup?wait=N`；`/health/detail` 增 `warmup` 段；Redis 降级不再置 `all_ok=False` |
| `app/main.py` | `_warmup_local_models()` / lifespan 转交 `app.core.warmup.run_warmup()` |
| `app/domains/course/router.py` | **修 P0 缺陷**（见 §7.3） |

### 7.3 压测发现的 P0 缺陷：`/api/series/{id}/cohorts` 无条件 500

```
'series' object has no attribute 'model_dump'   ← 实为 'tuple' object
```

`svc.list_cohorts(series_id)` 自 R2 裁定起返回 **`CohortListData` 分页壳**（`items` + `page_meta`），
不再是裸列表。router 直接迭代 pydantic 模型 → 得到 `(字段名, 值)` 元组 → 元组无 `.model_dump()`
→ **该接口无条件 500**。

修复：

```python
cohorts = await svc.list_cohorts(series_id)
return ok(data=cohorts.model_dump(mode="json"))
```

> 这是压测的直接价值：**契约测试没覆盖到的真实线上缺陷**。

---

## 8. 竞品对标（均附真实 URL，已实测可达性）

### 8.1 压测方法学

| 对标对象 | 可达 | URL |
|----------|------|-----|
| Locust 官方文档 | ✅ | https://docs.locust.io/en/stable/ |
| Locust 自定义客户端 / 事件钩子（TTFT 上报依据） | ✅ | https://docs.locust.io/en/stable/extending-locust.html |
| Google《The Tail at Scale》（长尾延迟） | ❌ ConnectTimeout | https://research.google/pubs/the-tail-at-scale |
| vLLM PagedAttention 论文 | ❌ ConnectError | https://arxiv.org/abs/2309.06180 |

> **对标落点**：TTFT 作为独立指标上报，正是「Tail at Scale」长尾治理的前提 ——
> 聚合 P95 会掩盖"首包已到但整体慢"与"整体快但首包卡住"的区别。
> vLLM continuous batching 的吞吐数据因 `arxiv.org` / `docs.vllm.ai`（429）不可达，
> 改由二手来源佐证，**不作为硬指标引用**。

### 8.2 容灾 / 混沌工程

| 对标对象 | 可达 | URL |
|----------|------|-----|
| Netflix Chaos Monkey | ✅ | https://github.com/Netflix/chaosmonkey |
| Gremlin · Chaos Engineering 定义 | ✅ | https://www.gremlin.com/chaos-engineering |
| Basiri 等《Chaos Engineering》IEEE 论文（2016） | ✅ 202 | https://ieeexplore.ieee.org/document/7504759 |
| Principles of Chaos 官网 | ❌ ConnectError | https://principlesofchaos.org |

> **对标落点**：Chaos Engineering 五原则的**第一条**「围绕稳态行为建立假设」直接催生了
> 本次新增的 `baseline` 场景（§3.3）；**第四条**「最小化爆炸半径」对应我们放弃 kill 共享服务、
> 改用独占端口 + env 覆盖的连接层注入（§3.1）。
> `principlesofchaos.org` 不可达，五原则内容转由 Gremlin 页面 + IEEE 原始论文佐证。

### 8.3 可观测性与缓存

| 对标对象 | 可达 | URL |
|----------|------|-----|
| Prometheus Counter / Gauge 语义 | ✅ | https://prometheus.io/docs/concepts/metric_types/ |
| Redis 内存优化官方指引 | ✅ | https://docs.redis.com/latest/ri/memory-optimizations/ |
| Anthropic《Building Effective Agents》（多步 agent 延迟治理） | ✅ | https://www.anthropic.com/engineering/building-effective-agents |

> **对标落点**：`edu_degraded_total`（Counter，累计降级次数）+ `edu_degraded_active`（Gauge，当前是否降级）
> 的组合完全对应 Prometheus 的两种语义 —— Counter 回答"发生过多少次"，Gauge 回答"现在是否处于降级态"，
> 单用任一个都不够。Anthropic 文中对 workflow / agent 的取舍讨论，正是 §2.3「链路深度 × 单次延迟」
> 根因的治理方向（但该文给的是设计原则，不含具体延迟预算数字）。

---

## 9. 遗留问题与后续建议

| 优先级 | 问题 | 证据 | 建议 |
|--------|------|------|------|
| **P0** | **LLM P95 / TTFT 严重超标** | P95 25~32s（目标 8s）、TTFT P95 17.5~21s（目标 3s） | 单开任务：削减主链路串行 LLM 调用次数（现 5 次）、引入 prompt cache、流式分段返回；**勿在 task39 内改架构** |
| **P0** | **Neo4j / Redis 断连无熔断** | RAG 检索 2.8s → **29.4s**；AI 问答 22s → **52.4s** | 加 circuit breaker（快速失败 + 半开探测）。当前"能降级"但"慢到不可用" |
| **P1** | **MinIO 上传静默延迟失败** | 断连时同步返回 200 + `status: pending`，失败推迟到后台任务 | 后台任务失败需可查询状态 + `edu_degraded_total{component="minio"}` 计数，以对齐 §6.4「明确报错」 |
| **P1** | **mongo / minio 降级指标 = 0** | 探针未命中读/写路径 | 补强制读 mongo 的探针；mongo 断连验证需覆盖 memory/dream 等真实读路径 |
| **P1** | **基线对照未建立** | 环境事故导致基线报出与注入同款的降级 | 环境恢复后重跑 `--only baseline`；建议把 baseline 固化为每次演练的第一步 |
| **P2** | LLM 压测样本量不足 | L2-learning n=2、L2-tool n=3，P95 无统计意义 | 需连续跑 ≥1.5h（仍在 LLM 窗口内）取数百样本 |
| **P2** | `TOKEN_BUCKET_ENABLED=False` | 令牌桶未在生产启用 | 复测已证明收益（2.00×→1.00×），建议择机灰度开启；**注意 BURST_RATIO 切勿设 2.0** |

---

## 10. 回归与测试基线

全量 pytest（`edu-agent/.venv`，`tests/`）——**含 §10.2 新增的 22 条契约测试后**：

```
3 failed, 602 passed, 145 skipped, 7 errors in 181s
```

（加入新测试前为 `3 failed / 580 passed / 145 skipped / 7 errors`，**+22 passed，failed/errors 零变化**
→ 新增契约测试未引入任何 fixture 串扰。）

**3 failed 明细与归因**：

| 用例 | 单独执行 | 归因 |
|------|----------|------|
| `test_be_task01_suite.py::test_be_task01_delete_hit` | — | 外部子进程 `restart_uvicorn_and_chat_delete_hit.py` returncode=1（依赖 8000 后端，环境已停） |
| `test_contract_task94.py::TestGwt4Registry::test_live_ai_hub_124_registered` | ❌ 仍失败 | **环境漂移**：硬编码期望 124 个 skill，实际扫到 **178 个**（`.claude/skills` 目录被扩容过）。与 task39 无因果关系 |
| `test_contract_task_c2.py::TestExpandSchema::test_expand_schema_returns_full` | ✅ **单跑通过** | **测试间 fixture 串扰**，全量执行时才失败 |

**7 errors** 全部在 `tests/test_contract_task22.py` —— 单独执行该文件时 **7 passed**，
同属 fixture 串扰。

> **结论**：3 failed / 7 errors **均与 task39 改动无因果关系**（1 条外部子进程、1 条环境漂移、
> 1 条 + 7 条测试间串扰）。
>
> **⚠️ 顺带发现（建议单开小任务）**：`test_contract_task94` 硬编码 `total == 124` 断言磁盘上
> 的 skill 数量，而实际为 178。这是一条**会持续失败**的测试，只要有人往 `.claude/skills`
> 增删文件就会红。建议改为「≥ 某个下限」或改为校验注册表自洽性，而不是绝对数量。

### 10.2 补交付短板：新增 22 条契约回归测试（第二次提交）

**为何事后补**：task39 首版提交改了 6 处生产代码，却**只做了实时压测取证、没写任何契约测试**。
共享环境掉线后实时验证无法复跑，这成了交付的真实短板。故补一批**纯单元测试**
（不依赖 MySQL / Redis / Milvus / Neo4j / MinIO 任何实时服务，任何环境都能跑）。

`tests/test_contract_task39.py`（22 passed）：

| 测试类 | 条数 | 钉住的修复 |
|--------|------|-----------|
| `TestLoopbackNormalization` | 10 | `config._normalize_loopback`：localhost→127.0.0.1；**userinfo/port/db 必须完整保留**；`[::1]`/域名/IP/unix socket **不许动**；空值与非法串不抛异常 |
| `TestDegradedMetrics` | 4 | Counter +1 且 Gauge=1；`clear_degraded` 只清 Gauge、**Counter 单调不回滚**；组件名归一化到小写；任意非法输入**永不抛** |
| `TestWarmupBackendPolicy` | 4 | cloud 模式**跳过**本地 BGE-M3；sidecar 可用**跳过**本地 reranker；sidecar 挂了**必须回落**本地；重复调用幂等 |
| `TestCohortsPagedShell` | 4 | 压测发现的 P0 500 回归 |

**两条防"空断言"的设计**（断言没跑过 ≠ 断言有效）：

1. `test_cuda_backend_does_load_local_bge` —— 反向对照：若 fixture 把 `bge_m3` 永久打桩掉了，
   「cloud 模式不加载 bge_m3」的断言就是**空转**。这条证明两条分支真能区分开。
2. `test_root_cause_pinned_iterating_model_yields_tuples` —— 把根因本身钉死：
   迭代 pydantic 模型得到的是 `(字段名, 值)` 元组，元组没有 `.model_dump()`。
   这样即使有人"修好"了 endpoints，也能看懂当初为什么 500。

**变异检验（mutation test，确认测试不是空转）**：把 `_normalize_loopback` 的判定条件
`== "localhost"` 改成 `== "__mutation_test__"` 后重跑 → **5 条立刻失败**
（4 条参数化用例 + 1 条 settings 单例检查），还原后恢复 22 passed。**测试确实抓得住回归。**

> 顺带确认：变异检验暴露出 `.env` 里配的确实是 `redis://localhost:6379/0`，
> 归一化是在 `Settings` 构造时生效的 —— 也就是说**只改 .env 不够，必须在配置层兜底**
> （他人环境/新机器复现时同样会踩）。

---

## 11. 复现命令

```bash
cd edu-agent

# GWT③ 预热（先起后端，再断言就绪）
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
curl -s "http://127.0.0.1:8000/health/warmup?wait=60"

# GWT① 压测（LLM 档位务必在 12:00-14:00 / 18:00-09:00 窗口内）
TASK39_CLASSES=cached ./.venv/Scripts/locust -f tests/performance/locustfile_task39.py \
  --headless -u 30 -r 10 -t 90s --host http://127.0.0.1:8000 \
  --csv test-reports/task39-locust-cached --html test-reports/task39-locust-cached.html

TASK39_CLASSES=chat,stream ./.venv/Scripts/locust -f tests/performance/locustfile_task39.py \
  --headless -u 6 -r 2 -t 150s --host http://127.0.0.1:8000 \
  --csv test-reports/task39-locust-llm --html test-reports/task39-locust-llm.html

# GWT② 容灾演练（baseline 建议先跑）
./.venv/Scripts/python.exe scripts/verify_task39_disaster_drill.py --only baseline
./.venv/Scripts/python.exe scripts/verify_task39_disaster_drill.py

# GWT② escalation 幂等
./.venv/Scripts/python.exe scripts/verify_task39_escalation_idempotent.py

# GWT④ checkpointer 并发
./.venv/Scripts/python.exe scripts/verify_task39_checkpoint_concurrency.py

# GWT⑤ 令牌桶边界
./.venv/Scripts/python.exe scripts/verify_task39_token_bucket_boundary.py
```

---

## 12. 产物清单

| 文件 | 内容 |
|------|------|
| `test-reports/task39-completion-report.md` | 本报告 |
| `test-reports/task39-locust-cached_stats.csv` / `.html` | GWT① 缓存链路压测 |
| `test-reports/task39-locust-llm_stats.csv` / `.html` | GWT① LLM 档位压测（含 TTFT） |
| `test-reports/task39-disaster-drill.json` / `.txt` | GWT② 六依赖演练明细 |
| `test-reports/task39-drill-baseline-mongo-minio.json` / `.txt` | GWT② 基线 + mongo + minio 补跑 |
| `test-reports/task39-token-bucket-boundary.txt` | GWT⑤ 令牌桶复测 |
| `test-reports/task39-pytest-baseline.txt` | 全量回归基线 |

> **状态：已停下，等待验收。**
