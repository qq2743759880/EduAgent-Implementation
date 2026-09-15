# -*- coding: utf-8 -*-
"""F-2 积分双源同步契约测试（不依赖真实 MySQL/Redis，纯 monkeypatch）。

钉死两件事，防回归：
1. 事件驱动同步：``award_points`` MySQL 落账成功后必须向 4 个 scope 的 POINTS ZSET
   ZINCRBY 同一增量；幂等命中（biz_key 重复）/ delta=0 不重复写；Redis 故障 fail-open
   不影响 MySQL 落账返回值。
2. 读取侧读修复：``_self_heal_my_points`` 以 MySQL 账本为准，ZSET 漂移即 ZADD 绝对
   对齐并修正返回行；Redis 写失败仍返回账本真值；账本查询异常则原样返回（fail-open）。
"""
from __future__ import annotations

from datetime import datetime

import pytest

import app.database as database
import app.gamification.service as gsvc


class _FakeRedis:
    """仅记录 ZSET 写入的假 Redis；可注入故障。"""

    def __init__(self, *, zadd_raises: bool = False):
        self.calls: list[tuple] = []
        self.expires: list[tuple] = []
        self.zadds: list[tuple[str, dict]] = []
        self._zadd_raises = zadd_raises

    async def zincrby(self, key, amount, value):
        self.calls.append((key, amount, value))
        return None

    async def expire(self, key, ttl):
        self.expires.append((key, ttl))

    async def zadd(self, key, mapping):
        if self._zadd_raises:
            raise RuntimeError("redis down")
        self.zadds.append((key, dict(mapping)))


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(database, "get_redis", lambda: fake)
    return fake


async def test_award_points_zincrby_four_scopes_and_idempotent(fake_redis, monkeypatch):
    """新流水落账 → 4 个 scope ZSET 各 ZINCRBY 一次；重复 biz_key → 不再 ZINCRBY。"""

    calls = {"n": 0}

    async def _fake_fetch_one(sql, args):
        if sql.lstrip().startswith("SELECT id"):
            calls["n"] += 1
            return None if calls["n"] == 1 else {"id": 999}  # 首次幂等未命中，二次命中
        return {"s": 100}  # 当前余额 SUM

    async def _fake_execute_write(sql, args):
        return 1

    monkeypatch.setattr(gsvc, "fetch_one", _fake_fetch_one)
    monkeypatch.setattr(gsvc, "execute_write", _fake_execute_write)

    added = await gsvc.award_points(7, "biz-f2-1", "COMMENT_CREATE", 2, note="x")
    assert added == 2
    assert len(fake_redis.calls) == 4
    scopes_hit = {c[0].split(":")[1] for c in fake_redis.calls}
    assert scopes_hit == {"DAILY", "WEEKLY", "MONTHLY", "ALL_TIME"}
    assert all(c[1] == 2 and c[2] == "7" for c in fake_redis.calls)

    # 幂等命中：返回 0，ZSET 无新增
    added_dup = await gsvc.award_points(7, "biz-f2-1", "COMMENT_CREATE", 2, note="x")
    assert added_dup == 0
    assert len(fake_redis.calls) == 4


async def test_award_points_redis_outage_fail_open(fake_redis, monkeypatch):
    """get_redis 抛 RuntimeError（Redis 未初始化/不可用）→ 积分照常落账，不抛错。"""

    async def _fetch_one(sql, args):
        return None if sql.lstrip().startswith("SELECT id") else {"s": 10}

    async def _execute_write(sql, args):
        return 1

    monkeypatch.setattr(gsvc, "fetch_one", _fetch_one)
    monkeypatch.setattr(gsvc, "execute_write", _execute_write)
    monkeypatch.setattr(database, "get_redis", lambda: (_ for _ in ()).throw(RuntimeError("no redis")))

    assert await gsvc.award_points(8, "biz-f2-2", "POST_CREATE", 5) == 5


async def test_self_heal_corrects_drift_with_zadd(fake_redis, monkeypatch):
    """ZSET 行 35 与账本 349 漂移 → ZADD 绝对写回 349，返回行同步修正，他人行不动。"""
    async def _truth(user_id, scope, dimension):
        assert dimension == "POINTS"
        return 349

    monkeypatch.setattr(gsvc, "_user_metric_value", _truth)
    snap = [
        {"rank_no": 1, "user_id": 100003, "metric_value": 160},
        {"rank_no": 2, "user_id": 1, "metric_value": 35},
    ]
    now = datetime.utcnow()
    out = await gsvc._self_heal_my_points(1, "ALL_TIME", snap, now)
    assert out[1]["metric_value"] == 349
    assert out[0]["metric_value"] == 160
    assert fake_redis.zadds == [(gsvc._rank_zset_key("ALL_TIME", "POINTS", now), {"1": 349})]


async def test_self_heal_no_drift_no_write(fake_redis, monkeypatch):
    async def _truth(user_id, scope, dimension):
        return 35

    monkeypatch.setattr(gsvc, "_user_metric_value", _truth)
    snap = [{"user_id": 1, "metric_value": 35}]
    out = await gsvc._self_heal_my_points(1, "MONTHLY", snap, datetime.utcnow())
    assert out[0]["metric_value"] == 35
    assert fake_redis.zadds == []


async def test_self_heal_redis_write_failure_still_returns_truth(monkeypatch):
    """ZADD 失败（Redis 故障）→ 不抛错，本次返回仍按 MySQL 真值。"""
    fake = _FakeRedis(zadd_raises=True)
    monkeypatch.setattr(database, "get_redis", lambda: fake)

    async def _truth(user_id, scope, dimension):
        return 186

    monkeypatch.setattr(gsvc, "_user_metric_value", _truth)
    snap = [{"user_id": 1, "metric_value": 35}]
    out = await gsvc._self_heal_my_points(1, "MONTHLY", snap, datetime.utcnow())
    assert out[0]["metric_value"] == 186  # 响应对齐账本


async def test_self_heal_truth_query_error_returns_original_snap(monkeypatch):
    async def _boom(user_id, scope, dimension):
        raise RuntimeError("db down")

    monkeypatch.setattr(gsvc, "_user_metric_value", _boom)
    snap = [{"user_id": 1, "metric_value": 35}]
    out = await gsvc._self_heal_my_points(1, "ALL_TIME", snap, datetime.utcnow())
    assert out is snap and out[0]["metric_value"] == 35


async def test_self_heal_user_not_in_rows_no_write(fake_redis, monkeypatch):
    async def _truth(user_id, scope, dimension):
        return 349

    monkeypatch.setattr(gsvc, "_user_metric_value", _truth)
    snap = [{"user_id": 100003, "metric_value": 160}]  # 请求者不在榜（插值路径另算）
    out = await gsvc._self_heal_my_points(1, "ALL_TIME", snap, datetime.utcnow())
    assert fake_redis.zadds == [] and out[0]["metric_value"] == 160
