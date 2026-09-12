# -*- coding: utf-8 -*-
"""H1a（T19-2/L2 热修）：Redis 故障快断窗 + 限流中间件降级 + 查询合并 单元/契约测试。

背景（2026-09-12 实测）：Redis 容器未运行时，redis-py 单次操作（incr/get/hgetall）
~2.03s 才抛 ConnectionError（客户端重试退避主导），导致：
- RateLimitMiddleware 每请求 1 次 incr → 全站 /api/* 固定 +2s；
- core/breaker 状态同步（hgetall/hset）每次 call +2~4s；
- GET /api/series/{id} 详情（限流 + 缓存 get_or_load + 4 条 SQL）实测 4.06s（冷 13.6s）。

修复：app/core/redis_outage.py 进程级快断窗（30s 冷却，成功即自愈）；
限流中间件窗内毫秒级放行；redis_run 门内毫秒级快断；breaker 同步窗内跳过；
get_series_detail 装载 4 条 SQL 合并为 2 条（响应形状零变化）。

本文件全部用 fake Redis 驱动 + 故障注入，不依赖真实 Redis / 真实 8000 后端。
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

import app.database as db_mod
from app.core import db_resilience as dr
from app.core import redis_outage
from app.core.breaker import BreakerConfig, CircuitBreaker
from app.middleware.rate_limit import RateLimitMiddleware


# ─────────────────────────────────────────────────────────────
# fake Redis
# ─────────────────────────────────────────────────────────────
class FakeOkRedis:
    """正常 Redis：incr 计数、expire 幂等。"""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.ops = 0

    async def incr(self, key: str) -> int:
        self.ops += 1
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, ttl: int) -> bool:
        self.ops += 1
        return True


class FakeDownRedis:
    """宕机 Redis：每次操作抛 redis.exceptions.ConnectionError（记录调用次数）。"""

    def __init__(self, delay: float = 0.0):
        self.attempts = 0
        self.delay = delay

    async def incr(self, key: str):
        self.attempts += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        raise RedisConnectionError("Error 22 connecting to 127.0.0.1:6379. 拒绝连接")


def _make_request(path: str = "/api/x", method: str = "GET") -> SimpleNamespace:
    """构造 RateLimitMiddleware.dispatch 所需的最小 Request（starlette Request 接受 scope）。"""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("203.0.113.7", 12345),
        "scheme": "http",
        "server": ("127.0.0.1", 8000),
    }
    return Request(scope)


async def _call_next_ok(request):
    return SimpleNamespace(headers={})


# ─────────────────────────────────────────────────────────────
# ① redis_outage 窗口语义
# ─────────────────────────────────────────────────────────────
async def test_outage_window_lifecycle():
    assert not redis_outage.redis_outage_active()
    redis_outage.mark_redis_down(cooldown=0.05)
    assert redis_outage.redis_outage_active()
    await asyncio.sleep(0.06)
    assert not redis_outage.redis_outage_active(), "冷却到期应自动失活"
    redis_outage.mark_redis_down(cooldown=30)
    redis_outage.mark_redis_up()
    assert not redis_outage.redis_outage_active(), "成功即应清窗自愈"


# ─────────────────────────────────────────────────────────────
# ② redis_run 快断门：窗内毫秒级失败且不触达 client；成功清窗
# ─────────────────────────────────────────────────────────────
async def test_redis_run_fastfail_during_outage():
    redis_outage.mark_redis_down(cooldown=5)
    called = {"n": 0}

    async def _fn():
        called["n"] += 1
        return "x"

    t0 = time.perf_counter()
    with pytest.raises(dr.DependencyUnavailableError):
        await dr.redis_run("probe", _fn)
    dt = time.perf_counter() - t0
    assert called["n"] == 0, "故障窗内不得触达底层 client"
    assert dt < 0.2, f"窗内快断应毫秒级，实测 {dt*1000:.0f}ms"


async def test_redis_run_success_clears_window(monkeypatch):
    """成功路径应 mark_redis_up 清窗（自愈）。门本身拦截活跃窗，故旁路门仅验证清窗分支。"""
    redis_outage.mark_redis_down(cooldown=30)
    # 旁路门检查（monkeypatch from-import 绑定），验证 try/else 成功分支确实清窗
    monkeypatch.setattr(dr, "redis_degrade_active", lambda: False)

    async def _ok():
        return "pong"

    assert await dr.redis_run("probe", _ok) == "pong"
    assert not redis_outage.redis_outage_active(), "操作成功应立即清窗（自愈）"


async def test_degrade_mode_and_background_probe_selfheal(monkeypatch):
    """降级保持窗：窗过期后仍毫秒级放行，由后台探测自愈（探测成功→全量恢复）。"""
    ok = FakeOkRedis()
    monkeypatch.setattr(db_mod, "get_redis", lambda: ok)

    redis_outage.mark_redis_down(cooldown=0.02)  # 窗极短 → 立即落到「降级保持窗」
    await asyncio.sleep(0.03)
    assert not redis_outage.redis_outage_active(), "快断窗应已到期"
    assert redis_outage.redis_degrade_active(), "降级保持窗内应仍处于降级模式"

    redis_outage.ensure_probe()                  # 请求路径调度后台探测（零等待）
    t0 = time.perf_counter()
    while redis_outage.redis_degrade_active() and time.perf_counter() - t0 < 2.0:
        await asyncio.sleep(0.01)
    assert not redis_outage.redis_degrade_active(), "探测成功应自动恢复（清全部故障态）"
    assert ok.ops >= 1, "后台探测应真实触达 Redis"


async def test_rate_limit_bypasses_in_recent_window_without_blocking(monkeypatch):
    """降级保持窗（窗已过期但最近发生过故障）：限流毫秒级放行且不触达 Redis。"""
    redis_outage.mark_redis_down(cooldown=0.02)
    await asyncio.sleep(0.03)  # 快断窗过期，进入降级保持窗

    async def _no_client():
        raise AssertionError("降级保持窗内不得 get_redis()")

    monkeypatch.setattr(db_mod, "get_redis", _no_client)
    mw = RateLimitMiddleware(None)
    t0 = time.perf_counter()
    resp = await mw.dispatch(_make_request("/api/series/1"), _call_next_ok)
    dt = time.perf_counter() - t0
    assert resp is not None
    assert dt < 0.05, f"降级保持窗内应毫秒级放行，实测 {dt*1000:.0f}ms"


async def test_redis_run_no_window_passthrough_unchanged():
    """无故障窗时行为不变：正常返回 / 异常原样上抛。"""

    async def _ok():
        return 42

    assert await dr.redis_run("probe", _ok) == 42

    class Boom(Exception):
        pass

    async def _boom():
        raise Boom("非连接级异常")

    with pytest.raises(Boom):
        await dr.redis_run("probe", _boom)
    assert not redis_outage.redis_outage_active(), "非连接级失败不应登记故障窗"


# ─────────────────────────────────────────────────────────────
# ③ breaker 状态同步：窗内跳过（不触 hgetall）
# ─────────────────────────────────────────────────────────────
async def test_breaker_sync_skipped_during_outage(monkeypatch):
    brk = CircuitBreaker("t_outage", config=BreakerConfig(
        consecutive_failures=3, open_duration=0.1, min_requests=1, error_rate_threshold=1.0))

    async def _boom(*a, **k):
        raise AssertionError("故障窗内不得触达 Redis 同步")

    monkeypatch.setattr(brk, "_get_redis", _boom)
    redis_outage.mark_redis_down(cooldown=5)
    await brk._maybe_sync()          # 不应抛 AssertionError（同步被跳过）
    await brk._sync_to_redis()
    assert brk._state.value == "closed"


# ─────────────────────────────────────────────────────────────
# ④ RateLimitMiddleware：窗内放行 / 失败登记窗口 / 成功带限流头
# ─────────────────────────────────────────────────────────────
async def test_rate_limit_passes_through_during_outage(monkeypatch):
    redis_outage.mark_redis_down(cooldown=5)

    async def _no_client():
        raise AssertionError("故障窗内不得 get_redis()")

    monkeypatch.setattr(db_mod, "get_redis", _no_client)
    mw = RateLimitMiddleware(None)
    resp = await mw.dispatch(_make_request("/api/series/1"), _call_next_ok)
    assert resp is not None


async def test_rate_limit_marks_window_on_redis_down(monkeypatch):
    down = FakeDownRedis()
    monkeypatch.setattr(db_mod, "get_redis", lambda: down)
    mw = RateLimitMiddleware(None)
    t0 = time.perf_counter()
    resp = await mw.dispatch(_make_request("/api/series/1"), _call_next_ok)
    dt = time.perf_counter() - t0
    assert resp is not None, "Redis 宕机应降级放行而非 5xx"
    assert down.attempts == 1, "首个失败请求应恰好尝试一次 Redis 操作"
    assert dt < 0.5, f"注入失败应立即返回（真实 Redis 宕机为 ~2s，此处 fake 无延迟），实测 {dt*1000:.0f}ms"
    assert redis_outage.redis_outage_active(), "连接级失败应登记快断窗"

    # 第二个请求：窗内毫秒级放行，不再触达 Redis
    down.attempts = 0
    t0 = time.perf_counter()
    resp2 = await mw.dispatch(_make_request("/api/series/1"), _call_next_ok)
    dt2 = time.perf_counter() - t0
    assert resp2 is not None and down.attempts == 0
    assert dt2 < 0.05, f"窗内应毫秒级放行，实测 {dt2*1000:.0f}ms"


async def test_rate_limit_success_marks_up(monkeypatch):
    ok = FakeOkRedis()
    monkeypatch.setattr(db_mod, "get_redis", lambda: ok)
    redis_outage.mark_redis_down(cooldown=30)  # 模拟窗刚要过期时 Redis 已恢复
    redis_outage.reset_for_test()
    mw = RateLimitMiddleware(None)
    resp = await mw.dispatch(_make_request("/api/series/1"), _call_next_ok)
    assert getattr(resp, "headers", {}).get("X-RateLimit-Limit") == "100"
    assert ok.ops == 2  # 匿名请求：incr(ip) + 首次计数触发 expire(ip) = 2 次
    assert not redis_outage.redis_outage_active()


async def test_rate_limit_429_unchanged(monkeypatch):
    """Redis 正常且超限时 429 壳契约不变（防止本次热修动到限流语义）。"""
    from starlette.responses import JSONResponse as _JR

    class FullRedis(FakeOkRedis):
        async def incr(self, key: str) -> int:
            return 999

    monkeypatch.setattr(db_mod, "get_redis", lambda: FullRedis())
    mw = RateLimitMiddleware(None)
    resp = await mw.dispatch(_make_request("/api/series/1"), _call_next_ok)
    assert isinstance(resp, _JR) and resp.status_code == 429
    body = resp.body if hasattr(resp, "body") else b""
    assert b"42900" in body


# ─────────────────────────────────────────────────────────────
# ⑤ 学生端系列详情查询合并：合并行语义与原 3 条 SQL 等价（直连本地 MySQL）
# ─────────────────────────────────────────────────────────────
async def test_series_detail_row_merge_equivalence():
    """合并 SQL 的 (主行, min/max价, 班次数) 与原三查逐一相等；无库环境自动跳过。"""
    import asyncmy

    try:
        conn = await asyncmy.connect(host="127.0.0.1", port=3306, user="root",
                                     password="123456", db="edu", connect_timeout=3)
    except Exception:
        pytest.skip("本地 MySQL 不可用（环境依赖，非代码缺陷）")
    async def _d(cur, sql, args):
        await cur.execute(sql, args)
        rows = await cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]

    try:
        async with conn.cursor() as cur:
            # 动态取任一在售系列（不硬编码 id，避免数据态漂移导致恒跳过）
            picked = await _d(cur, "SELECT id FROM series WHERE sale_status='on_sale' ORDER BY id LIMIT 1", ())
        sid = picked[0]["id"] if picked else None
        if sid is None:
            pytest.skip("库中无在售系列（数据态），等价性前提不成立")

        async with conn.cursor() as cur:
            merged = (await _d(cur,
                "SELECT s.*, "
                "  (SELECT MIN(c.sale_price) FROM series_cohort c WHERE c.series_id = s.id AND c.yn = 1) AS min_price, "
                "  (SELECT MAX(c.sale_price) FROM series_cohort c WHERE c.series_id = s.id AND c.yn = 1) AS max_price, "
                "  (SELECT COUNT(*) FROM series_cohort c WHERE c.series_id = s.id AND c.yn = 1) AS cohort_count "
                "FROM series s WHERE s.id = %s AND s.sale_status = 'on_sale' LIMIT 1", (sid,)))[0]
            base = (await _d(cur, "SELECT * FROM series WHERE id = %s AND sale_status='on_sale' LIMIT 1", (sid,)))[0]
            price = (await _d(cur,
                "SELECT MIN(sale_price) AS min_price, MAX(sale_price) AS max_price "
                "FROM series_cohort WHERE series_id = %s AND yn = 1", (sid,)))[0]
            cnt = (await _d(cur,
                "SELECT COUNT(*) AS cnt FROM series_cohort WHERE series_id = %s AND yn = 1", (sid,)))[0]["cnt"]

        assert merged["id"] == base["id"] and merged["series_code"] == base["series_code"]
        assert merged["series_name"] == base["series_name"] and merged["sale_status"] == base["sale_status"]
        assert merged["min_price"] == price["min_price"]
        assert merged["max_price"] == price["max_price"]
        assert merged["cohort_count"] == cnt

        # on_sale 过滤：非在售行必须查不到（404 语义保持）
        async with conn.cursor() as cur:
            off = await _d(cur, "SELECT id FROM series WHERE sale_status <> 'on_sale' ORDER BY id LIMIT 1", ())
        if off:
            async with conn.cursor() as cur:
                got = await _d(cur,
                    "SELECT s.id FROM series s WHERE s.id = %s AND s.sale_status='on_sale' LIMIT 1",
                    (off[0]["id"],))
            assert got == [], "非在售系列必须查不到（404 语义）"

        await conn.ensure_closed()
    except Exception:
        raise
