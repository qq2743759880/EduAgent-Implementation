# -*- coding: utf-8 -*-
"""P6 成就 & 游戏化 gamification schemas：徽章 / 积分 / 等级 / 排行榜。"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# Level 10 级积分门槛 & 头衔
LEVEL_TABLE: list[tuple[int, int, str]] = [
    (1,      0, "萌新"),
    (2,    500, "小学徒"),
    (3,   2000, "学员"),
    (4,   5000, "正式学习者"),
    (5,  10000, "学习达人"),
    (6,  20000, "学霸"),
    (7,  40000, "学术精英"),
    (8,  60000, "学术大师"),
    (9,  80000, "学者"),
    (10,100000, "传奇学神"),
]
MAX_LEVEL = LEVEL_TABLE[-1][0]


def calc_level(total_points: int) -> tuple[int, int, str]:
    """返回 (level_no, level_min, level_title)。"""
    current = LEVEL_TABLE[0]
    for lv, thr, title in LEVEL_TABLE:
        if total_points >= thr:
            current = (lv, thr, title)
        else:
            break
    return current


class BadgeItem(BaseModel):
    badge_code: str
    badge_name: str
    badge_desc: str
    category: str = Field(..., pattern=r"^(LEARNING|ACHIEVEMENT|SOCIAL)$")
    icon_emoji: str | None
    rarity: str = Field(..., pattern=r"^(COMMON|RARE|EPIC|LEGENDARY)$")
    trigger_rule: str
    rule_value: int
    reward_points: int
    unlocked: bool = False
    unlocked_at: datetime | None = None
    progress_current: int = 0
    progress_required: int = 0
    progress_pct: float = 0.0


class BadgeListResp(BaseModel):
    total: int
    unlocked_count: int
    next_milestone: str
    items: list[BadgeItem]


class PointLogItem(BaseModel):
    log_id: int
    point_type: str
    delta: int
    balance_after: int
    note: str | None
    created_at: datetime


class PointsResp(BaseModel):
    user_id: int
    total_points: int
    level_no: int
    level_title: str
    level_min: int
    next_level_min: int
    level_progress_pct: float
    logs_total: int
    recent_logs: list[PointLogItem]


class RankingRow(BaseModel):
    rank_no: int
    user_id: int
    user_name: str | None
    metric_value: int
    level_no: int = 1
    is_myself: bool = False
    badge_count: int = 0


class RankingResp(BaseModel):
    scope: str = Field(..., pattern=r"^(DAILY|WEEKLY|MONTHLY|ALL_TIME)$")
    dimension: str = Field(..., pattern=r"^(POINTS|STUDY_MIN|BADGE_COUNT)$")
    snapshot_date: date
    top: list[RankingRow]
    my_rank: RankingRow | None = None
    source: str = "SNAPSHOT_OR_LIVE"


class AwardResponse(BaseModel):
    points_added: int
    new_balance: int
    level_no: int
    level_title: str
    newly_unlocked: list[str] = []
