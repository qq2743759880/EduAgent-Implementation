# task25 完工报告：AI 助手三层记忆 + 遗忘机制（R7 显式记忆触发 + MEMORY.md 索引模式）

> 后端+数据库｜阶段 P4.5｜类型 agent｜执行 Trae 手动调度（dev-standard.mjs 8 阶段）
> 前置：task92（子代理独立上下文）、task24（LangGraph 图重构）｜后置：task26~28
> 交付物：`app/ai/memory/*`（9 模块）+ `user_memory` DDL + graph/chat 接线 + pytest（见 §6）

---

## 1. 背景与核心决策

task24 已验收（LangGraph 图重构）→ 本任务落地 **AI 助手三层记忆**（对齐 Anthropic Effective Context Engineering + Ebbinghaus 遗忘曲线）：

- **Working** = LangGraph state（当前推理上下文）
- **Short-term** = Redis session history + chat_message（会话历史）
- **Long-term** = MySQL `user_memory`（事实源）+ 向量（vector recall 用户分区）

**R7 改造项**：从"会话结束统一提炼"升级为 **显式记忆触发**——用户修正/明确偏好/「记住 X」等高价值信号**即时**规则抽离，会话结束补充，全部经异步队列落库。

**关键环境发现（与需求提示一致）**：Milvus collection 依赖外部存储机 VM `192.168.85.101:19530`，本环境 **不可达**（`TcpTestSucceeded=False`，vector 初始化抛 `MilvusException`）。已按任务授权走 **降级路径**：
- `MemoryVectorStore` 统一 `backend='milvus' | 'memory'`，Milvus 初始化失败自动降级 **in-process 内存向量**（`DeterministicEmbedder`，char 2-gram 哈希确定性向量，dim 512），保证 vector recall 语义与链路恒可用；
- 测试与验证的向量召回均在内存降级下通过；报告 §5 注明该降级。

**数据表**：新增 `user_memory` 表（`项目文档/patch_memory_tables.sql`），字段/索引经 `SHOW COLUMNS`/`SHOW INDEX` 与契约逐列核验（见 §5）。

---

## 2. 验收标准逐条核验（GWT 精简版，全文见任务文档）

### ① 多轮对话含明确偏好（如"我想考雅思"）→ 会话结束 user_memory 落库（importance≥4）+ 异步队列不阻塞应答
**判定：✅ PASS**

- **显式触发（R7）**：`detect_memories` 规则抽离「记住 X / 我想考X / 纠正 / 偏好」候选，importance≥4；`service.enqueue_turn` 再以阈值（默认 4）过滤后入队。
- **真库验证**（`scripts/_verify_task25_memory.py`）：
```
[verify] GWT① 入队 ok=True latency_ms=0.98      ← 毫秒级快返，不阻塞应答
[verify] GWT① 消费写入 processed=True count=1   ← 消费才落库，importance=5
```
- 契约测试 `test_detect_goal_preference`：goal 候选 importance=5≥4 且含"雅思"；`test_enqueue_fast_return_then_persist`：入队 <50ms、消费前 count=0、消费后 count=1。

### ② 下次相关话题 → 向量召回 top-3 进 plan prompt，回答体现记忆
**判定：✅ PASS**

- **graph 接入（GWT②）**：`app/ai/graph.py` 新增 `recall_memory` / `recall_profile` 工具服务，调 `service.recall_topk(user_id, q, top_k=3)`，结果供 memory/learning 子代理蒸馏进 lead plan prompt。
- **真库验证**：写入"用户想考雅思，目标 6.5"后以 `query="雅思考试"` 召回，**top-1 命中雅思记忆**（`vector_score=0.3637`），`len<=3`。
- 契约测试 `test_recall_topk_hits_relevant`：召回 top1 命中"雅思"，`len<=3`，命中记忆 `access_count` 提升（近因加分防遗忘）。

### ③ 记忆超 500 条 → 遗忘任务淘汰综合分最低
**判定：✅ PASS**

- **公式**：`score = importance×exp(-0.01·Δt_days) + recency_bonus`（`recency_bonus = W/(1+slope·days)`），实现与任务文档逐字一致（`score.py`）。
- **遗忘语义**：`pick_forget_candidates` 先软删 `score < 0.1` 的时间衰减记忆；仍超容量（默认 500）再从 `(score,id)` 升序淘汰综合分最低补容量。
- **真库验证**（capacity=3 语义等价 500）：写满低重要超容 → `soft_deleted=3, remaining=3`，**高重要雅思记忆保留**（`ielts_kept=True`，高重要久未访问按时间衰减而非误删）。
- 契约测试：`test_score_formula`（新写入=5×exp(0)+2=7 精确验证）、`test_high_importance_decays_slower_not_misdeleted`（高重要老龄得分仍高于低重要新记忆；跌阈软删 + 超容量最低分淘汰时高重要不被淘汰）、`test_over_capacity_keeps_high_importance`。

### ④ 记忆写入失败 → 队列重试不影响应答链路（异步隔离）
**判定：✅ PASS**

- **异步隔离**：`MemoryWriteQueue.enqueue_candidate` 只 LPUSH 入队即返回（Redis 不可用降级 in-memory asyncio.Queue），绝不阻塞/抛错到应答链路；后台 `_consume_loop` 阻塞 BRPOP 取单 → `store.write` → 容量卫兵。
- **有界重试**：写失败 `retries+1 ≤ max_retry(3)` 重入队，超限丢弃记日志，不无限重试。
- **chat 接线**：`chat/service.py` 会话结束 `asyncio.create_task(enqueue_turn(...))` + `try/except: pass` 不 await——应答链路最后一行无论成功失败都不影响返回。
- 契约测试：`test_write_failure_retries_without_raising`（前 2 次写失败自动重入队，第 3 次成功落库）、`test_enqueue_never_blocking_or_raising`（后台全失败 enqueue 仍恒成功返回）。

---

## 3. 独立子代理红线审查（R1-R5，独立上下文审查）

独立子代理（general_purpose_task）逐一读取 9 个 memory 模块 + config/graph/chat/DDL/测试，实跑 `pytest tests/test_contract_task25.py` 确认 11 passed，结论：

| 项 | 判定 | 核心证据 |
|----|------|------|
| R1 数据一致性 | ✅ PASS | DDL 11 列与 `persistence.py` `_SQL_FIELDS`/INSERT 逐列一致；字段长度截断（`memory_type[:32]/topic[:64]/content[:2000]`）与 DDL 对齐；`importance` 钳制 [1,5] 与 TINYINT UNSIGNED 对齐；import 全单向无循环 |
| R2 安全 | ✅ PASS | 无明文密钥（`MILVUS_TOKEN=""`）；SQL 全参数化 `%s`；Milvus filter `int()` 强转防注入；查询文本走 embedding 不进 SQL；队列/ingest/chat 均吞异常不泄漏到应答链路 |
| R3 正确性 | ✅ PASS | 遗忘公式与任务文档逐字一致；top-k=3 上限多处收敛；importance≥4 过滤（ingest + service 双轨）；容量>500 淘汰最低分；Milvus 不可达降级 in-memory 语义完整（upsert/search/delete 均回退） |
| R4 健壮性 | ✅ PASS | `retries ≤ max_retry` 有界不无限重试；空 content 拒绝（`return -1`）；向量 upsert 失败不影响事实源落库 |
| R5 契约冻结 | ✅ PASS | GWT①②③④ 均实现 + 测试覆盖；无新增 HTTP 端点（未破坏响应壳）；`recall_memory/recall_profile` 返回 `data + error` 判定式字典壳，与 `search_knowledge` 同族一致 |

**采纳的非阻断建议（一致性收尾）**：审查发现测试双件 `_MinimalQueue` 用 `retries < max_retry`、与真实 `queue._process` 的 `retries <= max_retry` 比较符不同 → 已改为 `<=` 与生产逐字一致（`tests/test_contract_task25.py:126-132`），复测 11/11 全绿。

---

## 4. 测试与工程质量

- `tests/test_contract_task25.py`：**11/11 通过**（GWT① 4 + GWT② 2 + GWT③ 3 + GWT④ 2）。
- 相邻回归：task24 `test_contract_task24.py` + task92 `test_contract_task92.py` **13/13 通过**（GWT②③ 接 graph.py / 子代理，未破坏）。
- `scripts/_verify_task25_memory.py`：**真库 + 真 Redis + in-memory 向量降级**端到端验证 PASS（GWT①③④ + GWT②召回）。
- DB 校验后清理验证数据（`user_id IN (90001,90002)` 清零），`user_memory` 空表入库待真实会话写入。
- 依赖基线：本任务未新增第三方依赖（全部复用 app.database.get_redis / asyncmy）；测试用 venv `.venv\Scripts\python.exe` 执行。

---

## 5. 数据库校验（RunCommand + mysql CLI / Python 脚本）

- `user_memory` 表已建：`SHOW COLUMNS FROM user_memory` 与 DDL 11 列逐列一致（bigint/timing(3)/utf8mb4）。
- 索引：`PRIMARY(id)` + `idx_um_user_created(user_id,created_at)` + `idx_um_user_score(user_id,score)` + `idx_um_user_type(user_id,memory_type)` 全部就位。
- 端到端真库验证（非 MOCK）：异步入队→消费落库→向量召回→容量遗忘，全部在 `edu` 库实库执行，证据见 §2 与 `_verify_task25_memory.py`。

> **Milvus 降级说明（契约内）**：Milvus collection 依赖外部 VM `192.168.85.101:19530`，本环境不可达（`MilvusException: Fail connecting to server`）。已按任务授权走 **in-process 内存向量降级**（`DeterministicEmbedder`，512 维），vector recall top-k 语义与链路可用性经验证成立。待存储机可达时 `backend` 自动切 `milvus`（`_try_init_milvus` 统一入口），无需改调用侧。

---

## 6. 交付物清单

| 产物 | 路径 |
|------|------|
| 三层记忆核心（schemas/score/vector/store/persistence） | `edu-agent/app/ai/memory/` |
| 显式触发 + 会话结束 ingest（R7） | `edu-agent/app/ai/memory/ingest.py` |
| 异步写队列 + 有界重试 + 容量卫兵 | `edu-agent/app/ai/memory/queue.py` |
| 门面 service（enqueue_turn/recall_topk/worker 生命周期） | `edu-agent/app/ai/memory/service.py` |
| LangGraph 工具接入（GWT②） | `edu-agent/app/ai/graph.py` |
| 会话结束异步 ingest 挂接（GWT①④） | `edu-agent/app/chat/service.py` |
| 三层记忆配置项（500/0.01/2.0/top-k=3/队列重试 3） | `edu-agent/app/config.py` |
| `user_memory` 表 DDL | `项目文档/patch_memory_tables.sql` |
| 契约测试（11 用例） | `edu-agent/tests/test_contract_task25.py` |
| 真库验证脚本 | `edu-agent/scripts/_verify_task25_memory.py` |

---

## 7. 交接与记忆

- 看板 task25 → 停等编排者验收（未验收不进入 task26）。
- sync.ps1 将运行；AI 助手代码属项目资产，写回 `.opencode/plans/aident-gate-MEMORY.md` 类索引不涉及（R7 MEMORY.md 索引模式文档随 task25 链路产出）。

**固化纪律**：三层记忆写长时仅收 importance≥4 的高价值信号；遗忘严格用 `importance×exp(-0.01·Δt)+recency_bonus`，高重要久未访问靠衰减而非误删；凡依赖外部存储的多模态（Milvus/Mongo/MinIO）先探测可达性，不可达按契约降级并在报告注明。