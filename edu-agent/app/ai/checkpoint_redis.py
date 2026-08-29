# -*- coding: utf-8 -*-
"""task24：基于原生 Redis（无需 RediSearch/RedisJSON 模块）的 durable execution checkpointer。

背景：LangGraph 自带的 AsyncRedisSaver 依赖 redisvl + RediSearch（FT.INDEX/FT.INFO）来创建
checkpoint 向量索引。本环境 Redis(6379) 为原生 Redis，无该模块。为满足 GWT②
「中途 kill 后同 thread_id 恢复、不重复已完成节点」的 Redis durable execution，这里
复用 InMemorySaver 的全部 blob/write 语义（channel delta、pending writes、版本号），
仅在其上叠加「每线程状态快照 → 持久化到 Redis」：a put/put_writes 后把该线程的
storage/writes/blobs 整体 pickle 写回 Redis；aget_tuple/alist 前先从 Redis 加载该线程
状态到内存再代理父类。进程 kill 后，新的 saver 实例以同一 Redis 重建该线程内存状态，
aget_tuple 返回最近 checkpoint，LangGraph 从该点续跑，不在内存中重复已完成节点。

键设计：{prefix}:{thread_id} => pickle(storage[thread] + 该线程 writes + 该线程 blobs)
用法：saver = PlainRedisSaver(redis_url=settings.REDIS_URL)  → compile(checkpointer=saver)。

task39 GWT④ 并发加固（并发 100 resume 无丢失/错乱）：
    原实现存在两处竞态，在「100 并发 resume」下会真实丢数据：
      R1. ``_client()`` 无锁：N 个协程首次并发进入 ``await self.aclose()`` 后各自
          ``from_url`` 建连，只有最后一个被 ``self._redis`` 记住，其余连接泄漏
          （服务端 maxclients 打满 → 后续 resume 全部失败）。
      R2. ``_persist_thread()`` 是「读快照 → await r.set」的读-改-写序列，且
          ``_ensure_loaded()`` 是「await r.get → 覆盖内存」。两者之间无互斥：
          同 thread_id 的两个并发 aput 会把各自的快照交错写入 Redis，
          后落盘的可能是**旧快照** → checkpoint 丢失；_ensure_loaded 覆盖内存时
          也会把更新的内存状态回退成旧值。
    修复：客户端初始化加全局锁；持久化/回填加「按 thread_id 粒度的锁」，
          把「super().aput() + 落盘」整段串行化，保证同一线程的写顺序与快照一致。
          锁按 thread_id 分片，不同线程之间仍完全并发（不影响吞吐）。
"""
from __future__ import annotations

import asyncio
import pickle
import uuid
from typing import Any

from loguru import logger

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.base import CheckpointTuple
from langchain_core.runnables import RunnableConfig


class PlainRedisSaver(InMemorySaver):
    """内存语义 + Redis 持久化的 checkpoint saver（原生 Redis，不依赖 search 模块）。

    继承 InMemorySaver：agetch/get_next_version/list/put/put_writes 等全部逻辑复用，
    只重写 async 入口，在写路径落盘、读路径回填。
    """

    # thread_id 锁表上限（防长跑内存无界增长；清表只影响锁对象，不丢已持久化数据）
    _MAX_TRACKED_LOCKS = 4096

    def __init__(
        self,
        redis_url: str,
        *,
        prefix: str = "edu:ckpt",
        ttl: int | None = 3600,
        serde: Any = None,
    ) -> None:
        super().__init__(serde=serde)
        self._redis_url = redis_url
        self._prefix = prefix
        self._ttl = ttl
        self._redis: Any = None
        self._loop: Any = None
        self._loaded_threads: set[str] = set()
        # task39 GWT④：并发锁（延迟创建，绑定事件循环）
        self._conn_lock: asyncio.Lock | None = None
        self._locks_guard: asyncio.Lock | None = None
        self._thread_locks: dict[str, asyncio.Lock] = {}
        # 锁设施自己的 loop 标记——必须与 self._loop 分开：
        # self._loop 由 _client() 在「首次真正建连后」才赋值，若复用它做判据，
        # 首轮并发期间 self._loop 仍为 None → 每次都判定「跨 loop」→ 反复重置锁表
        # → 各协程拿到不同的 Lock 对象 → 互斥彻底失效（实测同线程 100 并发写会丢最后一步）。
        self._locks_loop: Any = None

    # ---- 锁设施（GWT④）：随事件循环重建，避免跨 loop 使用 asyncio.Lock 报错 ----
    def _locks_for_loop(self) -> tuple[asyncio.Lock, asyncio.Lock]:
        """返回 (连接锁, 线程锁表锁)。事件循环切换时重建，避免跨 loop 复用锁。"""
        loop = asyncio.get_running_loop()
        if self._locks_loop is not loop:
            self._locks_loop = loop
            self._conn_lock = asyncio.Lock()
            self._locks_guard = asyncio.Lock()
            self._thread_locks = {}
        return self._conn_lock, self._locks_guard  # type: ignore[return-value]

    async def _thread_lock(self, thread_id: str) -> asyncio.Lock:
        """取 thread_id 维度的锁（不同线程互不阻塞，同线程串行化读-改-写）。"""
        _, guard = self._locks_for_loop()
        lk = self._thread_locks.get(thread_id)
        if lk is not None:
            return lk
        async with guard:
            lk = self._thread_locks.get(thread_id)
            if lk is None:
                # 锁表上限保护：长时间运行下 thread_id 无限增长会撑爆内存。
                # 锁只在极短的读-改-写期间持有，清表不会丢失已持久化的数据。
                if len(self._thread_locks) >= self._MAX_TRACKED_LOCKS:
                    self._thread_locks.clear()
                lk = asyncio.Lock()
                self._thread_locks[thread_id] = lk
            return lk

    # ---- 客户端懒初始化（async 环境） ----
    async def _client(self) -> Any:
        loop = asyncio.get_running_loop()
        if self._loop is loop and self._redis is not None:
            return self._redis
        conn_lock, _ = self._locks_for_loop()
        async with conn_lock:
            # 双重检查：拿到锁后可能已被其它协程建好
            loop = asyncio.get_running_loop()
            if self._loop is loop and self._redis is not None:
                return self._redis
            if self._loop is not None and self._loop is not loop:
                # 跨事件循环（测试注入新 loop）重连
                await self.aclose()
            import redis.asyncio as aioredis

            self._redis = aioredis.Redis.from_url(self._redis_url)
            self._loop = loop
            return self._redis

    def _key(self, thread_id: str) -> str:
        return f"{self._prefix}:{thread_id}"

    async def _persist_thread(self, thread_id: str) -> None:
        """把该线程的 storage/writes/blobs 快照持久化到 Redis。"""
        try:
            storage = dict(self.storage.get(thread_id) or {}) if hasattr(self, "storage") and thread_id in self.storage else {}
            writes = {k: v for k, v in dict(self.writes).items() if k[0] == thread_id}
            blobs = {k: v for k, v in dict(self.blobs).items() if k[0] == thread_id}
            payload = pickle.dumps({"storage": storage, "writes": writes, "blobs": blobs})
            r = await self._client()
            await r.set(self._key(thread_id), payload, ex=self._ttl)
        except Exception as exc:  # 持久化失败不阻塞执行（内存仍可用）
            logger.warning(f"[PlainRedisSaver] persist thread {thread_id} 失败: {type(exc).__name__}: {exc}")

    async def _ensure_loaded(self, thread_id: str) -> None:
        """aget_tuple 前把该线程状态从 Redis 回填到内存（首次或进程重启后）。"""
        if thread_id in self._loaded_threads:
            return
        try:
            r = await self._client()
            raw = await r.get(self._key(thread_id))
            if raw is None:
                self._loaded_threads.add(thread_id)
                return
            data = pickle.loads(raw)
            self.storage[thread_id].update(data.get("storage", {}))
            for k, v in data.get("writes", {}).items():
                self.writes[k] = v
            self.blobs.update(data.get("blobs", {}))
        except Exception as exc:
            logger.warning(f"[PlainRedisSaver] load thread {thread_id} 失败: {type(exc).__name__}: {exc}")
        finally:
            self._loaded_threads.add(thread_id)

    # ---- 重写 async 入口（task39 GWT④：同 thread_id 串行化读-改-写） ----
    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        async with await self._thread_lock(thread_id):
            await self._ensure_loaded(thread_id)
            return await super().aget_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Any:
        if config is not None:
            thread_id = config["configurable"].get("thread_id")
            if thread_id:
                async with await self._thread_lock(thread_id):
                    await self._ensure_loaded(thread_id)
        for item in super().list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(self, config, checkpoint, metadata, new_versions):
        thread_id = config["configurable"]["thread_id"]
        async with await self._thread_lock(thread_id):
            # 「写内存 + 落盘」整段持锁：保证落盘快照与内存状态一致，
            # 且同线程的多次 aput 不会交错覆盖出旧快照（GWT④ R2）。
            ret = await super().aput(config, checkpoint, metadata, new_versions)
            self._loaded_threads.add(thread_id)
            await self._persist_thread(thread_id)
            return ret

    async def aput_writes(self, config, writes, task_id, task_path=""):
        thread_id = config["configurable"]["thread_id"]
        async with await self._thread_lock(thread_id):
            await super().aput_writes(config, writes, task_id, task_path)
            self._loaded_threads.add(thread_id)
            await self._persist_thread(thread_id)

    async def asetup(self) -> None:
        """对齐 AsyncRedisSaver 的 asetup 契约（连接探测）。无 search 索引可建，仅 ping。"""
        r = await self._client()
        await r.ping()

    async def aclose(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
            self._loop = None

    async def __aenter__(self) -> PlainRedisSaver:
        await self.asetup()
        return self

    async def __aexit__(self, *exc_info: Any) -> bool | None:
        await self.aclose()
        return None