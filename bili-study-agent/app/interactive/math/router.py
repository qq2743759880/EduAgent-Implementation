# -*- coding: utf-8 -*-
"""P5 math router：practice / step-check / explain 3 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.interactive.math import service
from app.interactive.math.schemas import ExplainIn, ExplainOut, StepCheckIn, StepCheckOut

router = APIRouter()


@router.get("/practice", summary="数学互动练习题列表（可按 topic / level 过滤）", dependencies=[Depends(get_current_user)])
async def math_practice(
    _: CurrentUser = Depends(get_current_user),
    level_code: str | None = Query(default=None, max_length=8),
    topic: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
) -> dict:
    return await service.practice(level_code=level_code, topic=topic, page=page, page_size=page_size)


@router.post("/step-check", response_model=StepCheckOut, summary="步骤校验：分步给反馈（类似 Photomath）", dependencies=[Depends(get_current_user)])
async def math_step_check(payload: StepCheckIn) -> StepCheckOut:
    return await service.step_check(payload)


@router.post("/explain", response_model=ExplainOut, summary="整题讲解：本地规则优先（打靶）；生产可由 LLM/RAG 增强", dependencies=[Depends(get_current_user)])
async def math_explain(payload: ExplainIn) -> ExplainOut:
    return await service.explain(payload)
