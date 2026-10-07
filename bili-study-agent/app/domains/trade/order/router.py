# -*- coding: utf-8 -*-
"""trade/order 域（task17 契约⑧）路由。

端点（对齐 api-request.md §5 + 前端 orders.ts，幂等前缀 /api/trade/order）：
- POST   /api/trade/order                    下单（Idempotency-Key 必填；金额服务端重算）
- GET    /api/trade/orders                   订单分页（status 过滤 + 分页 + refundable）
- GET    /api/trade/order/{order_no}         订单详情（items + payments 嵌套）
- POST   /api/trade/order/{order_no}/cancel  取消订单（仅 pending；券回滚 + 余位释放）

响应壳沿用契约① ok()；失败 AppException → 全局 handler。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.common.exceptions import AppException
from app.core.resp import ok
from app.domains.trade.order import service as svc
from app.domains.trade.order.schemas import OrderCreateInput

router = APIRouter(tags=["trade · 订单"])

_VALID_STATUSES = ("pending", "paid", "completed", "cancelled", "partial_refunded", "refunded")


@router.post("/api/trade/order", summary="下单（幂等，金额服务端重算，防超卖）")
async def create_order(
    body: OrderCreateInput,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user: CurrentUser = Depends(get_current_user),
):
    if not idempotency_key:
        raise AppException("40021", "缺少 Idempotency-Key 请求头（下单必须幂等）")
    order = await svc.create_order(
        user.user_id, series_id=body.series_id, cohort_id=body.cohort_id, coupon_id=body.coupon_id,
    )
    return ok(data=order.model_dump(mode="json"))


@router.get("/api/trade/orders", summary="订单分页（状态过滤 + 分页 + refundable）")
async def list_orders(
    status: Optional[str] = Query(None, description=f"订单状态过滤，可选：{'/'.join(_VALID_STATUSES)}"),
    refundable: Optional[bool] = Query(None, description="true=仅可退款订单（paid/completed/partial_refunded）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    user: CurrentUser = Depends(get_current_user),
):
    order_status = status
    if refundable:
        # refundable=true → 状态为可退款集（paid/completed/partial_refunded）
        order_status = None  # 覆盖为多值逻辑，交给 service
        data = await svc.list_orders(user.user_id, order_status=order_status, refundable=True,
                                     page=page, page_size=page_size)
        return ok(data=data.model_dump(mode="json"))
    data = await svc.list_orders(user.user_id, order_status=order_status, page=page, page_size=page_size)
    return ok(data=data.model_dump(mode="json"))


@router.get("/api/trade/order/{order_no}", summary="订单详情（items + payments 嵌套）")
async def get_order_detail(
    order_no: str,
    user: CurrentUser = Depends(get_current_user),
):
    order = await svc.get_order_detail(user.user_id, order_no)
    return ok(data=order.model_dump(mode="json"))


@router.post("/api/trade/order/{order_no}/cancel", summary="取消订单（仅 pending）")
async def cancel_order(
    order_no: str,
    user: CurrentUser = Depends(get_current_user),
):
    resp = await svc.cancel_order(user.user_id, order_no)
    return ok(data=resp.model_dump(mode="json"))