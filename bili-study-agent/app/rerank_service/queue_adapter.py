# -*- coding: utf-8 -*-
"""
task-R1 可选消息队列削峰（默认直连 batcher，可选 Redis list 缓冲峰值）。

设计（对齐 P9「消息队列削峰」）：
- 默认 DirectQueue：进程内 asyncio.Queue 包装，零依赖，等价于 batcher 内部队列。
- RedisQueue（可选，RERANK_QUEUE_REDIS=True 且 redis 可用时启用）：LPUSH/BLPOP 缓冲跨进程峰值；
  redis 不可用时自动降级回 DirectQueue（不 500、不阻塞）。

本模块为「可选削峰」扩展点，不在 AC 强制路径上；ContinuousBatcher 的 max_queue 已提供内存级削峰保护。
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional, Union


class QueueAdapter:
    """队列适配接口：put 入队一个待处理项，get 阻塞取出。"""

    async def put(self, item: Any) -> None:  # pragma: no cover - 接口
        raise NotImplementedError

    async def get(self) -> Any:  # pragma: no cover - 接口
        raise NotImplementedError


class DirectQueue(QueueAdapter):
    """默认直连队列（内存），行为与 batcher 内部队列一致。"""

    def __init__(self, maxsize: int = 200) -> None:
        self._q: "asyncio.Queue[Any]" = asyncio.Queue(maxsize=maxsize)

    async def put(self, item: Any) -> None:
        await self._q.put(item)

    async def get(self) -> Any:
        return await self._q.get()


class RedisQueue(QueueAdapter):
    """可选 Redis list 削峰（LPUSH 入 / BRPOP 出）。redis 客户端缺失即降级。"""

    def __init__(self, redis_client: Any, key: str = "rerank:queue", timeout: int = 1) -> None:
        self._r = redis_client
        self._key = key
        self._timeout = timeout

    async def put(self, item: Any) -> None:
        # 序列化由调用方保证为 bytes/str；此处直接 LPUSH
        await self._r.lpush(self._key, item)

    async def get(self) -> Any:
        # BRPOP 阻塞弹出
        res = await self._r.brpop(self._key, timeout=self._timeout)
        if res is None:
            return None
        return res[1]


def build_queue_adapter(*, maxsize: int = 200, redis_client: Any = None) -> QueueAdapter:
    """按配置返回队列适配：RERANK_QUEUE_REDIS 且 redis 可用 → RedisQueue，否则 DirectQueue。"""
    from app.config import settings

    if getattr(settings, "RERANK_QUEUE_REDIS", False) and redis_client is not None:
        try:
            return RedisQueue(redis_client)
        except Exception:  # noqa: BLE001 - redis 不可用 → 降级直连
            pass
    return DirectQueue(maxsize=maxsize)
