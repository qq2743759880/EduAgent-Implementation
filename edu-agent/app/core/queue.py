"""
Redis List 任务队列（Phase 重构：task09 core/ 框架层）

面试考点：
- 为什么用 Redis List 而不是 RabbitMQ/Kafka？单体场景 Redis 已部署，无需额外 MQ 运维
- BLPOP vs BRPOP：BLPOP 从左弹出（FIFO），BRPOP 从右弹出（LIFO/栈）
- 为什么用 RPUSH+BLPOP？RPUSH 从右侧推入，BLPOP 从左侧弹出，实现 FIFO 队列
- 降级：Redis 不可用时本地内存队列兜底

用法：
  from app.core.queue import TaskQueue, enqueue, dequeue
  await enqueue("email", {"to": "a@b.com", "body": "..."})
  task = await dequeue("email", timeout=5)
"""
from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any

from loguru import logger


# 本地内存队列（Redis 不可用时降级）
_local_queues: dict[str, deque] = {}


class TaskQueue:
    """Redis List 任务队列（BLPOP 消费）。"""

    def __init__(self, name: str):
        self.name = f"queue:{name}"
        self._local = deque()

    async def _get_redis(self):
        try:
            from app.database import get_redis
            return get_redis()
        except RuntimeError:
            return None

    async def enqueue(self, task: dict[str, Any]) -> bool:
        """
        入队（RPUSH）。

        Returns:
            True: 入队成功
        """
        r = await self._get_redis()
        payload = json.dumps(task, ensure_ascii=False, default=str)

        if r is None:
            # 降级：本地内存队列
            logger.warning(f"[Queue] Redis 不可用，降级到本地队列: {self.name}")
            if self.name not in _local_queues:
                _local_queues[self.name] = deque()
            _local_queues[self.name].append(payload)
            return True

        await r.rpush(self.name, payload)
        return True

    async def dequeue(self, timeout: int = 5) -> dict[str, Any] | None:
        """
        出队（BLPOP，阻塞等待）。

        Args:
            timeout: 阻塞等待超时（秒）

        Returns:
            task dict 或 None（超时）
        """
        r = await self._get_redis()

        if r is None:
            # 降级：本地内存队列
            if self.name in _local_queues and _local_queues[self.name]:
                payload = _local_queues[self.name].popleft()
                return json.loads(payload)
            return None

        result = await r.blpop(self.name, timeout=timeout)
        if result is None:
            return None

        _, payload = result
        return json.loads(payload)

    async def length(self) -> int:
        """获取队列长度。"""
        r = await self._get_redis()
        if r is None:
            return len(_local_queues.get(self.name, deque()))
        return await r.llen(self.name)


# 全局队列注册表
_queues: dict[str, TaskQueue] = {}


def get_queue(name: str) -> TaskQueue:
    """获取或创建队列。"""
    if name not in _queues:
        _queues[name] = TaskQueue(name)
    return _queues[name]


async def enqueue(queue_name: str, task: dict[str, Any]) -> bool:
    """便捷入队。"""
    return await get_queue(queue_name).enqueue(task)


async def dequeue(queue_name: str, timeout: int = 5) -> dict[str, Any] | None:
    """便捷出队。"""
    return await get_queue(queue_name).dequeue(timeout)