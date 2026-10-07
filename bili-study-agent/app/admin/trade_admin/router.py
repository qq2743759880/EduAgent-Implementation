"""
管理端 交易运营聚合 router（需求 A）。

端点：GET /api/admin/trade/overview — ADMIN/MANAGER 可访问。
对齐 user_admin router 模式：router 前缀 + require_role 依赖；返回裸 dict 由 RespWrapMiddleware 包壳。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth import CurrentUser, UserRole, require_role
from app.admin.trade_admin import service as trade_service
from app.core.resp import ok

router = APIRouter(
    prefix="/api/admin/trade",
    tags=["admin-trade"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.MANAGER]))],
)


@router.get("/overview", summary="交易运营聚合概览（热门榜/营收/订单概况）")
async def trade_overview(
    top_n: int = Query(10, ge=1, le=100, description="热门课程榜条数"),
    user: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    data = await trade_service.get_overview(top_n=top_n)
    return ok(data=data)