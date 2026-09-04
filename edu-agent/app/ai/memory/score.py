"""遗忘曲线分数计算（task25 R7，Ebbinghaus 指数衰减）。

公式（与任务文档一致）：
    score = importance × exp(-0.01·Δt_days) + recency_bonus
    recency_bonus = MEMORY_RECENCY_WEIGHT / (1 + MEMORY_RECENCY_SLOPE · days_since_access)

语义设计（对齐「高重要久未访问按时间衰减而非误删」）：
- importance 越大，指数衰减后的残值越高 → 越晚跌到软删阈值（0.1），**不会被过早误删**。
  例：importance=1 经 ~120 天跌 <0.3；importance=5 经 ~390 天仍 ~0.08，接近阈值但明显更久。
- recency_bonus 保护**近期被召回**的记忆：刚被 recall 触发加分，避免因单一久未访问被淘汰。
- 时间衰减严格指数（exp(-λ·Δt)），λ=0.01，Δt 单位**天**：纯粹「久未访问」也会缓慢衰减，
  但 high-importance 衰减更慢，淘汰排序以 score 升序 → 最低分（低重要+久未访问）优先牺牲。
- 纯函数，无 I/O；独立单测直接覆盖（GWT③ 衰减/淘汰正确性）。
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def time_decay_factor(
    days_since_created: float,
    *,
    lambda_: float = 0.01,
) -> float:
    """Ebbinghaus 指数衰减因子 exp(-λ·Δt)。Δt≤0 视为 0（记忆不可能比创建更早衰减）。"""
    if days_since_created is None or days_since_created < 0:
        days_since_created = 0.0
    return math.exp(-lambda_ * float(days_since_created))


def recency_bonus(
    days_since_access: float | None,
    *,
    weight: float = 2.0,
    slope: float = 0.1,
) -> float:
    """近因加成：越久未访问加成越低，但恒 >0（不把近期访问的抹成 0）。
    无访问记录（None）视同 created_at 为访问基准（初始即带一定加成，防止刚写入即被判死）。"""
    if days_since_access is None:
        days_since_access = 0.0
    d = max(0.0, float(days_since_access))
    return weight / (1.0 + slope * d)


def memory_score(
    importance: int,
    *,
    days_since_created: float,
    days_since_access: float | None = None,
    lambda_: float = 0.01,
    recency_weight: float = 2.0,
    recency_slope: float = 0.1,
) -> float:
    """综合分 = importance×exp(-0.01·Δt_created) + recency_bonus(Δt_access)。"""
    decay = time_decay_factor(days_since_created, lambda_=lambda_)
    bonus = recency_bonus(days_since_access, weight=recency_weight, slope=recency_slope)
    return round(max(0.0, importance * decay + bonus), 6)


def days_since(now: datetime, ts: datetime | str | None) -> float:
    """把 DB/程序的时间截转成「距 now 的天数」（float，支持 datetime/字符串）。"""
    if ts is None:
        return 0.0
    if isinstance(ts, str):
        try:
            # MySQL DATETIME(3) -> '%Y-%m-%d %H:%M:%S.%f'；无毫秒则补
            raw = ts.strip()
            if "." not in raw:
                raw += ".000000"
            ts = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f")
        except Exception:
            return 0.0
    delta = (now - ts).total_seconds()
    return max(0.0, delta / 86400.0)


def pick_forget_candidates(
    rows: list[dict[str, Any]],
    *,
    capacity: int,
    soft_delete_score: float = 0.1,
) -> tuple[list[int], list[int]]:
    """遗忘选择（纯函数，白盒可直接测）。

    Args:
        rows: 该用户的有效记忆行（含 deleted=0），每项需含 id/importance/score/created_at/last_access_at
        capacity: 容量上限（>500）
        soft_delete_score: 软删阈值（score 低于此值直接遗忘）

    Returns:
        (ids_to_soft_delete_expired, ids_to_soft_delete_overcap)
        - expired：score < soft_delete_score 的时间衰减淘汰（高重要衰减慢，不易进此池→非误删）
        - overcap：expired 处理完仍超 capacity 时，按 score 升序淘汰最低分补齐到 capacity
    """
    if not rows:
        return [], []
    expired = [int(r["id"]) for r in rows if float(r["score"]) < soft_delete_score]
    active = [r for r in rows if int(r["id"]) not in expired]
    overcap_ids: list[int] = []
    if len(active) > capacity:
        # 综合分最低者优先淘汰（score 已编码 importance 衰减，高重要得分高，天然护住）
        ordered = sorted(active, key=lambda r: (float(r["score"]), int(r["id"])))
        slack = len(active) - capacity
        overcap_ids = [int(r["id"]) for r in ordered[:slack]]
    return expired, overcap_ids


def prune_ids_for_user(
    rows: list[dict[str, Any]],
    *,
    capacity: int,
    soft_delete_score: float = 0.1,
) -> list[int]:
    """返回该用户所有应软删的记忆 id 集合（expired ∪ overcap 去重）。"""
    expired, overcap = pick_forget_candidates(
        rows, capacity=capacity, soft_delete_score=soft_delete_score
    )
    return list(dict.fromkeys(expired + overcap))