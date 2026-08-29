# -*- coding: utf-8 -*-
"""task-P1C：Neo4j / Redis 断连熔断 验证测试。

不依赖 LLM / 真实 Neo4j / 真实 Redis（全部用本地 fake 驱动 + 故障注入），随时可测。

覆盖：
- GWT①：Neo4j driver / Redis client 外层加 circuit breaker（closed/open/half-open）
- GWT②：连续 N 次失败 → OPEN，毫秒级快速失败（非等超时）；open_duration 后半开放行探针
- GWT③：降级带 degraded_reason + edu_degraded_total 计数（复用 task39 metrics）
- GWT④：验收——断连后延迟回 <5s；恢复后半开 → CLOSED

竞品对标：Codex auto-review 拒绝熔断、Gremlin Chaos Engineering（最小爆炸半径）。
复用 task33 core/breaker.py（CircuitOpenError + 半开）。
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.core import db_resilience as dr
from app.core.breaker import BreakerConfig, BreakerState, CircuitBreaker
from app.core import cache as cache_mod
import app.database as db_mod
import app.chat.retriever as retriever
import app.ai.memory.vector as vector_mod
from app.monitoring import metrics as metrics_mod


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_redis_sync(monkeypatch: pytest.MonkeyPatch):
    """断路器状态纯内存，避免测试触碰真实 Redis（含 Redis 自身作为被测依赖的情形）。"""

    async def _noop(self):
        return None

    monkeypatch.setattr(CircuitBreaker, "_sync_from_redis", _noop)
    monkeypatch.setattr(CircuitBreaker, "_sync_to_redis", _noop)
    yield


@pytest.fixture
def spy_metrics(monkeypatch: pytest.MonkeyPatch):
    """Spy metrics.record_degraded / clear_degraded（兼容两种 import 风格：模块级 + 直接绑定）。"""
    calls: list[tuple] = []
    real_rec = metrics_mod.record_degraded
    real_clr = metrics_mod.clear_degraded

    def rec(component, reason=None):
        calls.append(("record", component, reason))
        real_rec(component, reason)

    def clr(component):
        calls.append(("clear", component))
        real_clr(component)

    monkeypatch.setattr(metrics_mod, "record_degraded", rec)
    monkeypatch.setattr(metrics_mod, "clear_degraded", clr)
    # vector.py 以 `from app.monitoring.metrics import record_degraded as _record_degraded` 直接绑定
    monkeypatch.setattr(vector_mod, "_record_degraded", rec)
    return calls


def _fresh_breaker(name: str, *, failures: int = 3, open_duration: float = 0.2):
    """构造一个测试用断路器（连续 N 次失败开路；open_duration 可控）。"""
    return CircuitBreaker(
        name,
        config=BreakerConfig(
            consecutive_failures=failures,
            open_duration=open_duration,
            half_open_probes=1,
            min_requests=1,
            error_rate_threshold=1.0,
        ),
    )


# ─────────────────────────────────────────────────────────────
# GWT①+②+③+④：Neo4j 熔断状态机（单位级，redis_run 底层）
# ─────────────────────────────────────────────────────────────

async def test_neo4j_breaker_state_machine(spy_metrics, monkeypatch):
    brk = _fresh_breaker("t_neo4j", failures=3, open_duration=0.2)
    monkeypatch.setattr(dr, "neo4j_breaker", brk)

    def fail():
        raise ConnectionError("neo4j down")

    # CLOSED → 连续 3 次失败 → OPEN
    assert brk._state.value == "closed"
    for _ in range(3):
        with pytest.raises(ConnectionError):
            await dr.neo4j_run("graph_expand", fail)
    assert brk._state.value == "open"

    # OPEN 态：毫秒级快速失败（不触达依赖），实测 <1s（GWT④ 断连后 <5s）
    t0 = time.perf_counter()
    with pytest.raises(dr.DependencyUnavailableError):
        await dr.neo4j_run("graph_expand", fail)
    dt = time.perf_counter() - t0
    assert dt < 5.0, f"OPEN 态快失败超 5s: {dt:.3f}s"
    assert dt < 1.0, f"OPEN 态应毫秒级快失败, 实测 {dt:.3f}s"

    # GWT③：降级埋点（neo4j 至少被记录一次）
    assert any(c[0] == "record" and c[1] == "neo4j" for c in spy_metrics)

    # 半开：open_duration 后探针成功 → CLOSED
    await asyncio.sleep(0.3)
    assert await dr.neo4j_run("graph_expand", lambda: "ok") == "ok"
    assert brk._state.value == "closed"

    # 恢复后清降级态
    assert any(c[0] == "clear" and c[1] == "neo4j" for c in spy_metrics)


# ─────────────────────────────────────────────────────────────
# GWT①+②+③+④：Redis 熔断状态机（redis_run 底层，异步 coro）
# ─────────────────────────────────────────────────────────────

async def test_redis_breaker_state_machine(spy_metrics, monkeypatch):
    brk = _fresh_breaker("t_redis", failures=3, open_duration=0.2)
    monkeypatch.setattr(dr, "redis_breaker", brk)

    async def fail_async():
        raise ConnectionError("redis down")

    assert brk._state.value == "closed"
    for _ in range(3):
        with pytest.raises(ConnectionError):
            await dr.redis_run("cache_x", fail_async)
    assert brk._state.value == "open"

    t0 = time.perf_counter()
    with pytest.raises(dr.DependencyUnavailableError):
        await dr.redis_run("cache_x", fail_async)
    dt = time.perf_counter() - t0
    assert dt < 5.0 and dt < 1.0, f"OPEN 态快失败过慢: {dt:.3f}s"

    assert any(c[0] == "record" and c[1] == "redis" for c in spy_metrics)

    await asyncio.sleep(0.3)
    assert await dr.redis_run("cache_x", lambda: "ok") == "ok"
    assert brk._state.value == "closed"
    assert any(c[0] == "clear" and c[1] == "redis" for c in spy_metrics)


# ─────────────────────────────────────────────────────────────
# GWT② 半开探针失败 → 回到 OPEN（状态机鲁棒性）
# ─────────────────────────────────────────────────────────────

async def test_breaker_half_open_failure_reopens(spy_metrics, monkeypatch):
    brk = _fresh_breaker("t_reopen", failures=2, open_duration=0.15)
    monkeypatch.setattr(dr, "neo4j_breaker", brk)

    def fail():
        raise RuntimeError("down")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await dr.neo4j_run("x", fail)
    assert brk._state.value == "open"

    await asyncio.sleep(0.25)  # > open_duration → 半开
    with pytest.raises(RuntimeError):
        await dr.neo4j_run("x", fail)  # 探针失败
    assert brk._state.value == "open"  # 回到 OPEN


# ─────────────────────────────────────────────────────────────
# GWT④ 验收：_graph_expand（RAG 检索 29.4s 根因路径）
# 断连后：前 N 次走真实(慢)失败 → 开路；之后 ms 级降级返回 <5s
# ─────────────────────────────────────────────────────────────

async def test_graph_expand_degrades_fast_after_open(spy_metrics, monkeypatch):
    # 3 连失败开路；open_duration 足够长（测试期间保持 OPEN）
    brk = _fresh_breaker("neo4j", failures=3, open_duration=30.0)
    monkeypatch.setattr(dr, "neo4j_breaker", brk)

    FAIL = 0.4  # 单次失败耗时，模拟 Neo4j 连接超时尾（task39 实测 29.4s）

    class FakeSession:
        def run(self, *a, **k):
            time.sleep(FAIL)
            raise ConnectionError("neo4j unreachable")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeDriver:
        def session(self, **k):
            return FakeSession()

    monkeypatch.setattr(retriever, "get_neo4j_driver", lambda: FakeDriver())
    monkeypatch.setattr(retriever, "build_sparse_vector", lambda q: {"数据结构": 1.0, "算法": 1.0})
    monkeypatch.setattr(retriever, "ensure_jieba_ready", lambda: None)

    # 前 3 次（CLOSED，每次约 FAIL）：触发开路
    for _ in range(3):
        ents, deg = await retriever._graph_expand("q", enable_graph=True)
        assert ents == [] and deg is not None
    assert brk._state.value == "open"

    # 第 4 次：OPEN 态 ms 级快失败，不触达 Neo4j（不 sleep）
    t0 = time.perf_counter()
    ents, deg = await retriever._graph_expand("q", enable_graph=True)
    dt = time.perf_counter() - t0
    assert ents == [] and deg is not None
    assert dt < 5.0, f"断连后图谱扩展应 <5s, 实测 {dt:.3f}s"
    assert dt < 1.0, f"断连后图谱扩展应毫秒级降级, 实测 {dt:.3f}s"
    assert "熔断" in (deg or ""), f"降级原因应标明熔断: {deg}"


# ─────────────────────────────────────────────────────────────
# GWT④ 验收：cache.get_or_load（AI 问答 52.4s 主要根因路径）
# 断连后：前 N 次走真实(慢) Redis 失败 → 开路；之后 ms 级直通 DB <5s
# ─────────────────────────────────────────────────────────────

async def test_cache_get_or_load_falls_through_fast(spy_metrics, monkeypatch):
    brk = _fresh_breaker("redis", failures=3, open_duration=30.0)
    monkeypatch.setattr(dr, "redis_breaker", brk)

    FAIL = 0.4

    class FakeRedis:
        async def get(self, k):
            await asyncio.sleep(FAIL)
            raise ConnectionError("redis down")

        async def set(self, *a, **k):
            await asyncio.sleep(FAIL)
            raise ConnectionError("redis down")

        async def eval(self, *a, **k):
            await asyncio.sleep(FAIL)
            raise ConnectionError("redis down")

    monkeypatch.setattr(db_mod, "get_redis", lambda: FakeRedis())
    call_count = {"n": 0}

    async def loader():
        call_count["n"] += 1
        return "DB_VALUE"

    # 前 3 次：走 Redis（每次约 FAIL）失败 → 开路，失败即直通 DB
    for _ in range(3):
        val = await cache_mod.get_or_load("course:1", loader)
        assert val == "DB_VALUE"
    assert brk._state.value == "open"

    # 第 4 次：OPEN 态快失败 → 立即直通 DB（不 sleep）
    t0 = time.perf_counter()
    val = await cache_mod.get_or_load("course:1", loader)
    dt = time.perf_counter() - t0
    assert val == "DB_VALUE"
    assert dt < 5.0, f"断连后缓存读取应 <5s, 实测 {dt:.3f}s"
    assert dt < 1.0, f"断连后缓存应毫秒级直通 DB, 实测 {dt:.3f}s"
    assert call_count["n"] >= 4  # loader 被调用（直通 DB）


# ─────────────────────────────────────────────────────────────
# GWT①+②+③：记忆向量 _redis_ok（AI 问答 Redis 路径）开路态快失败
# 预置 redis_breaker=OPEN（模拟 upsert/search 已累积失败）→ ping 不触达 Redis
# ─────────────────────────────────────────────────────────────

async def test_memory_vector_ping_fast_fail_when_open(spy_metrics, monkeypatch):
    brk = _fresh_breaker("redis", failures=3, open_duration=30.0)
    monkeypatch.setattr(dr, "redis_breaker", brk)
    # 预开路
    brk._state = BreakerState.OPEN
    brk._opened_at = 0.0

    class FakeEmbedder:
        dim = 1024

        def embed_batch(self, texts):
            return [[0.0] * self.dim for _ in texts]

    class FakeRedis:
        async def ping(self):
            await asyncio.sleep(0.4)
            raise ConnectionError("redis down")

    store = vector_mod.MemoryVectorStore(redis=FakeRedis(), milvus_uri="", embedder=FakeEmbedder())
    assert store.backend == "redis"

    t0 = time.perf_counter()
    ok = await store._redis_ok()
    dt = time.perf_counter() - t0
    assert ok is False
    assert dt < 5.0 and dt < 1.0, f"_redis_ok 开路态应快失败, 实测 {dt:.3f}s"
    assert store.backend == "memory"  # 已降级
    assert store.degraded_reason == "redis_unreachable"
    assert any(c[0] == "record" and c[1] == "redis" for c in spy_metrics)


# ─────────────────────────────────────────────────────────────
# GWT③：Redis 自身作为被测依赖时，breaker 的 Redis 同步静默容错
# （不阻断熔断逻辑；否则 Redis breaker 会被自身依赖拖垮）
# ─────────────────────────────────────────────────────────────

async def test_breaker_redis_sync_fault_tolerant(monkeypatch):
    """breaker 的 _sync_from_redis/__sync_to_redis 在 Redis 不可达时静默跳过。"""
    brk = _fresh_breaker("t_sync", failures=2, open_duration=0.2)

    # 让 _get_redis 返回一个会抛错的客户端
    class BadRedis:
        async def hgetall(self, k):
            raise ConnectionError("backend redis down")

        async def hset(self, *a, **k):
            raise ConnectionError("backend redis down")

    async def fake_get_redis():
        return BadRedis()

    monkeypatch.setattr(brk, "_get_redis", fake_get_redis)

    def fail():
        raise RuntimeError("dep down")

    # 连续失败仍应正常开路（同步错误被静默吞掉，不阻断状态机）
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await brk.call(fail)
    assert brk._state.value == "open"
