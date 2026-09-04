"""
Redis 分布式锁（Phase 重构：task09 core/ 框架层）

面试考点：
- SETNX + Lua 释放：为什么用 Lua？保证"判断归属 + 删除"的原子性，避免误删他人锁
- 锁超时：防止死锁（进程崩溃后锁自动释放）
- 可重入：本项目不需要（单次调用锁），简化实现

用法：
  from app.core.lock import RedisLock
  async with RedisLock("order:create:123", timeout=10):
      await create_order()
"""
from __future__ import annotations

import uuid
from typing import Any

from loguru import logger


class RedisLock:
    """Redis 分布式锁（SETNX + Lua 释放）。"""

    def __init__(self, name: str, timeout: float = 10.0):
        self.name = f"lock:{name}"
        self.timeout = int(timeout)
        self._token = uuid.uuid4().hex  # 唯一 token，防误删

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args: Any):
        await self.release()

    async def acquire(self) -> bool:
        """获取锁。返回 True=成功，False=超时。"""
        try:
            from app.database import get_redis
            r = get_redis()
        except RuntimeError:
            logger.warning("[Lock] Redis 不可用，跳过锁")
            return True  # 降级：无锁执行

        acquired = await r.set(self.name, self._token, nx=True, ex=self.timeout)
        if acquired:
            logger.debug(f"[Lock] 获取锁: {self.name}")
        return bool(acquired)

    async def release(self):
        """释放锁（Lua 原子操作：校验 token → 删除）。"""
        try:
            from app.database import get_redis
            r = get_redis()
        except RuntimeError:
            return

        lua_script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        await r.eval(lua_script, 1, self.name, self._token)