# -*- coding: utf-8 -*-
"""R-M1 学习事件聚合（M-3）——service 层。

数据面：MongoDB `learning_event`（append-only 事件流，旁路写入见 event_stream.py）；
对账基线：MySQL 进度表（scripts/eval/mevent_reconcile.py 只读抽验）。
mongo 不可达 → DependencyUnavailableError（50301 脱敏，message 面向用户，原始异常仅入日志，
对齐 T19-3 contracts/reshape-b.json amendments 契约）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from loguru import logger

from app.common.error_codes import ANALYTICS_RANGE_INVALID
from app.common.exceptions import AppException, DependencyUnavailableError
from app.domains.analytics.event_stream import _get_collection

# 时间窗值域（契约草案同源；range 天数上限=TTL 默认 90d，防全表扫描）
RANGE_PRESETS: dict[str, int] = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt is not None else None


async def summarize_learning_events(user_id: int, range_key: str) -> dict:
    """按 type 聚合时间窗内事件（count 降序 + 最近活跃），管理端看板数据源。"""
    days = RANGE_PRESETS.get(str(range_key or "").strip())
    if days is None:
        raise AppException(
            ANALYTICS_RANGE_INVALID,
            f"非法 range={range_key}（支持 {'/'.join(RANGE_PRESETS)}）",
        )
    since = datetime.now() - timedelta(days=days)
    match = {"user_id": int(user_id), "ts": {"$gte": since}}
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$type",
                "count": {"$sum": 1},
                "last_active_at": {"$max": "$ts"},
            }
        },
        {"$sort": {"count": -1, "_id": 1}},
    ]
    try:
        coll = _get_collection()
        rows = await coll.aggregate(pipeline).to_list(length=len(RANGE_PRESETS) + 8)
        overall_rows = await coll.aggregate(
            [
                {"$match": match},
                {"$group": {"_id": None, "count": {"$sum": 1}, "first_ts": {"$min": "$ts"}, "last_ts": {"$max": "$ts"}}},
            ]
        ).to_list(length=1)
    except Exception as exc:
        # 50301 契约：原始异常仅入日志（含堆栈），message 面向用户，data 恒 null
        logger.exception(f"[LearningEvent] 聚合查询失败（mongo 不可达?）: {type(exc).__name__}")
        raise DependencyUnavailableError() from exc

    overall = overall_rows[0] if overall_rows else None
    return {
        "user_id": int(user_id),
        "range": str(range_key),
        "range_days": days,
        "total": int(overall["count"]) if overall else 0,
        "by_type": [
            {
                "type": r["_id"],
                "count": int(r["count"]),
                "last_active_at": _iso(r.get("last_active_at")),
            }
            for r in rows
        ],
        "first_ts": _iso(overall.get("first_ts")) if overall else None,
        "last_ts": _iso(overall.get("last_ts")) if overall else None,
        "generated_at": _iso(datetime.now()),
    }
