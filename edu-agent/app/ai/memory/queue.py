"""三层记忆 - 异步写队列 + 遗忘任务（task25 R7）。

- **异步隔离（GWT①④）**：`enqueue_candidate` 只入队即返回（LPUSH→Redis，或 in-memory asyncio.Queue），
  绝不阻塞/抛错到应答链路；后台 worker 用阻塞 BRPOP 取单 → `store.write`（失败按 retries 上限重入队，
  超限则丢弃记日志）→ 写入后触发 `prune_if_over`（容量卫兵）。
- **broker 双实现**：Redis list（生产，复用 app.database.get_redis）+ 内存 asyncio.Queue（降级/测试）。
- worker 生命周期 `start_consumer` / `stop_consumer`；由应用 lifespan 启动（service 门面）。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from app.ai.memory.schemas import MemoryCandidate


class MemoryWriteQueue:
    """异步记忆写队列。enqueue 恒快速返回，worker 后台消费组成 `store.write` 链路。"""

    def __init__(self, store: Any, *, max_retry: int | None = None, queue_key: str | None = None) -> None:
        from app.config import settings

        self.store = store
        self._max_retry = int(max_retry if max_retry is not None else settings.MEMORY_QUEUE_MAX_RETRY)
        self._queue_key = queue_key or str(settings.MEMORY_QUEUE_KEY)
        self._memq: asyncio.Queue = asyncio.Queue()
        self._consumer: asyncio.Task | None = None
        self._running = False

    # --- 入队（异步隔离核心，绝不向调用方抛错） ---
    async def enqueue_candidate(self, user_id: int, candidate: MemoryCandidate) -> bool:
        payload = {
            "user_id": int(user_id),
            "content": (candidate.content or "")[:2000],
            "memory_type": candidate.memory_type[:32],
            "topic": (candidate.topic or "general")[:64],
            "importance": max(1, min(5, int(candidate.importance or 4))),
            "retries": 0,
        }
        try:
            from app.database import get_redis

            r = get_redis()
            await r.lpush(self._queue_key, json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as exc:
            # Redis 不可用 → 入内存队列（测试/降级路径成环亦有消费者吞掉）
            try:
                self._memq.put_nowait(payload)
                return True
            except Exception:
                logger.warning(f"[Memory:queue] 入队失败（丢弃一条，不阻塞应答）：{exc}")
                return False

    # --- 消费（阻塞取单 → 写记忆 → 容量卫兵） ---
    async def _process(self, payload: dict[str, Any]) -> bool:
        user_id = int(payload["user_id"])
        try:
            await self.store.write(
                user_id=user_id,
                content=payload["content"],
                memory_type=payload["memory_type"],
                topic=payload["topic"],
                importance=int(payload["importance"]),
            )
            # 写入后触发容量卫兵（遗忘淘汰，GWT③）
            try:
                await self.store.prune_if_over(user_id)
            except Exception:
                pass
            return True
        except Exception as exc:
            retries = int(payload.get("retries", 0)) + 1
            if retries <= self._max_retry:
                payload["retries"] = retries
                # 失败重入队（Redis index 0 队尾 → 稍后重试；内存队列追加）
                store_failed_payload: dict[str, Any] = dict(payload)
                try:
                    from app.database import get_redis

                    r = get_redis()
                    await r.rpush(self._queue_key, json.dumps(store_failed_payload, ensure_ascii=False))
                except Exception:
                    self._memq.put_nowait(store_failed_payload)
                logger.warning(f"[Memory:queue] 写记忆失败（将重试 {retries}/{self._max_retry}）: {exc}")
            else:
                logger.error(f"[Memory:queue] 写记忆失败已达上限，丢弃：user={user_id} exc={exc}")
            return False

    async def _consume_loop(self) -> None:
        from app.database import get_redis

        while self._running:
            item: dict[str, Any] | None = None
            came_from_redis = False
            # 1) Redis 优先
            try:
                r = get_redis()
                raw = await asyncio.wait_for(
                    r.brpop(self._queue_key, timeout=2), timeout=3
                )
                if raw is not None:
                    item = json.loads(raw[1])
                    came_from_redis = True
            except asyncio.TimeoutError:
                pass  # 轮询间隔无任务，继续
            except Exception:
                pass  # Redis 故障 → 走内存队列兜底

            # 2) 内存队列兜底（含 Redis 降级时写入的任务）
            if item is None:
                try:
                    mem_item = self._memq.get_nowait()
                    item = mem_item
                    came_from_redis = False
                except (asyncio.QueueEmpty, Exception):
                    item = None
            if item is None:
                await asyncio.sleep(0.05)  # 空转节流
                continue
            await self._process(item)

    def start_consumer(self) -> None:
        if self._running:
            return
        self._running = True
        self._consumer = asyncio.get_running_loop().create_task(self._consume_loop())

    async def stop_consumer(self) -> None:
        self._running = False
        if self._consumer is not None:
            self._consumer.cancel()
            try:
                await self._consumer
            except Exception:
                pass
            self._consumer = None

    # --- 测试便利 ---
    async def pump_once(self) -> bool:
        """单步消费：从任一 broker 取一条并处理（供单测确定性验证，不启长驻循环）。"""
        item = None
        try:
            from app.database import get_redis

            r = get_redis()
            # brpop 的 timeout 必须是整数秒；wait_for 控制快速返回（最短阻塞）
            raw = await asyncio.wait_for(r.brpop(self._queue_key, timeout=1), timeout=0.3)
            if raw is not None:
                item = json.loads(raw[1])
        except Exception:
            item = None
        if item is None:
            try:
                item = self._memq.get_nowait()
            except Exception:
                return False
        return await self._process(item)