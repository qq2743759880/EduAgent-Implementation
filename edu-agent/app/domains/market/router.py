# -*- coding: utf-8 -*-
"""market 域（task16 契约⑦）路由：优惠券 + 课程收藏。

端点（对齐前端 task40 api-client + task46 已消费契约）：
优惠券：
- GET  /api/coupons/templates         可领券模板（全量；前端 listCouponTemplates）
- GET  /api/coupons?series_id=        系列适用可领券模板（前端 listSeriesCoupons）
- GET  /api/coupons                   我的券分页（前端 listMyCoupons，status/page/page_size）
- POST /api/trade/coupon/receive      领券（前端 receiveCoupon；幂等中间件前缀内，防超发）
课程收藏：
- GET    /api/favorites               我的收藏分页（前端 listFavorites）
- POST   /api/favorites               新增收藏（前端 addFavorite，body {series_id}）
- DELETE /api/favorites/{series_id}   取消收藏（前端 removeFavorite）

注：task16 文档原型为 GET /api/coupons（可领）/ GET /api/coupons/me / POST /api/coupons/{id}/receive，
但与 api-request.md + task40/task46 前端已消费契约冲突，按 api-request.md 落地（本域为唯一权威交接单，
前端 task63/67 以其为准）。响应壳沿用契约① ok()。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.resp import ok
from app.domains.market import service as svc
from app.domains.market.schemas import CouponReceiveInput, FavoriteCreateInput

coupon_router = APIRouter(tags=["market · 优惠券"])
favorite_router = APIRouter(tags=["market · 课程收藏"])

# 合法 receive_status 白名单（GWT②）
_COUPON_STATUSES = ("unused", "used", "expired")


# ═══════════════════════════════════════════════════════
# 优惠券
# ═══════════════════════════════════════════════════════
@coupon_router.get("/api/coupons/templates", summary="可领券模板全量列表")
async def list_coupon_templates(
    user: CurrentUser = Depends(get_current_user),
):
    items = await svc.list_coupon_templates(series_id=None)
    return ok(data=[i.model_dump(mode="json") for i in items])


@coupon_router.get("/api/coupons", summary="我的券分页 / 系列适用券模板（series_id）")
async def list_coupons(
    series_id: Optional[int] = Query(None, ge=1, description="传则返回该系列适用可领券模板"),
    status: Optional[str] = Query(None, pattern="|".join(_COUPON_STATUSES), description="我的券 receive_status 过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    user: CurrentUser = Depends(get_current_user),
):
    if series_id is not None:
        # 系列适用可领券模板（前端 listSeriesCoupons）
        items = await svc.list_coupon_templates(series_id=series_id)
        return ok(data=[i.model_dump(mode="json") for i in items])
    # 我的券分页（前端 listMyCoupons）
    data = await svc.list_my_coupons(user.user_id, status=status, page=page, page_size=page_size)
    return ok(data=data.model_dump(mode="json"))


@coupon_router.post("/api/trade/coupon/receive", summary="领券（幂等中间件前缀内，防超发）")
async def receive_coupon(
    body: CouponReceiveInput,
    user: CurrentUser = Depends(get_current_user),
):
    coupon = await svc.receive_coupon(user.user_id, body.coupon_template_id)
    return ok(data=coupon.model_dump(mode="json"))


# ═══════════════════════════════════════════════════════
# 课程收藏
# ═══════════════════════════════════════════════════════
@favorite_router.get("/api/favorites", summary="我的收藏分页")
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.list_favorites(user.user_id, page=page, page_size=page_size)
    return ok(data=data.model_dump(mode="json"))


@favorite_router.post("/api/favorites", summary="新增收藏（服务端幂等）")
async def add_favorite(
    body: FavoriteCreateInput,
    user: CurrentUser = Depends(get_current_user),
):
    item = await svc.add_favorite(user.user_id, body.series_id, body.favorite_source)
    return ok(data=item.model_dump(mode="json"))


@favorite_router.delete("/api/favorites/{series_id}", summary="取消收藏（软删幂等）")
async def remove_favorite(
    series_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    resp = await svc.remove_favorite(user.user_id, series_id)
    return ok(data=resp.model_dump(mode="json"))