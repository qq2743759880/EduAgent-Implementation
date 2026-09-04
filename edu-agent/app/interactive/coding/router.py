# -*- coding: utf-8 -*-
"""P5 coding router：run / submit / hint / list / get。"""
from __future__ import annotations

from app.auth.dependencies import CurrentUser, get_current_user
from fastapi import APIRouter, Depends, Query

from app.interactive.coding import service
from app.interactive.coding.schemas import (
    Challenge, HintIn, HintOut, RunIn, RunSubmitOut, SubmitIn,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/challenges", summary="编程挑战题列表：按 lang / level 过滤分页")
async def coding_challenges(
    _: CurrentUser = Depends(get_current_user),
    lang_code: str | None = Query(default=None, max_length=16, pattern=r"^(python|javascript|java|cpp)$"),
    level_code: str | None = Query(default=None, max_length=8),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    return await service.list_challenges(lang=lang_code, level=level_code, page=page, page_size=page_size)


@router.get("/challenges/{code}", response_model=Challenge, summary="单题详情（含 sample 非隐藏用例）")
async def coding_challenge_detail(code: str) -> Challenge:
    return await service.get_challenge(code)


@router.post("/run", response_model=RunSubmitOut, summary="运行（只跑 sample 用例，不记录/不影响最终分）")
async def coding_run(
    payload: RunIn,
    current_user: CurrentUser = Depends(get_current_user),
) -> RunSubmitOut:
    return await service.run_code(current_user.user_id, payload)


@router.post("/submit", response_model=RunSubmitOut, summary="提交（含隐藏用例，计分）")
async def coding_submit(
    payload: SubmitIn,
    current_user: CurrentUser = Depends(get_current_user),
) -> RunSubmitOut:
    return await service.submit_code(current_user.user_id, payload)


@router.post("/hint", response_model=HintOut, summary="递进式 Hint（1..N step，到顶后 next_step_available=false）")
async def coding_hint(payload: HintIn) -> HintOut:
    return await service.hint(payload)
