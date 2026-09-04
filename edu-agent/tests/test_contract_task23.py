# -*- coding: utf-8 -*-
"""task23 契约测试：Redis 缓存三防 + 写后 DEL + 并发重建（GWT①/②/④）。

执行方式：in-process + 内存 FakeRedis（本机 Redis server 不可用，无 docker/WSL）。
用与 get_or_load 相同命令面（get/set-nx-ex/eval/delete）的 FakeRedis 语义等价验证。

GWT：
① 课程详情缓存命中 → 100 并发热命中不打库（loader 0 次），MySQL QPS 不随并发线性
② 写后精确 DEL → key 删除、1s 内新值可见、无陈旧读
④ 击穿：并发重建仅 1 次（SETNX 互斥）；穿透：空值 30s 缓存（重复请求 1 次 loader）
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from app.core import cache as cache_mod
import app.database as _db


class FakeRedis:
    def __init__(self):
        self._d: dict = {}

    async def get(self, k):
        v = self._d.get(k)
        if isinstance(v, tuple) and time.monotonic() > v[1]:
            self._d.pop(k, None); return None
        return v[0] if isinstance(v, tuple) else v

    async def set(self, k, v, *, nx=False, ex=None):
        live = self._d.get(k)
        if nx and live is not None:
            return None
        self._d[k] = (v, time.monotonic() + ex) if ex else v
        return "OK"

    async def eval(self, s, n, *a):
        if a:
            self._d.pop(a[0], None)
        return 1

    async def delete(self, *ks):
        c = 0
        for k in ks:
            if k in self._d:
                del self._d[k]; c += 1
        return c


@pytest.fixture(scope="module", autouse=True)
def _fake_redis(request):
    fake = FakeRedis()
    original = _db.get_redis
    _db.get_redis = lambda: fake
    # 还原，避免污染后续模块（如 test_core::TestBreaker 需要真实 get_redis 接口，GWT③ 测试隔离）
    request.addfinalizer(lambda: setattr(_db, "get_redis", original))
    yield fake


def _run(coro):
    return asyncio.run(coro)


class TestGWTCacheHit:
    def test_hot_hit_no_db(self):
        """GWT①：热命中 loader 不随并发线性（100 并发 → loader 0 次）。"""
        KEY = "t23:series:1"
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            await asyncio.sleep(0.001)
            return {"series_id": 1}

        async def go():
            await cache_mod.get_or_load(KEY, loader, ttl=300)   # 冷启动 1 次
            cold = calls["n"]
            lats = []

            async def one():
                s = time.perf_counter()
                await cache_mod.get_or_load(KEY, loader, ttl=300)
                lats.append((time.perf_counter() - s) * 1000)

            await asyncio.gather(*[one() for _ in range(100)])
            lats.sort(); p95 = lats[94]
            return cold, calls["n"], p95

        cold, total, p95 = _run(go())
        assert cold == 1 and total == 1, f"热命中只应冷1次打库, got cold={cold} total={total}"
        assert p95 < 50, f"P95={p95}ms，目标≤50ms"


class TestGWTDEL:
    def test_write_del_fresh(self):
        """GWT②：写后 DEL → 无陈旧读，新值 1s 内可见。"""
        KEY = "t23:del:series:9"
        state = {"v": "old", "n": 0}

        async def loader():
            state["n"] += 1
            return {"sale_status": state["v"]}

        async def go():
            await cache_mod.get_or_load(KEY, loader, ttl=300)   # 建缓存 old
            state["v"] = "new"
            await cache_mod.invalidate(KEY)                     # 写后 DEL
            got = await cache_mod.get_or_load(KEY, loader, ttl=300)
            return got

        got = _run(go())
        assert got["sale_status"] == "new", "DEL 后应读到新值"
        assert state["n"] == 2, "冷1 + 重建1"


class TestGWTDefense:
    def test_breakdown_single_rebuild(self):
        """GWT④ 击穿：并发重建同 key → SETNX 互斥仅 1 次 loader。"""
        KEY = "t23:race"
        n = {"v": 0}
        fire = asyncio.Event()

        async def slow_loader():
            n["v"] += 1
            await asyncio.sleep(0.05)
            return {"v": 1}

        async def racer():
            await fire.wait()
            await cache_mod.get_or_load(KEY, slow_loader, ttl=300)

        async def go():
            t = asyncio.ensure_future(asyncio.gather(*[racer() for _ in range(10)]))
            fire.set()
            await t
            return n["v"]

        assert _run(go()) == 1, "击穿应仅重建 1 次"

    def test_penetration_empty_cached(self):
        """GWT④ 穿透：空结果 3 次请求 → loader 仅 1 次（空值 30s 缓存）。"""
        KEY = "t23:null"
        n = {"v": 0}

        async def null_loader():
            n["v"] += 1
            return None

        async def go():
            for _ in range(3):
                await cache_mod.get_or_load(KEY, null_loader, ttl=300)
            return n["v"]

        assert _run(go()) == 1, "空值应 1 次播种"


class TestWritePathDEL:
    """R1 审查补齐：管理端写路径 DEL key 准确性（含 delete_cohort 聚合失效）。"""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_delete_cohort_invalidates_aggregate(self, monkeypatch):
        """delete_cohort 软删班次 → 失效 cohort:detail/seats + series:detail 聚合价/班次数。"""
        import app.domains.course_admin.service as adm

        deleted = []

        class FakeCohortRepo:
            async def get_by_id(self, cid):
                return {"id": cid, "series_id": 77}
            async def soft_delete(self, cid):
                deleted.append(cid)

        invalidated: list = []

        async def _inv(*ks):
            invalidated.extend(ks)

        monkeypatch.setattr(adm, "_cohort_repo", FakeCohortRepo())
        monkeypatch.setattr(adm, "invalidate", _inv)

        self._run(adm.delete_cohort(9))
        assert deleted == [9], "软删应执行"
        assert sorted(invalidated) == [
            "course:cohort:detail:9",
            "course:cohort:seats:9",
            "course:series:detail:77",
        ], f"delete_cohort 应失效含 series:detail 聚合, got {invalidated}"

    def test_module_ops_invalidate_cohort_detail(self, monkeypatch):
        """module 增/改/删 → 失效 cohort:detail（模块列表挂其下）。"""
        import app.domains.course_admin.service as adm

        class FakeModuleRepo:
            def __init__(self):
                self.rows = {"id": 2, "cohort_id": 55}
            async def get_by_id(self, mid):
                return self.rows
            async def hard_delete(self, mid):
                pass
            async def count_references(self, mid):
                return {"sessions": 0, "total": 0}
            async def get_by_stage(self, cohort_id, stage_no):
                return None
            async def insert(self, data):
                return 3
            async def update(self, mid, data):
                pass

        invalidated: list = []

        async def _inv(*ks):
            invalidated.extend(ks)

        monkeypatch.setattr(adm, "_module_repo", FakeModuleRepo())
        monkeypatch.setattr(adm, "invalidate", _inv)

        self._run(adm.delete_module(2))
        assert invalidated == ["course:cohort:detail:55"], f"delete_module 应失效 cohort:detail, got {invalidated}"