"""课程系列评价域 管理端路由（Season-2 需求 B）。

端点（ADMIN/MANAGER）：
- GET    /api/admin/reviews          评价列表（分页 + 可按 series 过滤）
- DELETE /api/admin/reviews/{id}     软删评价（yn=0，C-C 语义）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth import UserRole, require_role
from app.core.resp import ok
from app.domains.review import service as svc

admin_router = APIRouter(
    prefix="/api/admin/reviews",
    tags=["admin-reviews"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.MANAGER]))],
)


@admin_router.get("", summary="管理端评价列表（分页 + series 过滤）")
async def admin_list_reviews(
    series_id: int | None = Query(None, ge=1, description="按系列过滤"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，1~100"),
):
    data = await svc.admin_list_reviews(series_id=series_id, page=page, page_size=page_size)
    return ok(data=data.model_dump(mode="json"))


@admin_router.delete("/{review_id}", summary="软删评价")
async def admin_delete_review(review_id: int):
    data = await svc.admin_delete_review(review_id)
    return ok(data=data, message="评价已删除")