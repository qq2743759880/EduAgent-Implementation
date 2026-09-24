# -*- coding: utf-8 -*-
"""管理端基础设施实时快照（TO-EXEC-TB3 · 只读）。

owner 批评 6：「LLM 队列削峰、分布式锁、SETNX 缓存我根本没使用过，也没演示方案」。
本模块把已存在且已实证的机制（task39 限流/缓存/锁 + R1-③ Redis 队列）
变成管理端可视面板的数据源。

**领域红线：全程只读。**
- Redis：仅 `PING / INFO / KEYS / TYPE / TTL / GET / LLEN / ZCARD`。
  绝不出现 `SET / SETNX / DEL / EXPIRE / INCR / RPUSH / EVAL`——
  限流计数只**读现值**，绝不打点（否则面板自身就成了流量源，污染被测指标）。
- Mongo：仅 `count_documents / find`。
- MySQL：不访问（本页不碰业务库）。

**降级语义**：任一依赖不可达 → 该分节 `available=False` + `error`，其余分节照常，
整体永远 200（管理端面板不得因基础设施抖动而白屏，否则恰好在最需要它的时候失效）。

契约先冻结后实现：冻结稿见 `.ai-hub/plans/artifacts/dispatch/REPORT-TB3.md` §0。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from loguru import logger

# 缓存冷/热探测键族（优先级顺序；第一个非空族被采用）
# 来源：app/domains/course/service.py:138/177/190 + app/mcp/executor.py:696 真实缓存点
_PROBE_FAMILIES: tuple[str, ...] = (
    "course:series:detail:*",
    "course:cohort:detail:*",
    "course:cohort:seats:*",
    "edu:schema:*",
)

# 各分节取样上限（面板用，避免 KEYS 大族拖慢请求）
_MAX_LOCK_ITEMS = 50
_MAX_QUEUE_ITEMS = 50
_MAX_EVENT_ITEMS = 5


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt is not None else None


def mask_uid(user_id: Any) -> str:
    """user_id 脱敏：保留前 4 位，其余以 `*` 替代（保留位数不足则全掩）。

    契约硬约束②：learning_event 样例**不出原始 user_id**。
    """
    s = str(user_id if user_id is not None else "")
    if not s:
        return ""
    if len(s) <= 4:
        return "*" * len(s)
    return s[:4] + "*" * (len(s) - 4)


def _safe_endpoint(url: str) -> str:
    """Redis 端点脱敏：去掉 userinfo（防 `redis://user:pass@host` 泄凭据）。"""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(str(url or ""))
        if not parts.hostname:
            return "redis://(configured)"
        netloc = parts.hostname + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme or "redis", netloc, parts.path, "", ""))
    except Exception:  # noqa: BLE001
        return "redis://(configured)"


# ============================================================
# ① 限流计数
# ============================================================
def _rate_limit_rules() -> dict[str, tuple[int, int]]:
    """限流规则表（**同源** app.middleware.rate_limit._RATE_LIMIT_RULES，不复制副本）。"""
    from app.middleware.rate_limit import _RATE_LIMIT_RULES

    return _RATE_LIMIT_RULES


def _rule_scope(path: str) -> tuple[int, int]:
    """按与中间件完全相同的匹配语义解析某条规则对应的 (窗口秒, 上限)。

    复用中间件自身的 `_get_limit_for_path`，避免面板口径与真实限流口径漂移。
    """
    from app.middleware.rate_limit import _get_limit_for_path

    return _get_limit_for_path(path)


async def _collect_rate_limit(r: Any) -> dict[str, Any]:
    """限流计数：遍历现存 `rl:*` 键，按路径聚合当前窗口命中/拒绝数。

    键形（app/middleware/rate_limit.py:191/193）：
      rl:ip:{client_ip}:{path}  /  rl:uid:{user_id}:{path}
    值为窗口内 `INCR` 累加计数，TTL 为窗口剩余寿命。**仅读，不 INCR。**
    """
    from app.config import settings

    rules = _rate_limit_rules()
    window = 60  # 中间件全部规则窗口均为 60s（_RATE_LIMIT_RULES 同源常量）

    hits_total = 0
    keys_active = 0
    rejected_total = 0
    per_path: dict[str, dict[str, int]] = {}

    try:
        keys = await r.keys("rl:*")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"keys rl:* 失败: {type(exc).__name__}") from exc

    for key in keys:
        keys_active += 1
        # rl:<dim>:<subject>:<path...>  → path 可能含 "/"，取第 4 段起全部
        parts = key.split(":")
        if len(parts) < 4:
            continue
        path = ":" .join(parts[3:])
        try:
            raw = await r.get(key)
            current = int(raw or 0)
        except Exception:  # noqa: BLE001
            continue
        hits_total += current
        bucket = per_path.setdefault(path, {"hits": 0, "keys_active": 0, "rejected": 0})
        bucket["hits"] += current
        bucket["keys_active"] += 1
        # 「拒绝」口径：该键计数已超过其规则上限 → 至少已有 (current - max) 次被 429 短路
        _, max_requests = _rule_scope(path)
        if current > max_requests:
            bucket["rejected"] += current - max_requests
            rejected_total += current - max_requests

    items: list[dict[str, Any]] = []
    # 先列规则表全部规则（面板要能看见「规则存在」，即便当前窗口零命中）
    seen: set[str] = set()
    for path, (win, mx) in rules.items():
        if path == "default":
            continue
        seen.add(path)
        b = per_path.get(path, {"hits": 0, "keys_active": 0, "rejected": 0})
        items.append(
            {
                "path": path,
                "window_seconds": win,
                "max_requests": mx,
                "hits": b["hits"],
                "keys_active": b["keys_active"],
                "rejected": b["rejected"],
            }
        )
    # 再补「规则表里没有、但实际有计数键」的路径（default 档 / 通配命中）
    for path, b in per_path.items():
        if path in seen:
            continue
        _, mx = _rule_scope(path)
        items.append(
            {
                "path": path,
                "window_seconds": window,
                "max_requests": mx,
                "hits": b["hits"],
                "keys_active": b["keys_active"],
                "rejected": b["rejected"],
            }
        )
    items.sort(key=lambda x: (-int(x["hits"]), str(x["path"])))

    return {
        "window_seconds": window,
        "hits_total": hits_total,
        "keys_active": keys_active,
        "rejected": rejected_total,
        "rules": items,
        # 面板展示用：本进程是否处于 Redis 故障降级窗（降级期内限流「放行」不计数）
        "bypass_window": _redis_degrade_active(),
        "chat_limit": int(getattr(settings, "EDUAGENT_CHAT_LIMIT", 0) or 0),
    }


def _redis_degrade_active() -> bool:
    try:
        from app.core.redis_outage import redis_degrade_active

        return bool(redis_degrade_active())
    except Exception:  # noqa: BLE001
        return False


# ============================================================
# ② SETNX 缓存（冷/热现场对比）
# ============================================================
async def _collect_cache(r: Any) -> dict[str, Any]:
    """缓存演示：挑一个真实存在的缓存 key，现场测「冷读 → 热读」往返耗时。

    ⚠️ 语义诚实声明：本探测**只读**（仅 `GET`），不触发 loader 重建，
    因此 `cold_ms_first` 是「本进程对该 key 的首次往返耗时」，与后续热读对比
    反映的是连接池预热 + 网络抖动，**不是** 322.6ms→5.3ms 那类
    「DB 重建 vs 缓存命中」的量级差（那需要 `get_or_load` 走 loader，属写路径）。
    面板文案已按此口径标注，不夸大为「DB vs 缓存」对比。

    `speedup_ratio` = cold_ms_first / hot_ms_second，需同族键真实存在才给出，
    族全空时返回 null（不伪造）。
    """
    family = None
    keys: list[str] = []
    for pattern in _PROBE_FAMILIES:
        try:
            found = await r.keys(pattern)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"keys {pattern} 失败: {type(exc).__name__}") from exc
        if found:
            family = pattern
            keys = sorted(found)
            break
        if family is None:
            family = family or pattern

    probe_key = keys[0] if keys else None
    hot_ms = cold_ms_first = hot_ms_second = None

    if probe_key is not None:
        try:
            t0 = time.perf_counter()
            await r.get(probe_key)
            cold_ms_first = round((time.perf_counter() - t0) * 1000, 3)

            t1 = time.perf_counter()
            await r.get(probe_key)
            hot_ms = round((time.perf_counter() - t1) * 1000, 3)

            t2 = time.perf_counter()
            await r.get(probe_key)
            hot_ms_second = round((time.perf_counter() - t2) * 1000, 3)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"get {probe_key} 失败: {type(exc).__name__}") from exc

    # 互斥重建键（击穿防护观测）：get_or_load 使用 {key}:mutex
    mutex_count = 0
    try:
        for pattern in _PROBE_FAMILIES:
            mutex_count += len(await r.keys(f"{pattern}:mutex"))
    except Exception:  # noqa: BLE001
        mutex_count = 0

    ratio = None
    if cold_ms_first is not None and hot_ms_second:
        ratio = round(cold_ms_first / hot_ms_second, 2)

    return {
        "probe_key_pattern": family,
        "probe_families": list(_PROBE_FAMILIES),
        "sample_key": probe_key,
        "keys_cached": len(keys),
        "hit": probe_key is not None,
        "cold_ms_first": cold_ms_first,
        "hot_ms": hot_ms,
        "hot_ms_second": hot_ms_second,
        "speedup_ratio": ratio,
        "mutex_keys": mutex_count,
        "note": "只读 GET 往返对比（连接池预热口径），非 DB 重建 vs 缓存命中",
    }


# ============================================================
# ③ 分布式锁
# ============================================================
async def _collect_locks(r: Any) -> dict[str, Any]:
    """现存分布式锁列表 + TTL（`app/core/lock.py::RedisLock` 命名 `lock:{name}`）。"""
    try:
        keys = sorted(await r.keys("lock:*"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"keys lock:* 失败: {type(exc).__name__}") from exc

    items: list[dict[str, Any]] = []
    for key in keys[:_MAX_LOCK_ITEMS]:
        ttl = None
        try:
            ttl = int(await r.ttl(key))
        except Exception:  # noqa: BLE001
            pass
        items.append({"key": key, "ttl_seconds": ttl})
    # 按剩余寿命升序（即将过期者优先可见）
    items.sort(key=lambda x: (x["ttl_seconds"] if x["ttl_seconds"] is not None else 1 << 30))

    return {
        "count": len(keys),
        "items": items,
        "truncated": len(keys) > _MAX_LOCK_ITEMS,
        "impl": "SETNX + Lua 释放（app/core/lock.py::RedisLock）",
    }


# ============================================================
# ④ 队列深度
# ============================================================
async def _collect_queues(r: Any) -> dict[str, Any]:
    """Redisson/List 队列深度（`app/core/queue.py::TaskQueue` 命名 `queue:{name}`）。

    实测现网还存在 `edu:mem_queue:degraded`（记忆 worker 降级队列，R01 范式），
    故同时扫描 `queue:*` 与 `edu:mem_queue:*` 两族，避免只认一种命名而漏报真实积压。
    """
    keys: set[str] = set()
    try:
        keys.update(await r.keys("queue:*"))
        keys.update(await r.keys("edu:mem_queue:*"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"keys queue:* 失败: {type(exc).__name__}") from exc

    items: list[dict[str, Any]] = []
    for key in sorted(keys)[:_MAX_QUEUE_ITEMS]:
        length: int | None = None
        try:
            ktype = await r.type(key)
            if ktype == "list":
                length = int(await r.llen(key))
            elif ktype == "zset":
                length = int(await r.zcard(key))
            else:
                length = None  # 非队列类型（如降级标记 string）不冒充深度
        except Exception:  # noqa: BLE001
            length = None
        items.append({"key": key, "length": length})
    items.sort(key=lambda x: (-(x["length"] if isinstance(x["length"], int) else -1), str(x["key"])))

    return {
        "count": len([i for i in items if i["length"] is not None]),
        "total_keys": len(keys),
        "total_depth": sum(i["length"] for i in items if isinstance(i["length"], int)),
        "items": items,
        "truncated": len(keys) > _MAX_QUEUE_ITEMS,
        "impl": "RPUSH + BLPOP（app/core/queue.py::TaskQueue）",
    }


# ============================================================
# Redis 总装
# ============================================================
async def collect_redis_snapshot() -> dict[str, Any]:
    """Redis 四件套总装。不可达 → available=False，不抛。"""
    from app.config import settings

    out: dict[str, Any] = {
        "available": False,
        "endpoint": _safe_endpoint(settings.REDIS_URL),
        "ping": False,
        "dbsize": None,
        "keyspace_expires": None,
        "rate_limit": {"window_seconds": 60, "hits_total": None, "keys_active": None, "rejected": None, "rules": []},
        "cache": {
            "probe_key_pattern": None,
            "sample_key": None,
            "keys_cached": None,
            "hit": None,
            "cold_ms_first": None,
            "hot_ms": None,
            "hot_ms_second": None,
            "speedup_ratio": None,
            "mutex_keys": None,
        },
        "locks": {"count": None, "items": []},
        "queues": {"count": None, "items": []},
    }
    try:
        from app.database import get_redis

        r = get_redis()
        out["ping"] = bool(await r.ping())
        out["dbsize"] = int(await r.dbsize())
        try:
            info = await r.info("keyspace")
            db_key = str(settings.REDIS_URL).rstrip("/").rsplit("/", 1)[-1]
            ks = info.get(f"db{db_key}") or {}
            out["keyspace_expires"] = int(ks.get("expires") or 0)
        except Exception:  # noqa: BLE001
            pass

        out["rate_limit"] = await _collect_rate_limit(r)
        out["cache"] = await _collect_cache(r)
        out["locks"] = await _collect_locks(r)
        out["queues"] = await _collect_queues(r)
        out["available"] = True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[Infra] Redis 快照失败（分节降级）: {type(exc).__name__}: {exc}")
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return out


# ============================================================
# Mongo 三集合统计 + learning_event 样例
# ============================================================
async def _latest_ts(coll: Any) -> str | None:
    """集合最新一条的 `ts`（无 ts 字段的集合取 _id 时间戳，取不到则 null）。"""
    try:
        doc = await coll.find_one(sort=[("ts", -1)])
        if doc and doc.get("ts") is not None:
            ts = doc["ts"]
            return _iso(ts) if isinstance(ts, datetime) else str(ts)[:32]
        doc = await coll.find_one(sort=[("_id", -1)])
        if doc and isinstance(doc.get("_id"), datetime):
            return _iso(doc["_id"])
    except Exception:  # noqa: BLE001
        return None
    return None


async def collect_mongo_snapshot() -> dict[str, Any]:
    """MongoDB 三集合统计（artifacts.files / artifacts.chunks / learning_event）。"""
    from app.config import settings

    names = ("artifacts.files", "artifacts.chunks", "learning_event")
    out: dict[str, Any] = {
        "available": False,
        "database": settings.MONGO_DB,
        "collections": [{"name": n, "count": None, "latest_ts": None} for n in names],
    }
    try:
        from app.database import get_mongo_db

        db = get_mongo_db()
        rows = []
        for name in names:
            coll = db[name]
            try:
                count = int(await coll.count_documents({}))
            except Exception:  # noqa: BLE001
                count = None
            rows.append({"name": name, "count": count, "latest_ts": await _latest_ts(coll)})
        out["collections"] = rows
        out["available"] = True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[Infra] Mongo 快照失败（分节降级）: {type(exc).__name__}: {exc}")
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return out


async def collect_learning_event_sample() -> dict[str, Any]:
    """learning_event 最近 5 条（uid 脱敏）+ 事件流运行态。"""
    out: dict[str, Any] = {"available": False, "total": None, "items": [], "stream_stats": {}}
    # 事件流运行态来自进程内 worker，与 mongo 可达性无关 → 先取，保证降级时仍可见
    try:
        from app.domains.analytics import event_stream

        out["stream_stats"] = event_stream.stats_snapshot()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[Infra] event_stream 快照失败: {type(exc).__name__}: {exc}")
        out["stream_stats"] = {}

    try:
        from app.database import get_mongo_db

        coll = get_mongo_db()["learning_event"]
        out["total"] = int(await coll.count_documents({}))
        cursor = coll.find({}).sort("ts", -1).limit(_MAX_EVENT_ITEMS)
        items = []
        async for doc in cursor:
            payload = doc.get("payload")
            items.append(
                {
                    "ts": _iso(doc.get("ts")) if isinstance(doc.get("ts"), datetime) else (
                        str(doc.get("ts"))[:32] if doc.get("ts") is not None else None
                    ),
                    "type": doc.get("type"),
                    "user_id_masked": mask_uid(doc.get("user_id")),  # 脱敏：不出原始 uid
                    "session_id": doc.get("session_id"),
                    # 只给 payload 的键名，不给值（payload 可能含业务明细；面板只需形状）
                    "payload_keys": sorted(list(payload.keys()))[:12] if isinstance(payload, dict) else [],
                }
            )
        out["items"] = items
        out["available"] = True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[Infra] learning_event 样例失败（分节降级）: {type(exc).__name__}: {exc}")
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return out


# ============================================================
# 总入口
# ============================================================
async def build_snapshot() -> dict[str, Any]:
    """`GET /api/admin/infra/snapshot` 的 data 体（契约定稿见 REPORT-TB3 §0.2）。"""
    redis_part, mongo_part, event_part = (
        await collect_redis_snapshot(),
        await collect_mongo_snapshot(),
        await collect_learning_event_sample(),
    )
    return {
        "generated_at": _iso(datetime.now()),
        "redis": redis_part,
        "mongo": mongo_part,
        "learning_event": event_part,
    }
