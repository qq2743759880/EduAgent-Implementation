# -*- coding: utf-8 -*-
"""R-M1 学习事件分析 —— router（M-3 聚合端点 + 事件流运行态观测）。

鉴权范式对齐 app.auth.dependencies：
- summary：admin/manager 可查任意 user_id；student 仅可查本人（否则 403 ANALYTICS_FORBIDDEN）；
- stream-stats：仅 admin/manager（require_role 工厂）。
响应壳 {code:0,message:"ok",data} 由 ok() 统一；错误码见 app/common/error_codes.py analytics 段。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentUser, get_current_user, require_role
from app.auth.schemas import UserRole
from app.common.error_codes import ANALYTICS_FORBIDDEN
from app.common.exceptions import AppException
from app.core.resp import ok
from app.domains.analytics import event_stream, service
from app.domains.analytics.schemas import LearningEventStreamStats, LearningEventSummary

router = APIRouter(prefix="/api/analytics", tags=["R-M1 学习事件分析"])


@router.get("/learning-events/summary", summary="学习事件聚合（管理端看板数据源；student 仅可查自己）")
async def learning_events_summary(
    user_id: int | None = Query(None, ge=1, description="目标用户 ID；缺省=当前登录用户"),
    range: str = Query("7d", alias="range", description="时间窗：1d/7d/30d/90d"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """按 type 聚合 learning_event（count/最近活跃）。student 传他人 user_id → 403。"""
    target_id = current_user.user_id
    if user_id is not None and int(user_id) != current_user.user_id:
        if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
            raise AppException(ANALYTICS_FORBIDDEN, "student 仅可查询本人学习事件聚合")
        target_id = int(user_id)
    data = await service.summarize_learning_events(target_id, range)
    return ok(data)


@router.get("/learning-events/stream-stats", summary="学习事件流运行态（队列/熔断/计数；仅 admin/manager）")
async def learning_events_stream_stats(
    current_user: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """事件流旁路观测面：开关/队列积压/熔断状态/丢弃计数（对账与降级验收用）。"""
    return ok(event_stream.stats_snapshot())
