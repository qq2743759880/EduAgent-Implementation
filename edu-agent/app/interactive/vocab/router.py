# -*- coding: utf-8 -*-
"""P5 vocab router：/daily /recall /progress 3 API。"""
from __future__ import annotations

from app.auth.dependencies import CurrentUser, get_current_user
from fastapi import APIRouter, Depends, Query

from app.interactive.vocab import service
from app.interactive.vocab.schemas import (
    DailyPlan, ProgressStat, RecallIn, RecallOut,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/daily", response_model=DailyPlan, summary="今日单词计划：到期复习 + 新词配额")
async def vocab_daily(
    current_user: CurrentUser = Depends(get_current_user),
    level_code: str | None = Query(default=None, max_length=8, description="L1..L5，默认按画像定级"),
    new_quota: int = Query(default=20, ge=5, le=100, description="今日新词上限"),
    review_quota: int = Query(default=60, ge=5, le=200, description="今日复习上限"),
) -> DailyPlan:
    return await service.daily_plan(current_user.user_id, level_code=level_code,
                                     new_quota=new_quota, review_quota=review_quota)


@router.post("/recall", response_model=RecallOut, summary="SM-2 记忆质量 quality 上报（0-5）")
async def vocab_recall(
    payload: RecallIn,
    current_user: CurrentUser = Depends(get_current_user),
) -> RecallOut:
    return await service.recall(current_user.user_id, payload)


@router.get("/progress", response_model=ProgressStat, summary="单词闯关进度：等级掌握数 / 打卡 / 30 天正确率")
async def vocab_progress(
    current_user: CurrentUser = Depends(get_current_user),
    level_code: str | None = Query(default=None, max_length=8),
) -> ProgressStat:
    return await service.progress(current_user.user_id, level_code=level_code)
