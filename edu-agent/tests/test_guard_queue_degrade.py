# -*- coding: utf-8 -*-
"""R1-③ 环境依赖项离线单测：Redis 队列削峰逻辑（内存后端 + Redis 异常降级）。

无需真实 Redis / 压测流量即可验证削峰队列正确性：
  1) 内存后端 enqueue/await_queue FIFO 取回一致；
  2) await_queue 超时返回 None（友好提示）；
  3) Redis lpush/blpop 抛异常 → 自动降级内存队列，不抛错、不丢任务。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.ai.guard import ConcurrencyGuard


@pytest.fixture
def mem_guard():
    # redis=None → 内存后端（无外部依赖
    return ConcurrencyGuard(global_limit=4, user_max=2, queue_timeout=1.0, queue_key="test:queue", redis=None)


# 1. 内存后端 FIFO 取回一致
@pytest.mark.asyncio
async def test_mem_queue_fifo_roundtrip(mem_guard):
    await mem_guard.enqueue({"q": "hello", "n": 1})
    await mem_guard.enqueue({"q": "world", "n": 2})
    assert await mem_guard.await_queue() == {"q": "hello", "n": 1}
    assert await mem_guard.await_queue() == {"q": "world", "n": 2}


# 2. await_queue 无任务 + 超时 → None（友好提示，不抛错）
@pytest.mark.asyncio
async def test_mem_queue_await_timeout_returns_none(mem_guard):
    assert await mem_guard.await_queue(timeout=0.05) is None


# 3. Redis mock：lpush 抛异常 → 降级内存队列，任务不丢
class _FlakyRedis:
    """模拟 Redis 全面的网络异常。"""

    async def lpush(self, *a, **kw):  # noqa: N802
        raise ConnectionError("redis down")

    async def blpop(self, *a, **kw):  # noqa: N802
        raise ConnectionError("redis down")


@pytest.mark.asyncio
async def test_redis_flaky_degrades_to_mem():
    g = ConcurrencyGuard(
        global_limit=4, user_max=2, queue_timeout=1.0,
        queue_key="test:flaky", redis=_FlakyRedis(),
    )
    # enqueue 时 Redis 失败 → 落内存
    await g.enqueue({"q": "x", "n": 1})
    # await_queue 时 Redis 失败 → 落内存取回
    assert await g.await_queue() == {"q": "x", "n": 1}


# 4. JSON payload 可序列化（enqueue 内部 json.dumps 不因非串行对象抛错泄漏）
@pytest.mark.asyncio
async def test_enqueue_serializes_exception_payload(mem_guard):
    class _O:
        def __str__(self):  # default=str 兜底
            return "obj"

    await mem_guard.enqueue({"q": "keep", "meta": _O()})  # 不抛错
    got = await mem_guard.await_queue()
    assert got["q"] == "keep"
    assert "meta" in got, "default=str 兜底应保留 key（值为字符串化）"