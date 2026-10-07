# -*- coding: utf-8 -*-
"""R-M1 学习事件流（M-1）——MongoDB `learning_event` 旁路异步写。

对齐 neo4j-mongo-activation-plan §MongoDB=M-1 + R01 记忆 worker 降级范式
（app/ai/memory/queue.py）+ 复用 app/core/breaker.py 三态熔断（closed→open→half_open）：

- **旁路异步**：`emit_learning_event` 为同步 put_nowait（毫秒级快返），绝不阻塞/抛错
  到主链——MySQL 仍是事务事实源，主链事务零改动；
- **写失败不阻断**：后台 worker 单消费者 `breaker.call(insert_one)`，失败按 retries
  重入队，超限丢弃 WARN；队列满丢弃计数（节流告警）；
- **断连熔断自愈**：连续失败 N 次（MONGO_EVENT_BREAKER_FAILURES）→ OPEN 快速失败
  （事件保留队列不丢），open_duration 到点 → HALF_OPEN 放探针 → 成功回 CLOSED；
- **开关**：`MONGO_EVENT_ENABLED=False` 时挂点空转（返回 False，零 mongo 依赖）；
- **集合 schema**：`{user_id, type, payload, ts, session_id}`（append-only）；
  索引：`(user_id, ts)` 复合、`(type, ts)` 复合、`ts` TTL（MONGO_EVENT_TTL_DAYS 可配，
  collMod 热更 expireAfterSeconds，0=不过期）。

口径注：`ts` 用服务器本地 naive datetime（与 MySQL NOW() 同口径，对账窗口直接可比；
TTL 按 mongo UTC 解释存在时区偏移，对 90d 级 TTL 语义无害，已在契约草案登记）。

worker 生命周期 `start_event_worker` / `stop_event_worker` 由 app.main.lifespan 启停
（启动失败仅 WARN 不阻断主服务，与存储初始化同语义）。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from app.config import settings
from app.core.breaker import BreakerConfig, CircuitBreaker, CircuitOpenError

# 集合名与事件类型值域（契约草案 contracts/reshape-r-analytics.json 同步登记）
COLLECTION = "learning_event"
EVENT_TYPES = ("video_heartbeat", "quiz_submit", "session_complete")


def _get_collection():
    """mongo 集合访问器（模块级函数：测试可 monkeypatch 注入 fake）。"""
    from app.database import get_mongo_db

    return get_mongo_db()[COLLECTION]


class LearningEventWorker:
    """学习事件写队列 worker（进程内 asyncio.Queue + 熔断写 mongo）。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max(1, int(settings.MONGO_EVENT_QUEUE_MAXSIZE)))
        self._max_retry = max(1, int(settings.MONGO_EVENT_MAX_RETRY))
        self._breaker = CircuitBreaker(
            "mongo_learning_event",
            BreakerConfig(
                consecutive_failures=max(1, int(settings.MONGO_EVENT_BREAKER_FAILURES)),
                open_duration=float(settings.MONGO_EVENT_BREAKER_OPEN_S),
                half_open_probes=1,
            ),
        )
        self._running = False
        # 观测计数（stats_snapshot 暴露给 stream-stats 端点 / 对账脚本）
        self.stats: dict[str, int] = {
            "enqueued": 0,             # 成功入队事件数
            "written": 0,              # 成功写入 mongo 事件数
            "retries": 0,              # 写失败重入队次数
            "dropped_over_retry": 0,   # 超重试上限丢弃数
            "dropped_queue_full": 0,   # 队列满丢弃数（enqueue 侧）
            "breaker_open_requeue": 0, # 熔断 OPEN 期事件保留回队次数
            "loop_error": 0,           # 消费循环自愈捕获的未预期异常数
        }

    # --- 消费主循环 ---
    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                doc = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            try:
                await self._write(doc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # 自愈：单条异常只计数不炸 worker（R01 范式）
                self.stats["loop_error"] += 1
                logger.warning(f"[LearningEvent] 消费循环异常（worker 存活继续）: {type(exc).__name__}: {exc}")

    async def _write(self, doc: dict[str, Any]) -> None:
        retries = int(doc.get("_retries") or 0)
        try:
            await self._breaker.call(self._insert, doc)
            self.stats["written"] += 1
            return
        except CircuitOpenError:
            # 熔断 OPEN：事件保留队列（不计重试），睡眠防空转；队列满由 enqueue 侧兜底丢弃
            self.stats["breaker_open_requeue"] += 1
            self._requeue(doc, retries)
            await asyncio.sleep(min(0.5, max(0.05, float(settings.MONGO_EVENT_BREAKER_OPEN_S) / 10.0)))
            return
        except Exception as exc:
            if retries + 1 > self._max_retry:
                self.stats["dropped_over_retry"] += 1
                logger.warning(
                    f"[LearningEvent] 写 mongo 失败超限丢弃（主链无感）: type={doc.get('type')} "
                    f"user_id={doc.get('user_id')} retries={retries} err={type(exc).__name__}: {exc}"
                )
                return
            self.stats["retries"] += 1
            self._requeue(doc, retries + 1)
            await asyncio.sleep(0.2)  # 线性退避，防 mongo 瞬断时空转打爆
            return

    def _requeue(self, doc: dict[str, Any], retries: int) -> None:
        doc["_retries"] = retries
        try:
            self._queue.put_nowait(doc)
        except asyncio.QueueFull:
            self.stats["dropped_queue_full"] += 1
            if self.stats["dropped_queue_full"] % 100 == 1:  # 告警节流，防宕机期刷爆日志
                logger.warning(
                    f"[LearningEvent] 队列满丢弃事件（累计={self.stats['dropped_queue_full']}，主链无感）"
                )

    async def _insert(self, doc: dict[str, Any]) -> None:
        payload = {k: v for k, v in doc.items() if not k.startswith("_")}
        await _get_collection().insert_one(payload)

    def stats_snapshot(self) -> dict[str, Any]:
        return {
            "enabled": bool(settings.MONGO_EVENT_ENABLED),
            "worker_running": self._running,
            "queue_size": self._queue.qsize(),
            "queue_maxsize": self._queue.maxsize,
            "breaker_state": self._breaker._state.value,
            "collection": COLLECTION,
            "counters": dict(self.stats),
        }


# ── 进程级单例（lifespan 启停；测试用 reset_event_worker_for_test 重置）──
_worker: LearningEventWorker | None = None
_task: asyncio.Task | None = None


def _get_worker() -> LearningEventWorker:
    global _worker
    if _worker is None:
        _worker = LearningEventWorker()
    return _worker


def emit_learning_event(
    event_type: str,
    *,
    user_id: int,
    session_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    """旁路挂点唯一入口（sync + put_nowait）：任何失败只计数/WARN，绝不向主链抛错。

    Returns:
        True=已入队；False=开关关闭/队列满/内部异常（均为可观测降级，主链无感）。
    """
    try:
        if not settings.MONGO_EVENT_ENABLED:
            return False
        w = _get_worker()
        doc = {
            "user_id": int(user_id),
            "type": str(event_type)[:32],
            "payload": payload if isinstance(payload, dict) else {},
            "ts": datetime.now(),  # 服务器本地 naive，与 MySQL NOW() 同口径（见模块 docstring）
            "session_id": int(session_id) if session_id is not None else None,
        }
        try:
            w._queue.put_nowait(doc)
            w.stats["enqueued"] += 1
            return True
        except asyncio.QueueFull:
            w.stats["dropped_queue_full"] += 1
            if w.stats["dropped_queue_full"] % 100 == 1:
                logger.warning(
                    f"[LearningEvent] 队列满丢弃事件（累计={w.stats['dropped_queue_full']}，"
                    f"type={event_type} user_id={user_id}，主链无感）"
                )
            return False
    except Exception as exc:  # 自愈兜底：挂点永不向主链抛错
        logger.warning(f"[LearningEvent] emit 异常（主链无感）: {type(exc).__name__}: {exc}")
        return False


async def ensure_indexes(db: Any = None) -> dict[str, Any]:
    """幂等建索引：uid_ts / type_ts 复合 + ts TTL（TTL 天数变更走 collMod 热更）。

    mongo 不可达时抛出（由调用方决定降级语义：lifespan WARN，脚本直接失败）。
    """
    from pymongo import ASCENDING, DESCENDING

    if db is None:
        from app.database import get_mongo_db

        db = get_mongo_db()
    coll = db[COLLECTION]
    await coll.create_index([("user_id", ASCENDING), ("ts", DESCENDING)], name="uid_ts")
    await coll.create_index([("type", ASCENDING), ("ts", DESCENDING)], name="type_ts")
    ttl_days = int(settings.MONGO_EVENT_TTL_DAYS)
    info = await coll.index_information()
    ts_idx = info.get("ts_1")
    if ttl_days > 0:
        want = ttl_days * 86400
        if ts_idx and ts_idx.get("expireAfterSeconds") is not None and ts_idx["expireAfterSeconds"] != want:
            await db.command(
                {"collMod": COLLECTION, "index": {"keyPattern": {"ts": 1}, "expireAfterSeconds": want}}
            )
        elif ts_idx is None or ts_idx.get("expireAfterSeconds") is None:
            await coll.create_index([("ts", ASCENDING)], expireAfterSeconds=want)
    elif ts_idx and ts_idx.get("expireAfterSeconds") is not None:
        await coll.drop_index("ts_1")  # TTL=0 → 摘除过期策略（保留普通 ts 索引由上面复合索引覆盖查询面）
    return {"collection": COLLECTION, "indexes": sorted((await coll.index_information()).keys())}


async def start_event_worker() -> dict[str, Any]:
    """lifespan 启动点：ensure_indexes + 拉起消费 task。mongo 不可达仅 WARN 不阻断。"""
    global _task
    w = _get_worker()
    idx: dict[str, Any] = {}
    if settings.MONGO_EVENT_ENABLED:
        try:
            idx = await ensure_indexes()
        except Exception as exc:
            logger.warning(f"[LearningEvent] 索引创建失败（worker 仍启动，写入期重试自愈）: {exc}")
    if _task is None or _task.done():
        _task = asyncio.create_task(w.run())
    logger.info(f"[LearningEvent] worker 已启动（enabled={settings.MONGO_EVENT_ENABLED}, indexes={idx.get('indexes')}）")
    return idx


async def stop_event_worker(timeout: float = 5.0) -> int:
    """lifespan 停止点：取消消费 task；返回残留队列长度（可观测，不强等 mongo）。"""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(_task), timeout=timeout)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass
    _task = None
    if _worker is not None:
        _worker._running = False
    return _worker._queue.qsize() if _worker is not None else 0


def stats_snapshot() -> dict[str, Any]:
    """stream-stats 端点数据源（worker 未启动也返回静态快照，不抛错）。"""
    base: dict[str, Any] = {
        "enabled": bool(settings.MONGO_EVENT_ENABLED),
        "worker_running": _task is not None and not _task.done(),
        "queue_size": _worker._queue.qsize() if _worker is not None else 0,
        "queue_maxsize": int(settings.MONGO_EVENT_QUEUE_MAXSIZE),
        "breaker_state": _worker._breaker._state.value if _worker is not None else "closed",
        "collection": COLLECTION,
        "counters": dict(_worker.stats) if _worker is not None else {},
    }
    return base


def reset_event_worker_for_test() -> None:
    """测试专用：清空单例与后台 task 引用（用例间隔离，防串扰）。"""
    global _worker, _task
    if _task is not None and not _task.done():
        _task.cancel()
    _worker = None
    _task = None
