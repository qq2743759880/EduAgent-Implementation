"""task09: core/ 框架层单测套件（8 模块 + 并发/故障注入）"""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.resp import ok, fail, RespModel
from app.core.cache import get_or_load, invalidate
from app.core.lock import RedisLock
from app.core.idempotency import Idempotency, get_idempotency
from app.core.breaker import (
    CircuitBreaker, CircuitOpenError, BreakerState, BreakerConfig,
    get_breaker,
)
from app.core.trace import trace_id_var, span_id_var, get_trace_id, generate_trace_id, start_span
from app.core.queue import TaskQueue, get_queue, enqueue, dequeue


# ============================================================
# 1. resp.py
# ============================================================
class TestResp:
    def test_ok_default(self):
        result = ok()
        assert result == {"code": 0, "message": "ok", "data": None}

    def test_ok_with_data(self):
        result = ok(data={"user": "test"}, message="success")
        assert result["code"] == 0
        assert result["data"] == {"user": "test"}
        assert result["message"] == "success"

    def test_fail_string_code(self):
        result = fail("AUTH_EXPIRED", "登录已过期")
        assert result["code"] == "AUTH_EXPIRED"
        assert result["message"] == "登录已过期"
        assert result["data"] is None

    def test_fail_int_code(self):
        result = fail(404, "Not Found")
        assert result["code"] == 404

    def test_resp_model(self):
        m = RespModel(code=0, message="ok", data={"a": 1})
        d = m.model_dump()
        assert d["code"] == 0
        assert d["data"] == {"a": 1}


# ============================================================
# 2. cache.py (三防：穿透/击穿/雪崩)
# ============================================================
class TestCache:
    """Redis 缓存测试（mock Redis）。"""

    @pytest.fixture
    def mock_redis(self):
        store = {}

        async def _get(key):
            return store.get(key)

        async def _set(key, value, **kwargs):
            store[key] = value
            return True

        async def _delete(*keys):
            for k in keys:
                store.pop(k, None)

        async def _eval(script, num_keys, *args):
            # 简化 Lua 脚本：释放锁
            if "del" in script:
                k = args[0]
                if store.get(k) == args[1]:
                    store.pop(k, None)
            return 0

        r = AsyncMock()
        r.get = AsyncMock(side_effect=_get)
        r.set = AsyncMock(side_effect=_set)
        r.delete = AsyncMock(side_effect=_delete)
        r.eval = AsyncMock(side_effect=_eval)
        return r, store

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_redis):
        r, store = mock_redis
        store["test:key"] = '"cached_value"'
        with patch("app.database.get_redis", return_value=r):
            result = await get_or_load("test:key", lambda: "fresh")
            assert result == "cached_value"

    @pytest.mark.asyncio
    async def test_cache_miss_loader_called(self, mock_redis):
        r, store = mock_redis
        call_count = 0

        async def loader():
            nonlocal call_count
            call_count += 1
            return "fresh_data"

        with patch("app.database.get_redis", return_value=r):
            result = await get_or_load("test:miss", loader)
            assert result == "fresh_data"
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_null_cache_penetration(self, mock_redis):
        r, store = mock_redis
        call_count = 0

        async def loader():
            nonlocal call_count
            call_count += 1
            return None

        with patch("app.database.get_redis", return_value=r):
            result = await get_or_load("test:null", loader)
            assert result is None
            # 空值应写入哨兵
            assert store.get("test:null") == "__NULL__"

    @pytest.mark.asyncio
    async def test_mutex_lock_acquired(self, mock_redis):
        r, store = mock_redis
        # 第一次 SET NX 成功（抢到锁）
        r.set.side_effect = None
        r.set.return_value = True

        async def loader():
            return "data"

        with patch("app.database.get_redis", return_value=r):
            result = await get_or_load("test:mutex", loader)
            assert result == "data"

    @pytest.mark.asyncio
    async def test_redis_down_fallback(self):
        """Redis 不可用 → 直通 DB。"""
        call_count = 0

        async def loader():
            nonlocal call_count
            call_count += 1
            return "fallback_data"

        with patch("app.database.get_redis", side_effect=RuntimeError):
            result = await get_or_load("test:down", loader)
            assert result == "fallback_data"
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_concurrent_get_or_load(self, mock_redis):
        """并发 100 请求同一 key，仅 1 个 loader 重建。"""
        r, store = mock_redis
        call_count = 0

        async def loader():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return "concurrent_data"

        # 第一次 SET NX 返回 True（抢到锁），后续返回 False
        lock_acquired = [False]
        async def _set(key, value, nx=False, ex=None):
            if nx:
                if not lock_acquired[0]:
                    lock_acquired[0] = True
                    return True
                return False
            store[key] = value
            return True

        r.set.side_effect = _set

        with patch("app.database.get_redis", return_value=r):
            tasks = [asyncio.create_task(get_or_load("test:concurrent", loader)) for _ in range(100)]
            results = await asyncio.gather(*tasks)

        assert all(r == "concurrent_data" for r in results)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_short_polling_gets_value(self, mock_redis):
        """没抢到锁时，短轮询等待后获取到新值。"""
        r, store = mock_redis
        loaded = [False]

        async def _set(key, value, nx=False, ex=None):
            if nx:
                return False  # 锁被占用
            store[key] = value
            return True

        async def _get(key):
            if loaded[0]:
                return '"polled_value"'
            return None

        r.set.side_effect = _set
        r.get.side_effect = _get

        async def loader():
            loaded[0] = True
            # 写入缓存供短轮询获取
            store["test:poll"] = '"polled_value"'
            return "polled_value"

        with patch("app.database.get_redis", return_value=r):
            result = await get_or_load("test:poll", loader)
            assert result == "polled_value"

    @pytest.mark.asyncio
    async def test_invalidate(self, mock_redis):
        r, store = mock_redis
        store["test:del"] = "value"
        with patch("app.database.get_redis", return_value=r):
            await invalidate("test:del")
            assert "test:del" not in store

    @pytest.mark.asyncio
    async def test_invalidate_redis_down(self):
        with patch("app.database.get_redis", side_effect=RuntimeError):
            await invalidate("test:down")  # 不应抛异常


# ============================================================
# 3. lock.py
# ============================================================
class TestLock:
    @pytest.mark.asyncio
    async def test_acquire_success(self):
        mock_r = AsyncMock()
        mock_r.set.return_value = True
        mock_r.eval.return_value = 1

        with patch("app.database.get_redis", return_value=mock_r):
            lock = RedisLock("test", timeout=10)
            result = await lock.acquire()
            assert result is True
            mock_r.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_with_lua_token(self):
        mock_r = AsyncMock()
        mock_r.set.return_value = True
        mock_r.eval.return_value = 1

        with patch("app.database.get_redis", return_value=mock_r):
            lock = RedisLock("test", timeout=10)
            await lock.acquire()
            await lock.release()
            # release 应该调用 Lua eval
            mock_r.eval.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_down_fallback(self):
        with patch("app.database.get_redis", side_effect=RuntimeError):
            lock = RedisLock("test", timeout=10)
            result = await lock.acquire()
            assert result is True  # 降级放行

    @pytest.mark.asyncio
    async def test_context_manager(self):
        mock_r = AsyncMock()
        mock_r.set.return_value = True
        mock_r.eval.return_value = 1

        with patch("app.database.get_redis", return_value=mock_r):
            async with RedisLock("test", timeout=10) as lock:
                assert lock._token is not None
            mock_r.eval.assert_called_once()


# ============================================================
# 4. idempotency.py
# ============================================================
class TestIdempotency:
    @pytest.fixture
    def mock_redis(self):
        store = {}

        async def _get(key):
            return store.get(key)

        async def _set(key, value, nx=False, ex=None):
            if nx and key in store:
                return False
            store[key] = value
            return True

        async def _delete(key):
            store.pop(key, None)

        r = AsyncMock()
        r.get = AsyncMock(side_effect=_get)
        r.set = AsyncMock(side_effect=_set)
        r.delete = AsyncMock(side_effect=_delete)
        return r, store

    @pytest.mark.asyncio
    async def test_check_first_time(self, mock_redis):
        r, store = mock_redis
        idem = Idempotency()
        with patch.object(idem, "_get_redis", return_value=r):
            result = await idem.check("order:123")
            assert result is None  # 首次，未处理

    @pytest.mark.asyncio
    async def test_save_and_check(self, mock_redis):
        r, store = mock_redis
        idem = Idempotency()
        with patch.object(idem, "_get_redis", return_value=r):
            await idem.save("order:123", {"status": "ok"})
            result = await idem.check("order:123")
            assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_save_duplicate(self, mock_redis):
        r, store = mock_redis
        idem = Idempotency()
        with patch.object(idem, "_get_redis", return_value=r):
            ok1 = await idem.save("order:123", {"first": True})
            ok2 = await idem.save("order:123", {"second": True})
            assert ok1 is True
            assert ok2 is False  # 重复被拒绝

    @pytest.mark.asyncio
    async def test_redis_down_fallback(self):
        idem = Idempotency()
        with patch.object(idem, "_get_redis", return_value=None):
            result = await idem.check("order:123")
            assert result is None  # 降级放行
            ok = await idem.save("order:123", {"status": "ok"})
            assert ok is True  # 降级放行

    @pytest.mark.asyncio
    async def test_invalidate(self, mock_redis):
        r, store = mock_redis
        idem = Idempotency()
        with patch.object(idem, "_get_redis", return_value=r):
            await idem.save("order:inv", {"status": "ok"})
            assert "idem:order:inv" in store
            await idem.invalidate("order:inv")
            assert "idem:order:inv" not in store

    def test_get_idempotency_singleton(self):
        idem1 = get_idempotency()
        idem2 = get_idempotency()
        assert idem1 is idem2


# ============================================================
# 5. breaker.py (三态 + Redis Hash + Gauge)
# ============================================================
class TestBreaker:
    def test_init_state_closed(self):
        b = CircuitBreaker("test")
        assert b._state == BreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_call_success(self):
        b = CircuitBreaker("test")
        result = await b.call(lambda: "ok")
        assert result == "ok"
        assert b._state == BreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_call_async_success(self):
        b = CircuitBreaker("test")
        async def fn():
            return "async_ok"
        result = await b.call(fn)
        assert result == "async_ok"

    @pytest.mark.asyncio
    async def test_closed_to_open(self):
        """注入 50% 错误率，closed → open。"""
        config = BreakerConfig(min_requests=10, error_rate_threshold=0.5)
        b = CircuitBreaker("test", config=config)

        errors = 0
        for i in range(20):
            try:
                if i % 2 == 0:
                    await b.call(lambda: "ok")
                else:
                    await b.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except (CircuitOpenError, ValueError):
                errors += 1

        assert b._state == BreakerState.OPEN

    @pytest.mark.asyncio
    async def test_open_raises_circuit_open_error(self):
        config = BreakerConfig(min_requests=10, error_rate_threshold=0.5)
        b = CircuitBreaker("test", config=config)

        for i in range(20):
            try:
                await b.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except (ValueError, CircuitOpenError):
                pass

        assert b._state == BreakerState.OPEN
        with pytest.raises(CircuitOpenError):
            await b.call(lambda: "should_not_run")

    @pytest.mark.asyncio
    async def test_half_open_recovery(self):
        """半开→探针成功→恢复 closed。"""
        config = BreakerConfig(
            min_requests=10, error_rate_threshold=0.5,
            open_duration=0.01,  # 快速进入半开
            half_open_probes=2,
        )
        b = CircuitBreaker("test", config=config)

        # 触发熔断
        for i in range(20):
            try:
                await b.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except (ValueError, CircuitOpenError):
                pass
        assert b._state == BreakerState.OPEN

        # 等待 open_duration → 半开
        await asyncio.sleep(0.02)

        # 探针成功
        await b.call(lambda: "ok")
        await b.call(lambda: "ok")
        assert b._state == BreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_fail_back_to_open(self):
        """半开探针失败→回到 open。"""
        config = BreakerConfig(
            min_requests=10, error_rate_threshold=0.5,
            open_duration=0.01, half_open_probes=3,
        )
        b = CircuitBreaker("test", config=config)

        for i in range(20):
            try:
                await b.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except (ValueError, CircuitOpenError):
                pass
        assert b._state == BreakerState.OPEN

        await asyncio.sleep(0.02)
        # 第一个探针就失败
        try:
            await b.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except (ValueError, CircuitOpenError):
            pass
        assert b._state == BreakerState.OPEN

    def test_get_breaker_singleton(self):
        b1 = get_breaker("singleton")
        b2 = get_breaker("singleton")
        assert b1 is b2

    def test_get_breaker_different_names(self):
        b1 = get_breaker("a")
        b2 = get_breaker("b")
        assert b1 is not b2

    @pytest.mark.asyncio
    async def test_redis_sync(self):
        """测试 Redis Hash 同步（mock）。"""
        mock_r = AsyncMock()
        mock_r.hgetall.return_value = {}
        mock_r.hset.return_value = 1

        b = CircuitBreaker("test")
        with patch.object(b, "_get_redis", return_value=mock_r):
            await b._sync_from_redis()
            mock_r.hgetall.assert_called_once()


# ============================================================
# 6. trace.py
# ============================================================
class TestTrace:
    def test_generate_trace_id(self):
        tid = generate_trace_id()
        assert len(tid) == 16
        assert tid != generate_trace_id()  # 每次不同

    def test_trace_id_var(self):
        import contextvars
        tid = generate_trace_id()
        token = trace_id_var.set(tid)
        assert get_trace_id() == tid
        trace_id_var.reset(token)

    def test_start_span(self):
        with start_span("test_span"):
            span_id = span_id_var.get("")
            assert span_id != ""
            assert len(span_id) == 8

    def test_start_span_restores_parent(self):
        parent = "parent123"
        span_id_var.set(parent)
        with start_span("child"):
            assert span_id_var.get("") != parent
        assert span_id_var.get("") == parent


# ============================================================
# 7. queue.py
# ============================================================
class TestQueue:
    @pytest.fixture
    def mock_redis(self):
        store = {}
        lists = {}

        async def _rpush(key, value):
            if key not in lists:
                lists[key] = []
            lists[key].append(value)
            return len(lists[key])

        async def _blpop(key, timeout=0):
            await asyncio.sleep(0)
            if key in lists and lists[key]:
                return (key, lists[key].pop(0))
            return None

        async def _llen(key):
            return len(lists.get(key, []))

        r = AsyncMock()
        r.rpush = AsyncMock(side_effect=_rpush)
        r.blpop = AsyncMock(side_effect=_blpop)
        r.llen = AsyncMock(side_effect=_llen)
        return r, lists

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, mock_redis):
        r, lists = mock_redis
        q = TaskQueue("test")
        with patch.object(q, "_get_redis", return_value=r):
            await q.enqueue({"task": "hello"})
            result = await q.dequeue(timeout=1)
            assert result == {"task": "hello"}

    @pytest.mark.asyncio
    async def test_dequeue_empty(self, mock_redis):
        r, lists = mock_redis
        q = TaskQueue("test")
        with patch.object(q, "_get_redis", return_value=r):
            result = await q.dequeue(timeout=0.1)
            assert result is None

    @pytest.mark.asyncio
    async def test_queue_length(self, mock_redis):
        r, lists = mock_redis
        q = TaskQueue("test")
        with patch.object(q, "_get_redis", return_value=r):
            await q.enqueue({"a": 1})
            await q.enqueue({"b": 2})
            length = await q.length()
            assert length == 2

    @pytest.mark.asyncio
    async def test_redis_down_fallback(self):
        """Redis 不可用 → 本地内存队列降级。"""
        q = TaskQueue("test")
        with patch.object(q, "_get_redis", return_value=None):
            await q.enqueue({"task": "local"})
            result = await q.dequeue(timeout=0.1)
            assert result == {"task": "local"}

    @pytest.mark.asyncio
    async def test_convenience_functions(self, mock_redis):
        r, lists = mock_redis
        q = TaskQueue("test")
        with patch.object(q, "_get_redis", return_value=r):
            # 先注册
            from app.core import queue as qm
            qm._queues["test"] = q
            await enqueue("test", {"msg": "hello"})
            result = await dequeue("test", timeout=1)
            assert result == {"msg": "hello"}


# ============================================================
# 8. crud_mixin.py
# ============================================================
class TestCrudMixin:
    """测试 CrudMixin 的配置和属性（CRUD 操作需 MySQL 集成测试覆盖，task11-14）。"""

    def test_table_name(self):
        from app.core.crud_mixin import CrudMixin

        class TestRepo(CrudMixin):
            table = "test_table"

        repo = TestRepo()
        assert repo.table == "test_table"
        assert repo.pk == "id"
        assert repo.soft_delete is True

    def test_custom_pk(self):
        from app.core.crud_mixin import CrudMixin

        class TestRepo(CrudMixin):
            table = "test_table"
            pk = "uuid"

        repo = TestRepo()
        assert repo.pk == "uuid"

    def test_soft_delete_disabled(self):
        from app.core.crud_mixin import CrudMixin

        class TestRepo(CrudMixin):
            table = "test_table"
            soft_delete = False

        repo = TestRepo()
        assert repo.soft_delete is False


# ============================================================
# 9. Redis 宕机降级集成测试
# ============================================================
class TestRedisDownDegradation:
    """Redis 不可用时，所有组件不抛 500。"""

    @pytest.mark.asyncio
    async def test_cache_down_no_500(self):
        async def loader():
            return "db_data"
        with patch("app.database.get_redis", side_effect=RuntimeError):
            result = await get_or_load("any:key", loader)
            assert result == "db_data"  # 降级直通

    @pytest.mark.asyncio
    async def test_lock_down_no_500(self):
        with patch("app.database.get_redis", side_effect=RuntimeError):
            lock = RedisLock("test")
            ok = await lock.acquire()
            assert ok is True  # 降级放行

    @pytest.mark.asyncio
    async def test_idempotency_down_no_500(self):
        idem = Idempotency()
        with patch.object(idem, "_get_redis", return_value=None):
            result = await idem.check("test")
            assert result is None  # 降级放行
            ok = await idem.save("test", {"status": "ok"})
            assert ok is True

    @pytest.mark.asyncio
    async def test_queue_down_no_500(self):
        q = TaskQueue("test")
        with patch.object(q, "_get_redis", return_value=None):
            await q.enqueue({"task": "local"})
            result = await q.dequeue(timeout=0.1)
            assert result == {"task": "local"}


# ============================================================
# 10. 并发场景测试
# ============================================================
class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_breaker(self):
        """并发 100 请求熔断器，状态一致。"""
        config = BreakerConfig(min_requests=50, error_rate_threshold=0.5)
        b = CircuitBreaker("concurrent", config=config)

        async def ok_call():
            return "ok"

        async def err_call():
            raise ValueError("fail")

        async def request():
            try:
                await b.call(ok_call)
            except CircuitOpenError:
                pass
            except ValueError:
                pass

        tasks = [request() for _ in range(100)]
        await asyncio.gather(*tasks)
        # 状态应该稳定（closed 或 open，不能崩溃）
        assert b._state in (BreakerState.CLOSED, BreakerState.OPEN)

    @pytest.mark.asyncio
    async def test_concurrent_lock(self):
        """并发获取同一锁，仅一个成功。"""
        mock_r = AsyncMock()
        # 只有第一次 SET NX 成功
        set_results = [True] + [False] * 99
        mock_r.set.side_effect = set_results
        mock_r.eval.return_value = 1

        acquired = []
        async def try_lock():
            with patch("app.database.get_redis", return_value=mock_r):
                lock = RedisLock("concurrent_lock")
                ok = await lock.acquire()
                acquired.append(ok)

        await asyncio.gather(*[try_lock() for _ in range(100)])
        assert sum(acquired) == 1  # 仅一个成功