# -*- coding: utf-8 -*-
"""P6 成就 & 游戏化 router：5 条 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import CurrentUser, get_current_user

from . import service
from .schemas import AwardResponse, BadgeListResp, PointsResp, RankingResp

router = APIRouter(prefix="/api/gamification", tags=["成就 & 游戏化"])


@router.get("/me/badges", response_model=BadgeListResp, summary="徽章清单（含个人解锁进度）")
async def my_badges(current_user: CurrentUser = Depends(get_current_user)) -> BadgeListResp:
    return await service.list_badges_with_progress(current_user.user_id)


@router.get("/me/points", response_model=PointsResp, summary="我的积分 + 等级 + 近期流水")
async def my_points(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> PointsResp:
    return await service.my_points(current_user.user_id, page=page, page_size=page_size)


@router.post("/me/award", response_model=AwardResponse, summary="手动加积分（打靶用，真实业务走系统触发）")
async def award(
    point_type: str = Query(..., max_length=32),
    delta: int = Query(..., ge=-100000, le=100000),
    biz_key: str = Query(..., max_length=64),
    note: str | None = Query(default=None, max_length=200),
    current_user: CurrentUser = Depends(get_current_user),
) -> AwardResponse:
    if delta == 0:
        raise HTTPException(status_code=422, detail="delta 不能为 0")
    return await service.admin_award(current_user.user_id, point_type=point_type,
                                     delta=delta, biz_key=biz_key, note=note)


@router.get("/rankings", response_model=RankingResp, summary="排行榜：日/周/月/总 × 积分/时长/徽章")
async def rankings(
    scope: str = Query(default="DAILY", pattern=r"^(DAILY|WEEKLY|MONTHLY|ALL_TIME)$"),
    dimension: str = Query(default="POINTS", pattern=r"^(POINTS|STUDY_MIN|BADGE_COUNT)$"),
    top_n: int = Query(default=20, ge=3, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> RankingResp:
    return await service.ranking(current_user.user_id, scope=scope,
                                 dimension=dimension, top_n=top_n)


@router.post("/me/check-badges", summary="主动触发徽章检测（返回本次新解锁徽章列表）")
async def trigger_check_badges(
    current_user: CurrentUser = Depends(get_current_user),
):
    codes = await service.check_and_unlock_badges(current_user.user_id, event_scope="USER_TRIGGER")
    return {"newly_unlocked": codes, "count": len(codes)}
