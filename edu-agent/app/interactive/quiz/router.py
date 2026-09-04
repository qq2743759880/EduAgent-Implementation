# -*- coding: utf-8 -*-
"""P5 quiz router：next / submit / wrong-book 3 API + 额外 3 个辅助（复习模式抽题、单题详情、题型列表）。"""
from __future__ import annotations

from app.auth.dependencies import CurrentUser, get_current_user
from fastapi import APIRouter, Depends, Query

from app.interactive.quiz import service
from app.interactive.quiz.schemas import (
    Question, SubmitAnswer, SubmitResult, WrongBookList,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/next", response_model=Question, summary="下一道互动习题（优先到期错题，否则按薄弱知识点/学科/题型抽）")
async def quiz_next(
    current_user: CurrentUser = Depends(get_current_user),
    subject_code: str | None = Query(default=None, max_length=32, description="english / math / programming"),
    question_type: str | None = Query(default=None, max_length=16, description="SINGLE/MULTI/JUDGE/FILL/DRAG_SORT/MATCH"),
) -> Question:
    return await service.next_question(current_user.user_id, subject_code=subject_code,
                                       question_type=question_type)


@router.post("/submit", response_model=SubmitResult, summary="提交作答：即时判分+解析，并写入错题本")
async def quiz_submit(
    payload: SubmitAnswer,
    current_user: CurrentUser = Depends(get_current_user),
) -> SubmitResult:
    return await service.submit(current_user.user_id, payload)


@router.get("/wrong-book", response_model=WrongBookList, summary="错题本列表：分页 + status 过滤 + 到期复习过滤")
async def quiz_wrong_book(
    current_user: CurrentUser = Depends(get_current_user),
    status: str = Query(default="ACTIVE", pattern=r"^(ACTIVE|MASTERED|ARCHIVED|ALL)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    subject_code: str | None = Query(default=None, max_length=32),
    only_due: bool = Query(default=False),
) -> WrongBookList:
    return await service.wrong_book_list(current_user.user_id, status=status, page=page, page_size=page_size,
                                          subject_code=subject_code, only_due=only_due)


@router.get("/wrong-next", response_model=Question, summary="错题复习模式：取一道到期错题（=复习模式的「下一道」）")
async def quiz_wrong_next(
    current_user: CurrentUser = Depends(get_current_user),
    subject_code: str | None = Query(default=None, max_length=32),
) -> Question:
    return await service.pick_wrong(current_user.user_id, subject_code=subject_code)


@router.get("/types", summary="支持题型枚举清单（给前端 Tab/筛选用）")
async def quiz_types() -> dict[str, str]:
    return {
        "SINGLE": "单选题",
        "MULTI": "多选题",
        "JUDGE": "判断题",
        "FILL": "填空题（含多空）",
        "DRAG_SORT": "拖拽排序",
        "MATCH": "连线匹配",
    }


@router.get("/question/{custom_code}", response_model=Question, summary="按 custom_code 取题目详情（打靶/自测用）")
async def quiz_question_detail(custom_code: str) -> Question:
    q = await service._load_by_code_or_id(code=custom_code)
    if q is None:
        from app.common.exceptions import AppException as BizError
        raise BizError(404005, f"未找到 custom_code={custom_code}")
    return q
