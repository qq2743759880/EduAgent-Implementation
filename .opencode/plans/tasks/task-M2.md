# task-M2 — Redis 共享向量降级（多实例一致性）

> 执行工具：**Trae** ｜ 依赖：task-M1, task25（现状） ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P2（多实例一致性）
> 核心定位：生产多实例下实例 A/B 各自内存向量导致同一用户召回不一致 → Milvus 不可达时降级到 **Redis 共享向量**（跨实例一致），Redis 也不可达才降级进程内 dict 并显式标注 `degraded_reason`。

## 1. 任务卡片

- **类型/工具**：backend（AI 记忆域） / Trae
- **依赖**：task-M1（`valid_to IS NULL` 预过滤语义共用；事件表为事实源）、task25（`vector.py` 现状）
- **并行组**：W4（第四批 P3，与 task-A1/E1 并行）
- **工作量**：**M**
- **测试窗口纪律**：无 LLM 依赖，可随时跑；Redis 需本机已启动（6379，原生 Redis 无模块）

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **Claude** | 降级时用 Redis 做共享内存向量，或直接拒绝向量检索退回关键词 | production-upgrade-plan.md P2 引述 |
| **rewind**（开源） | append-only Postgres + pgvector HNSW + **Redis pub/sub 横向扩展** | https://github.com/adi-suresh01/rewind |

## 3. 实现规划要点

### 3.1 `MemoryVectorStore` 增加 redis backend（改造 `app/ai/memory/vector.py`）

- 新增 backend 档位枚举 `backend ∈ {milvus, redis, memory}`，降级链：`milvus → redis → memory`。
- **Redis 共享向量结构**：
  - 每用户向量存 HSET：`memory:vec:{user_id}` → `{memory_id: json([vector])}`（content 存 MySQL 事件表，Redis 只存向量+id，避免双份大文本）；
  - 每用户元数据索引存 ZSET：`memory:vec:idx:{user_id}` → `{memory_id: score(importance*recency)}`，供全量 scan + 排序；
  - 搜索：从 HSET 取该用户全部向量做 cosine 排序（用户量级 1000×20/月=可控），或后续用 Redis Stack 向量模块时升级（当前原生 Redis 无模块，先做扫描式，`MEMORY_REDIS_SCAN_LIMIT=2000` 防大 key）；
  - **跨实例一致性**：写入用 Lua 原子（HSET + ZADD），读走同一 key → 实例 A/B 召回一致。
- **valid_to 联动（task-M1）**：Redis 只索引 `valid_to IS NULL` 的事件；Dream 巩固盖章时同步 `HDEL` 对应 memory_id（`app/ai/memory/service.py` 的盖章路径统一回调 `vector_store.invalidate(memory_id)`）。
- **降级标注**：`self.backend` 与 `self.degraded_reason` 如实反映 `milvus_unreachable` / `redis_unreachable`，Redis 不可达才落 `memory` 档 + `degraded_reason="redis_unreachable"`（对齐 GWT③）。
- **配置项**：

```python
MEMORY_VECTOR_BACKEND_ORDER = ["milvus", "redis", "memory"]
MEMORY_REDIS_VEC_KEY_PREFIX = "memory:vec"
MEMORY_REDIS_SCAN_LIMIT = 2000
```

### 3.2 契约测试

- `tests/test_contract_task_m2.py`：
  - Given Redis 可达 + Milvus 不可达，When upsert/search，Then backend=redis 且两实例（两个 `MemoryVectorStore` 实例）召回结果一致；
  - Given Redis 也不可达，When upsert/search，Then backend=memory 且 `degraded_reason="redis_unreachable"`；
  - Given 事件表有效记忆（task-M1 语义），When 盖章废弃，Then Redis 中该 memory_id 被剔除，检索不再返回。

## 4. 验收标准（Given/When/Then）

- **AC1（降级链）**：Given Milvus URI 指向不可达地址且 Redis 可达，When 实例 A 与实例 B 分别 upsert 同一用户记忆并 search，Then 两实例 backend=redis、召回结果（memory_id 集合与顺序）完全一致。
- **AC2（内存兜底标注）**：Given Milvus 与 Redis 均不可达，When search，Then backend=memory 且响应携带 `degraded_reason="redis_unreachable"`，不抛 500。
- **AC3（失效联动）**：Given Redis backend 下存在有效记忆，When task-M1 的 Dream 巩固将其盖 `valid_to`，Then Redis 索引中该 memory_id 被移除，search 永不返回。
- **AC4（跨实例并发写）**：Given 两实例同时 upsert 同一 memory_id 的不同内容版本，When 完成，Then Redis 最终状态一致（Lua 原子性），无丢失/脏读。
- **AC5（兼容回归）**：Given Milvus 正常，When 执行原 task25/task-M1 全部契约测试，Then 全 PASS（redis backend 不改变 milvus 主路径行为）。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-M2-completion-report.md`（降级链实测、双实例一致性对比、失效联动验证）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"Redis 是 Milvus 的唯一共享降级后端；进程内 dict 仅最后兜底"决策。
- **完成动作**：git commit → sync.ps1。

## 6. 批判承接

- **production-upgrade-plan.md P2**（内存向量多实例不一致）：实例 A/B 各自内存向量，同一用户召回不一致 → AC1/AC4 落实。
- **critique-backlog-tracker.md**：task39「真 Redis 分布式（bigkey/checkpoint 生产验证）」——本任务 Redis HSET/ZSET 需遵守既有 ZSET 分片约定（`zadd_sharded`），大 key 治理沿用 `scan_bigkeys`；task92 批判②「artifact 跨实例」——本任务验证的 Redis 共享模式可作为 artifact 跨实例参考实现。

## 7. 与其他 task 关联

- **联动**：task-M1（valid_to 过滤语义 + 失效回调）；task-O1（backend 切换/降级事件埋点，供 5 维指标中的"记忆命中率"归因）；task39（压测时纳入 Redis 降级链场景）。
- **执行顺序**：W4 第四批；建议在 task-M1 事件表落地后实施（AC3 依赖盖章回调）。