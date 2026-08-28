# task-M2 完工报告 — Redis 共享向量降级链（多实例一致性）

> 执行工具：本地（ponytail：最短可用实现，零新依赖）
> 依赖：task-M1（`valid_to` 盖章语义 + `_sync_vector` 失效回调）、task25（`vector.py` 现状）
> 修订依据：`.opencode/plans/production-upgrade-plan.md` P2（多实例一致性）
> 状态：**验收待确认（W4 第四批 P3）**

## 1. 改造清单（6 文件 / +184 −4）

| 文件 | 改动 |
|---|---|
| `app/ai/memory/vector.py` | 新增 `redis` 档位，降级链 `milvus→redis→memory`；HSET 向量 + ZSET 索引 + owner 反向映射；`_redis_ok` 运行时心跳；`upsert/search/delete/clear_user` 三档分支；新增 `invalidate(memory_id)` |
| `app/ai/memory/store.py` | `consolidate` 中对源实体调用 `self._vector.invalidate(sid)`（Dream 盖章联动，AC3） |
| `app/config.py` | 新增 `MEMORY_VECTOR_BACKEND_ORDER` / `MEMORY_REDIS_VEC_KEY_PREFIX="memory:vec"` / `MEMORY_REDIS_SCAN_LIMIT=2000` |
| `tests/test_contract_task_m2.py` | 7 个契约测试（AC1~AC5），含共享内存 fake redis 模拟多实例 |
| `test-reports/task-M2-completion-report.md` | 本报告 |

**Redis 结构（生产）**
- HSET `memory:vec:{user_id}` → `{memory_id: json([vector])}`
- ZSET `memory:vec:idx:{user_id}` → `{memory_id: importance}`（枚举/排序索引，`MEMORY_REDIS_SCAN_LIMIT` 防大 key）
- HSET `memory:vec:owner` → `{memory_id: user_id}`（删除时无需已知 user_id）

## 2. 验收实测（AC1~AC5 全 PASS）

### AC1 降级链 + 跨实例一致 ✅
双实例 `MemoryVectorStore(milvus_uri="", redis=共享后端)`，backend 均 = `redis`。
实跑样本（注入确定性 embedder 隔离 BGE 噪声）：

```
backend_A redis   backend_B redis
A.recall [ (1, 0.7715), (2, 0.1376) ]
B.recall [ (1, 0.7715), (2, 0.1376) ]
IDENTICAL True
```

实例 A 写入后实例 B 立即可见（共享 key）→ 召回集合 / 顺序 / cosine 分数完全一致。

### AC2 内存兜底标注 ✅
`MemoryVectorStore(milvus_uri="", redis=RedisDown())` → 首次 IO 探测到 Redis 不可达 →
`backend=memory`、`degraded_reason="redis_unreachable"`、search 返回 `[]`、不抛 500。
（另测：未初始化 `get_redis()` 时 init 即判定 redis 不可达，同样结果。）

### AC3 失效联动 ✅
- 向量级：`upsert(5)` → `search` 命中；`invalidate(5)` → `search` 不再返回 5。
- 端到端（store 层）：`write` 两条偏好 → `consolidate` 合并 →
  `store._vector.search(user_id=11)` 中源 `memory_id` **已不在索引**；合并条目可被 `recall` 召回。
  印证 task-M1 盖章路径回调 `vector_store.invalidate`。

### AC4 跨实例并发写 ✅
两实例 `gather` 并发 upsert 同一 `memory_id=99` 的不同内容 → 完成后两实例 `search` 结果
`ra == rb`（共用 Redis，最后写入者胜出，无丢失/脏读）。

### AC5 兼容回归 ✅
`task25` + `task-M1` 全部契约测试 **20 passed**（与改造前基线逐条一致）。
`MemoryVectorStore()` 默认构造在双不可达环境下降级 memory，基础 upsert/search 仍可用。

## 3. 竞品实证对照
- **Claude 降级 Redis 共享向量**：本任务 `redis` 档位即该模式，Milvus 不可达时多实例统一走 Redis key，召回一致。
- **rewind（append-only + Redis pub/sub 横向扩展）**：本任务用 Redis 作为跨实例唯一共享向量后端，与 rewind "Redis 横向扩展" 思路一致（pub/sub 广播留给 task-O1 指标埋点，不在本任务范围）。

## 4. 批判与可落地优化（ponytail：明确删掉的过度设计）
1. **未引真 Redis 依赖 / 不接 Redis Stack 向量模块**：原生 Redis 无模块，先做 HSET 扫描式召回（用户量级可控）；升级到 Redis Stack 向量索引是后续独立优化，非本任务必需 → 已留 `MEMORY_REDIS_SCAN_LIMIT` 兜底。
2. **owner 反向映射多一个 HSET**：为让 `delete/invalidate` 无需已知 user_id（与现有 `_sync_vector(entity_id, None)` 签名一致），用 O(1) 反向查表替代全用户扫描 → 可接受的小开销。
3. **ZSET score 仅作枚举索引**：search 仍按 cosine 重排（与 in-memory 路径一致），保证 redis/memory 两档召回语义对齐；importance 写入 ZSET 供未来"重要性优先扫描"扩展，不引入排序耦合。
4. **心跳探测放在 IO 路径**：sync `__init__` 不 await ping（redis ping 是协程），可达性延迟到首次 upsert/search/delete 时探测并降级；init 仅按"客户端是否可取"判档，避免事件循环假设。
5. **测试用共享内存 fake redis**：本沙箱 `127.0.0.1:6379` 实际拒绝连接（与任务备注"已启动"不符），按代码库惯例（queue.py 内存 broker）用 duck-typed 共享字典模拟多实例连同一后端，证明跨实例一致/失效/并发语义；生产路径 `app.database.get_redis()` 接口一致，部署后无需改码。

## 5. git 与同步
- 单 commit（保护 17 个 prior-task staged 文件，沿用 loose-ref+packed-refs 修复）。
- 完工动作：`sync.ps1` 已运行（资产归集 + 渲染至 Trae/Claude/OpenCode/Codex/Cursor/OpenClaw）。
- 看板 `project-handoff.md` 第四批(P3) task-M2 行已更新。

## 6. 交接记忆（待 sync 落 AI-Hub `trae-projects/EduAgent/project_memory.md`）
"Redis 是 Milvus 的唯一共享降级后端；进程内 dict 仅最后兜底（degraded_reason=redis_unreachable）。"
