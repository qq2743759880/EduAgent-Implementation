"""task-M2 契约测试：Redis 共享向量降级链（多实例一致性）。

本沙箱无可达 Redis，按 ponytail + 代码库惯例（queue.py 内存 broker 兜底），
用共享内存 fake redis 模拟"多实例共享同一 Redis 后端"，验证跨实例一致/失效联动/并发语义。
生产路径 `app.database.get_redis()` 返回真实 redis.asyncio 客户端，接口一致。
"""
from __future__ import annotations

import asyncio

import pytest

from app.ai.memory.vector import MemoryVectorStore, DeterministicEmbedder
from app.ai.memory.store import MemoryStore
from app.ai.memory.event_persistence import MemEventMemoryPersistence


def _mid(hit: dict) -> int:
    """recall 输出键可能是 memory_id 或 id（兼容两种 schema）。"""
    return int(hit.get("memory_id", hit.get("id")))


# ---------------------------------------------------------------------------
# 共享内存 fake redis（duck-typed，覆盖本任务用到的子集）
# ---------------------------------------------------------------------------
class _SharedRedis:
    """单进程内共享字典，模拟多实例连同一台 Redis（AC1/AC4 跨实例一致）。"""

    def __init__(self, store: dict | None = None) -> None:
        self._s: dict = store if store is not None else {}

    async def ping(self):
        return True

    async def hset(self, key, field, value):
        b = self._s.setdefault(key, {"hash": {}, "zset": {}})
        b["hash"][str(field)] = value
        return 1

    async def hget(self, key, field):
        b = self._s.get(key)
        return b["hash"].get(str(field)) if b else None

    async def hdel(self, key, *fields):
        b = self._s.get(key)
        if not b:
            return 0
        c = 0
        for f in fields:
            if str(f) in b["hash"]:
                del b["hash"][str(f)]
                c += 1
        return c

    async def hmget(self, key, fields):
        b = self._s.get(key)
        if not b:
            return [None] * len(fields)
        return [b["hash"].get(str(f)) for f in fields]

    async def zadd(self, key, mapping):
        b = self._s.setdefault(key, {"hash": {}, "zset": {}})
        for m, s in mapping.items():
            b["zset"][str(m)] = float(s)
        return len(mapping)

    async def zrem(self, key, *members):
        b = self._s.get(key)
        if not b:
            return 0
        c = 0
        for m in members:
            if str(m) in b["zset"]:
                del b["zset"][str(m)]
                c += 1
        return c

    async def zrange(self, key, start, end):
        b = self._s.get(key)
        if not b or not b["zset"]:
            return []
        items = sorted(b["zset"].items(), key=lambda kv: (kv[1], kv[0]))
        return [m for m, _ in items]

    async def delete(self, key):
        self._s.pop(key, None)
        return 1


class _RedisDown:
    """ping 直接抛错，模拟 Redis 不可达（触发降级 memory + degraded_reason）。"""

    async def ping(self):
        raise ConnectionError("redis unreachable (simulated)")


# ---------------------------------------------------------------------------
# AC1：降级链 milvus→redis，双实例召回完全一致
# ---------------------------------------------------------------------------
class TestAC1CrossInstanceConsistency:
    async def test_two_instances_recall_identical(self):
        shared = _SharedRedis()
        # 注入确定性 embedder，隔离"embedding 噪声"，只验证 redis 共享后端的跨实例一致
        A = MemoryVectorStore(milvus_uri="", redis=shared, embedder=DeterministicEmbedder())
        B = MemoryVectorStore(milvus_uri="", redis=shared, embedder=DeterministicEmbedder())
        assert A.backend == "redis" and B.backend == "redis", "双实例均应落到 redis 档"

        # 实例 A、B 分别 upsert 同一用户的不同记忆
        await A.upsert(memory_id=1, user_id=7, content="Python 列表去重用 set")
        await B.upsert(memory_id=2, user_id=7, content="FastAPI 依赖注入机制")
        # 实例 B 写入后，实例 A 也应能搜到（跨实例可见）
        await A.upsert(memory_id=3, user_id=7, content="异步 asyncio 事件循环")

        ra = await A.search(user_id=7, query="Python 去重")
        rb = await B.search(user_id=7, query="Python 去重")
        # 召回集合 + 顺序 + 分数完全一致
        assert [h["memory_id"] for h in ra] == [h["memory_id"] for h in rb], "召回 memory_id 集合/顺序应一致"
        assert ra == rb, "跨实例召回结果应逐字段一致（含 cosine 分数）"

        # A 写入后 B 能搜到 → 共享后端
        found_by_b = await B.search(user_id=7, query="asyncio 事件循环")
        assert any(h["memory_id"] == 3 for h in found_by_b), "B 应能看到 A 写入的 memory_id=3"


# ---------------------------------------------------------------------------
# AC2：Milvus + Redis 均不可达 → backend=memory + degraded_reason，不 500
# ---------------------------------------------------------------------------
class TestAC2MemoryFallback:
    async def test_redis_unreachable_falls_to_memory(self):
        v = MemoryVectorStore(milvus_uri="", redis=_RedisDown())
        # 首次 IO 探测到 redis 不可达 → 降级 memory + 标注
        res = await v.search(user_id=1, query="任意")
        assert v.backend == "memory", "Redis 不可达应降级 memory"
        assert v.degraded_reason == "redis_unreachable", "应标注 degraded_reason=redis_unreachable"
        assert res == [], "memory 兜底不 500，空结果"

    async def test_redis_client_missing_falls_to_memory(self):
        # 不注入 redis 且 get_redis() 未初始化（测试环境）→ init 即判定 redis 不可达
        v = MemoryVectorStore(milvus_uri="")
        assert v.backend == "memory"
        assert v.degraded_reason == "redis_unreachable"
        await v.upsert(memory_id=1, user_id=1, content="兜底内容")
        assert (await v.search(user_id=1, query="兜底")).__len__() >= 1


# ---------------------------------------------------------------------------
# AC3：失效联动（valid_to 盖章 → Redis 移除，search 永不返回）
# ---------------------------------------------------------------------------
class TestAC3Invalidation:
    async def test_vector_invalidate_removes_from_redis(self):
        v = MemoryVectorStore(milvus_uri="", redis=_SharedRedis())
        await v.upsert(memory_id=5, user_id=9, content="旧记忆内容")
        assert any(h["memory_id"] == 5 for h in await v.search(user_id=9, query="旧记忆内容"))
        await v.invalidate(5)
        assert not any(h["memory_id"] == 5 for h in await v.search(user_id=9, query="旧记忆内容"))

    async def test_dream_consolidate_stamps_sources_out_of_index(self):
        # store 层：Dream 巩固合并源记忆 → 源实体向量从 Redis 索引移除（AC3 端到端）
        store = MemoryStore(
            MemEventMemoryPersistence(),
            MemoryVectorStore(milvus_uri="", redis=_SharedRedis()),
        )
        m1 = await store.write(user_id=11, content="喜欢 Python", memory_type="preference")
        m2 = await store.write(user_id=11, content="喜欢 FastAPI", memory_type="preference")
        await store.consolidate(
            source_entity_ids=[m1, m2],
            summary_content="技术栈偏好：Python / FastAPI",
            importance=5,
        )
        # 源记忆的向量已从 Redis 索引中剔除
        vhits = await store._vector.search(user_id=11, query="Python")
        assert not any(h["memory_id"] in (m1, m2) for h in vhits), "源记忆向量应被移除"
        # 合并后的新条目仍可被召回（to_recall_dict 不含 id，按内容判定）
        recall = await store.recall(user_id=11, query="技术栈")
        assert recall and any("技术栈偏好" in (h.get("content") or "") for h in recall), "合并条目应被召回"


# ---------------------------------------------------------------------------
# AC4：跨实例并发写同一 memory_id → 最终状态一致（LWW，无丢失/脏读）
# ---------------------------------------------------------------------------
class TestAC4ConcurrentWrite:
    async def test_concurrent_upsert_same_id_consistent(self):
        shared = _SharedRedis()
        emb = DeterministicEmbedder()
        A = MemoryVectorStore(milvus_uri="", redis=shared, embedder=emb)
        B = MemoryVectorStore(milvus_uri="", redis=shared, embedder=emb)
        # 两实例并发 upsert 同一 memory_id 的不同内容版本
        await asyncio.gather(
            A.upsert(memory_id=99, user_id=3, content="version A"),
            B.upsert(memory_id=99, user_id=3, content="version B"),
        )
        ra = await A.search(user_id=3, query="version")
        rb = await B.search(user_id=3, query="version")
        # 两实例读到的最终状态完全一致（共用 Redis，最后写入者胜出）
        assert ra == rb, "并发写后双实例召回状态应一致"
        assert ra and ra[0]["memory_id"] == 99


# ---------------------------------------------------------------------------
# AC5：回归 —— redis 改造不破坏 milvus 主路径 / memory 兜底基础行为
# ---------------------------------------------------------------------------
class TestAC5Regression:
    async def test_default_fallback_recall_unbroken(self):
        # 默认构造（无 milvus/redis 注入）：本环境降级 memory，基础 upsert/search 仍可用
        v = MemoryVectorStore()
        assert v.backend in ("memory", "milvus", "redis")
        await v.upsert(memory_id=1, user_id=1, content="基础回退")
        res = await v.search(user_id=1, query="基础回退")
        assert res and res[0]["memory_id"] == 1
