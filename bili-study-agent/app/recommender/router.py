# -*- coding: utf-8 -*-
"""P4 推荐引擎 router。"""
from __future__ import annotations

from app.auth.dependencies import CurrentUser, get_current_user
from fastapi import APIRouter, Depends, Query

from app.recommender import engine
from app.recommender.schemas import (
    LearningPath, NextStepOut, RecommendFeedbackIn, RecommendFeedbackOut,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/path", response_model=LearningPath, summary="生成个性化学习路径（完整 6-8 周路径）")
async def recommend_path(
    current_user: CurrentUser = Depends(get_current_user),
    subject_code: str | None = Query(default=None, max_length=32, description="english / programming / math，空=画像自动挑"),
    target_level: str | None = Query(default=None, max_length=8, description="目标 L1-L5，空=画像当前等级+1"),
    save: bool = Query(default=True, description="是否写入 learning_path_instance 持久化快照"),
) -> LearningPath:
    return await engine.build_learning_path(current_user.user_id, subject_code=subject_code,
                                             target_level=target_level, save=save)


@router.get("/next", response_model=NextStepOut, summary="下一步推荐（首页/学习页卡片式轻量推荐）")
async def recommend_next(
    current_user: CurrentUser = Depends(get_current_user),
    top_n: int = Query(default=5, ge=1, le=20),
) -> NextStepOut:
    return await engine.hybrid_rank(current_user.user_id, top_n=top_n, for_scene="NEXT")


@router.post("/feedback", response_model=RecommendFeedbackOut, summary="推荐反馈：有帮助/不感兴趣/已学过/太难")
async def recommend_feedback(
    payload: RecommendFeedbackIn,
    current_user: CurrentUser = Depends(get_current_user),
) -> RecommendFeedbackOut:
    return await engine.submit_feedback(current_user.user_id, payload)
