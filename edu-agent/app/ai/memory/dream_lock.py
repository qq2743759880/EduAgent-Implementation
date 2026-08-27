"""Dream 巩固分布式锁（task-M1 P3，对齐 Claude AutoDream mtime 锁）。

- 优先 Redis `SET key 1 NX EX {ttl}` 窗口锁：多实例仅一个能巩固同一用户。
- Redis 不可达 → 降级进程内锁（基于单调时钟），并标注 degraded_reason。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger


class DreamLock:
    def __init__(self, *, ttl_s: int = 600) -> None:
        self.ttl_s = int(ttl_s)
        self._local: dict[int, float] = {}
        self._local_lock = asyncio.Lock()

    async def acquire(self, user_id: int, *, redis: Any = None) -> bool:
        key = f"memory:dream:{int(user_id)}"
        try:
            if redis is None:
                from app.database import get_redis
                redis = get_redis()
            res = await redis.set(key, "1", nx=True, ex=self.ttl_s)
            return res is not None
        except Exception as exc:
            logger.warning(f"[Dream] Redis 锁不可用，降级进程内锁: {type(exc).__name__}: {exc}")
            return await self._acquire_local(int(user_id))

    async def release(self, user_id: int, *, redis: Any = None) -> None:
        key = f"memory:dream:{int(user_id)}"
        try:
            if redis is None:
                from app.database import get_redis
                redis = get_redis()
            await redis.delete(key)
        except Exception:
            self._local.pop(int(user_id), None)

    async def _acquire_local(self, user_id: int) -> bool:
        async with self._local_lock:
            now = time.monotonic()
            exp = self._local.get(user_id, 0.0)
            if exp > now:
                return False
            self._local[user_id] = now + self.ttl_s
            return True
