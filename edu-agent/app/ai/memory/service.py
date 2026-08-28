"""三层记忆 - 门面 service（task25 R7）。

对外统一入口，供 chat service / graph 工具 / 管理接口调用：
- `get_memory_store()` / `get_memory_queue()`：单例
- `start_memory_worker()` / `stop_memory_worker()`：应用 lifespan 启停后台消费
- `enqueue_turn(user_id, text)`：单轮显式触发（R7）→ 规则抽候选 → 异步入队
- `recall_topk(user_id, query, top_k)`：GWT② 向量召回 top-3

线程/协程安全：单例惰性初始化 + asyncio 单事件循环场景（与 FastAPI 一致）。
"""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from app.config import settings
from app.ai.memory.ingest import detect_memories, ingest_turn
from app.ai.memory.queue import MemoryWriteQueue
from app.ai.memory.store import MemoryStore


# ---------------------------------------------------------------------------
# 单例（惰性）
# ---------------------------------------------------------------------------
_store: MemoryStore | None = None
_queue: MemoryWriteQueue | None = None
_init_lock = asyncio.Lock()
_worker_started = False


async def _ensure_instances() -> tuple[MemoryStore, MemoryWriteQueue]:
    """惰性构建 store + queue（幂等，并发安全）。"""
    global _store, _queue
    if _store is not None and _queue is not None:
        return _store, _queue
    async with _init_lock:
        if _store is not None and _queue is not None:
            return _store, _queue
        from app.ai.memory import persistence as _persistence

        persistence = _persistence.build_persistence()
        store = MemoryStore(persistence)
        queue = MemoryWriteQueue(store)
        _store, _queue = store, queue
        return store, queue


async def get_memory_store() -> MemoryStore:
    store, _ = await _ensure_instances()
    return store


async def get_memory_queue() -> MemoryWriteQueue:
    _, queue = await _ensure_instances()
    return queue


def memory_store_sync() -> MemoryStore:
    """同步取 store（图/工具在非 async 上下文构造时用；未构建则建内存降级实例）。"""
    from app.ai.memory import persistence as _p
    from app.ai.memory.event_persistence import MemEventMemoryPersistence
    from app.ai.memory.vector import MemoryVectorStore

    global _store
    if _store is None:
        _store = MemoryStore(MemEventMemoryPersistence(), MemoryVectorStore())
    return _store


# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------
async def start_memory_worker() -> None:
    """后台消费者（配合阻塞 BRPOP + 内存兜底）。由 Tests/主应用 lifespan 调用一次。"""
    global _worker_started, _dream_scheduler_task, _hitl_sweep_task
    if _worker_started:
        return
    queue = await get_memory_queue()
    queue.start_consumer()
    _worker_started = True
    # task-M1：启动 Dream 巩固后台调度（轻量、非阻塞，失败不影响主链路）
    try:
        _dream_scheduler_task = asyncio.create_task(_dream_scheduler_loop())
    except Exception as exc:
        logger.warning(f"[Memory] Dream 调度启动失败（忽略）: {exc}")
    # task-S1-③：启动 HITL 过期 pending 后台扫描（pending 超 TTL → 自动拒绝，AC3 后台路径）
    try:
        if getattr(settings, "HITL_ESCALATION_AUTO", True):
            _hitl_sweep_task = asyncio.create_task(_hitl_sweep_loop())
    except Exception as exc:
        logger.warning(f"[Memory] HITL sweep 调度启动失败（忽略）: {exc}")
    logger.info("[Memory] 记忆写队列消费者已启动")


async def stop_memory_worker() -> None:
    global _worker_started, _dream_scheduler_task, _hitl_sweep_task
    if not _worker_started:
        return
    queue = await get_memory_queue()
    await queue.stop_consumer()
    if _dream_scheduler_task is not None:
        _dream_scheduler_task.cancel()
        _dream_scheduler_task = None
    if _hitl_sweep_task is not None:
        _hitl_sweep_task.cancel()
        _hitl_sweep_task = None
    _worker_started = False
    logger.info("[Memory] 记忆写队列消费者已停止")


# ---------------------------------------------------------------------------
# 对上层接口（chat service / graph 工具调用）
# ---------------------------------------------------------------------------
async def enqueue_turn(user_id: int, text: str, *, threshold: int | None = None) -> int:
    """单轮对话结束的显式触发记忆（R7）：规则抽候选 → 异步入队。

    importance < threshold 的候选会被过滤（默认 settings.MEMORY_IMPORTANCE_THRESHOLD=4），
    满足 GWT①「importance≥4 才写长时记忆」。全程不阻塞/不抛错到应答链路。
    """
    cluster = detect_memories(text)
    queue = await get_memory_queue()
    pushed = 0
    th = int(threshold if threshold is not None else 4)
    for c in cluster:
        if c.importance < th:
            continue
        ok = await queue.enqueue_candidate(int(user_id), c)
        pushed += 1 if ok else 0
    return pushed


async def recall_topk(user_id: int, query: str, top_k: int = 3, *,
                       valid_only: bool = True) -> list[dict[str, Any]]:
    """GWT②：向量召回 top-k 记忆（供 graph 的 memory 子代理/lead plan prompt）。

    valid_only 默认 True：仅返回 `valid_to IS NULL` 有效版本（task-M1 AC2）。"""
    store = await get_memory_store()
    return await store.recall(user_id=int(user_id), query=query, top_k=max(1, top_k), valid_only=valid_only)


async def run_forget(user_id: int) -> dict[str, int]:
    """主动遗忘任务（容量卫兵/管理接口）。"""
    store = await get_memory_store()
    return await store.run_forget(int(user_id))


# ===========================================================================
# task-M1：事件溯源 / Dream 巩固 包装（供 API / 管理接口 / 图工具调用）
# ===========================================================================
_dream_scheduler_task: asyncio.Task | None = None
_hitl_sweep_task: asyncio.Task | None = None


async def _hitl_sweep_loop() -> None:
    """后台轻量调度：周期扫描 HITL 过期 pending → 自动拒绝（task-S1-③，AC3 后台路径）。

    对齐 task-M1 `_dream_scheduler_loop` 模式：非阻塞 SCAN/SQL，失败不影响主链路。
    间隔复用 settings.HITL_ESCALATION_INTERVAL；TTL 复用 settings.HITL_PENDING_TTL_S。
    store 惰性取默认（生产 = MysqlHitlStore），避免顶层耦合 hitl_gate。
    """
    from app.ai.hitl_gate import sweep_expired_pending, _default_hitl_store

    interval = max(60, int(getattr(settings, "HITL_ESCALATION_INTERVAL", 1800)))
    ttl_s = int(getattr(settings, "HITL_PENDING_TTL_S", 600))
    store = _default_hitl_store()
    logger.info(f"[HITL] sweep 后台扫描已启动（interval={interval}s, ttl={ttl_s}s）")
    while True:
        try:
            await asyncio.sleep(interval)
            res = await sweep_expired_pending(store=store, ttl_s=ttl_s)
            rejected = int(res.get("rejected") or 0)
            if rejected:
                logger.info(f"[HITL] sweep 自动拒绝过期 pending {res}")
        except Exception as exc:
            logger.warning(f"[HITL] sweep 循环异常（下次重试）: {exc}")


async def rewind_entity(*, user_id: int, entity_id: int, target_event_id: int) -> dict:
    """回滚某记忆实体到目标版本（ChronoMem 语义：追加 rewind 事件，HEAD 指向目标）。"""
    store = await get_memory_store()
    new_eid = await store.rewind(
        entity_id=int(entity_id), target_event_id=int(target_event_id),
        operator=f"user:{int(user_id)}",
    )
    return {"entity_id": int(entity_id), "new_head_entity_id": int(new_eid)}


async def entity_history(*, entity_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    """分页事件流（审计溯源）。"""
    store = await get_memory_store()
    return await store.history(entity_id=int(entity_id), limit=int(limit), offset=int(offset))


async def trigger_dream(*, user_id: int, **kwargs) -> dict:
    """手动触发 Dream 巩固（受分布式锁保护）。"""
    from app.ai.memory.dream import run_dream

    return await run_dream(int(user_id), **kwargs)


async def compact_user_memory(*, user_id: int, **kwargs) -> dict:
    """手动触发容量压缩（懒合成摘要）。"""
    from app.ai.memory.compactor import compact_user

    store = await get_memory_store()
    return await compact_user(store, int(user_id), **kwargs)


async def _dream_scheduler_loop() -> None:
    """后台轻量调度：扫描会话计数键，达标用户触发 Dream（非阻塞 SCAN，失败不影响主链路）。"""
    scan_interval = max(300, int(getattr(settings, "DREAM_MIN_AGE_HOURS", 24) * 60))
    prefix = "memory:session_count:"
    while True:
        try:
            await asyncio.sleep(scan_interval)
            from app.ai.memory.dream import run_dream
            from app.database import get_redis

            r = get_redis()
            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor, match=f"{prefix}*", count=200)
                for k in keys:
                    try:
                        uid = int(k.decode().split(prefix)[-1])
                        cnt = int(await r.get(k) or 0)
                        if cnt >= settings.DREAM_SESSION_INTERVAL:
                            asyncio.create_task(run_dream(uid))
                            await r.delete(k)
                    except Exception:
                        continue
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning(f"[Memory] Dream 调度循环异常（下次重试）: {exc}")