"""
Redis 缓存分层封装（Phase 重构：task09 core/ 框架层）

防护策略（三防）：
- 穿透（查不存在数据直达 DB）：空结果缓存 30s（"null" 哨兵值）
- 击穿（热点 key 过期瞬间并发重建）：SETNX 互斥重建 + 逻辑过期兜底
- 雪崩（大量 key 同时过期）：TTL 随机抖动 ±10%

面试考点：
- 为什么缓存穿透用空值缓存而不是布隆过滤器？布隆过滤器需要预先知道所有可能 key，动态 key 场景不适用
- SETNX 互斥锁 vs 逻辑过期：SETNX 简单可靠，逻辑过期需要额外维护过期时间
- TTL 抖动为什么 ±10%？统计上均匀分布可避免雪崩，±10% 足够且不浪费内存

用法：
  from app.core.cache import get_or_load
  data = await get_or_load("series:detail:1", lambda: fetch_from_db(1), ttl=300)
"""
from __future__ import annotations

import asyncio
import random
from uuid import uuid4
from typing import Any, Awaitable, Callable

from loguru import logger

from app.config import settings
from app.core.db_resilience import DependencyUnavailableError, redis_run  # task-P1C Redis 断连熔断
from app.monitoring.metrics import record_degraded as _record_degraded


async def get_or_load(
    key: str,
    loader: Callable[[], Awaitable[Any]],
    *,
    ttl: int | None = None,
    null_ttl: int = 30,
    mutex_timeout: int = 10,
) -> Any:
    """
    缓存读取：命中返回缓存值，未命中走 loader 重建。

    三防策略：
    1. 穿透防护：loader 返回 None 时写入空值哨兵（TTL 30s）
    2. 击穿防护：SETNX 互斥锁（同一 key 同时只有 1 个 loader 重建）
    3. 雪崩防护：TTL 随机 ±10% 抖动

    Args:
        key: 缓存 key
        loader: 数据加载函数（async callable）
        ttl: 缓存过期时间（秒），None 则用默认 300s
        null_ttl: 空结果缓存时间（秒）
        mutex_timeout: 互斥锁超时（秒）

    Returns:
        loader 返回的数据，或缓存的旧值（逻辑过期兜底）
    """
    if ttl is None:
        ttl = 300

    # 抖动 TTL
    actual_ttl = int(ttl * (1 + random.uniform(-0.1, 0.1)))

    try:
        from app.database import get_redis
        r = get_redis()
    except RuntimeError:
        # Redis 未配置 → 直通 DB（§6.4：缓存穿透直达 DB，功能可用、性能下降）
        _record_degraded("redis", "cache_unavailable:no_client")
        return await loader()

    # 运行期 Redis 故障（连接中断/超时） → 直通 DB，避免缓存故障引发 500（R3 加固）
    # task-P1C：经 redis_run 熔断保护——连续 N 次失败 → OPEN → 后续毫秒级快速失败直通 DB，
    # 不再傻等 socket 超时（task39 实测 Redis 断连让课程/班次详情等长尾阻塞）。
    try:
        return await redis_run(
            f"cache:{key.split(':')[0]}",
            lambda: _read_or_rebuild(r, key, loader, ttl, actual_ttl, null_ttl, mutex_timeout),
        )
    except DependencyUnavailableError:
        # 熔断中：毫秒级直通 DB（不触达 Redis），避免长尾阻塞
        return await loader()
    except Exception:
        logger.warning(f"[Cache] Redis 读写异常，直通 DB（缓存降级）: {key}")
        # task39 GWT②：Redis 断连的**主要**可观测面就在这里（课程详情/班次详情均走本函数）
        _record_degraded("redis", "cache_readwrite_failed")
        return await loader()


async def _read_or_rebuild(r, key, loader, ttl, actual_ttl, null_ttl, mutex_timeout):
    # 1. 尝试读缓存
    cached = await r.get(key)
    if cached is not None:
        if cached == "__NULL__":
            return None
        import json
        try:
            return json.loads(cached)
        except Exception:
            return cached

    # 2. 缓存未命中 → 加互斥锁后重建
    mutex_key = f"{key}:mutex"
    # 唯一随机 token 作为锁值：释放时用 Lua 比对，超锁后他人抢锁时旧持有者不会误删他人锁（task39 批判③）
    mutex_token = uuid4().hex
    lock_acquired = await r.set(mutex_key, mutex_token, nx=True, ex=mutex_timeout)

    if lock_acquired:
        # 抢到锁 → 执行 loader 重建
        try:
            data = await loader()
            if data is None:
                # 空结果缓存（穿透防护）
                await r.set(key, "__NULL__", ex=null_ttl)
            else:
                import json
                await r.set(key, json.dumps(data, ensure_ascii=False, default=str), ex=actual_ttl)
            return data
        finally:
            # Lua 释放锁（比对唯一 token，防止误删他人已重获的锁）
            await r.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                1, mutex_key, mutex_token,
            )
    else:
        # 没抢到锁 → 短轮询等待重建完成
        for _ in range(3):
            await asyncio.sleep(0.1)
            cached = await r.get(key)
            if cached is not None:
                if cached == "__NULL__":
                    return None
                import json
                try:
                    return json.loads(cached)
                except Exception:
                    return cached

        # 轮询超时 → 直通 DB（降级）
        logger.warning(f"[Cache] 缓存重建等待超时，直通 DB: {key}")
        return await loader()


async def invalidate(*keys: str) -> None:
    """精确删除缓存（写操作后调用）。"""
    try:
        from app.database import get_redis
        r = get_redis()
        if keys:
            await r.delete(*keys)
    except Exception:
        # Redis 故障时删除失败 → 容忍（key 将自然过期），不阻断写链路
        pass