"""课程系列评价域 用户端路由（Season-2 需求 B）。

端点：
- GET  /api/courses/{series_id}/reviews   某系列评价列表（分页 {total,page,page_size,items}，含昵称）
- POST /api/courses/{series_id}/reviews   登录用户给已报名该系列评价（rating 1~5 必填，content 可选）
要求登录（get_current_user）；返回统一 C-A 壳 ok()。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth import CurrentUser, get_current_user
from app.core.resp import ok
from app.domains.review import service as svc
from app.domains.review.schemas import ReviewCreate

router = APIRouter(tags=["course · 评价"])


@router.get("/api/courses/{series_id}/reviews", summary="某系列评价列表（分页）")
async def list_reviews(
    series_id: int,
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，1~100"),
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.list_reviews(series_id, page=page, page_size=page_size)
    return ok(data=data.model_dump(mode="json"))


@router.post("/api/courses/{series_id}/reviews", summary="给已报名该系列提交评价")
async def create_review(
    series_id: int,
    body: ReviewCreate,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.create_review(series_id, user.user_id, body.rating, body.content)
    return ok(data=data, message="评价已提交")