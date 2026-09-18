# -*- coding: utf-8 -*-
"""trade/payment 域（task18 契约⑨）路由。

端点（对齐 api-request.md §6 + 前端 payments.ts，权威前缀 /api/trade/payment）：
- POST   /api/trade/payment/{order_no}             发起支付（body {pay_channel}）
- GET    /api/trade/payment/{payment_no}           支付详情/轮询
- POST   /api/trade/payment/{payment_no}/mock-notify   mock 回调（仅 mock 模拟渠道）
- GET    /api/trade/payments                       支付分页（status/order_no 过滤）
- POST   /api/trade/payment/{payment_no}/cancel    取消支付（pending→closed）
- POST   /api/trade/payment/{payment_no}/retry     重试支付（closed/failed→pending）
- POST   /api/trade/payments/reconcile             对账任务（报告）
- GET    /api/trade/payments/reconcile             对账报告查询（等价 POST 即日报告）

双路径别名（契约⑨判决：防前端/旧称破坏，两套都通）：
- POST   /api/payments/{order_no}                 alias → 发起支付
- GET    /api/payments/{payment_no}               alias → 详情/轮询
- GET    /api/payments                            alias → 支付分页
- POST   /api/payments/{payment_no}/cancel        alias → 取消支付
- POST   /api/payments/{payment_no}/retry         alias → 重试支付
- POST   /api/payments/reconcile / GET /api/payments/reconcile  alias → 对账
- POST   /payment-notifications/mock              mock 回调（body {payment_no, third_party_trade_no}，仅 mock 渠道）
- POST   /payment-notifications/channel           真实渠道回调（alipay/wechat_pay；验商户+RSA2 验签+验金额闸门，W-NEXT-PAYGATE-001）

响应壳沿用契约① ok()；失败 AppException → 全局 handler。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth import UserRole
from app.config import settings
from app.core.resp import ok
from app.domains.trade.payment import service as svc
from app.domains.trade.payment.schemas import (
    ChannelNotifyInput, MockNotifyInput, MockNotifyPathBody, PaymentLaunchInput,
)

router = APIRouter(tags=["trade · 支付"])


@router.post("/api/trade/payment/{order_no}", summary="发起支付")
@router.post("/api/payments/{order_no}", summary="发起支付（alias）", include_in_schema=False)
async def launch_payment(
    order_no: str,
    body: PaymentLaunchInput,
    user: CurrentUser = Depends(get_current_user),
):
    result = await svc.launch_payment(user.user_id, order_no, body.pay_channel)
    return ok(data=result.model_dump(mode="json"))


@router.get("/api/trade/payment/{payment_no}", summary="支付详情/轮询")
@router.get("/api/payments/{payment_no}", summary="支付详情/轮询（alias）", include_in_schema=False)
async def get_payment(
    payment_no: str,
    user: CurrentUser = Depends(get_current_user),
):
    payment = await svc.get_payment(user.user_id, payment_no)
    return ok(data=payment.model_dump(mode="json"))


@router.post("/api/trade/payment/{payment_no}/mock-notify", summary="mock 回调（仅 mock 渠道）")
@router.post("/api/payments/{payment_no}/mock-notify", summary="mock 回调（alias）", include_in_schema=False)
async def mock_notify(
    payment_no: str,
    body: MockNotifyPathBody | None = None,
    me: CurrentUser = Depends(get_current_user),
):
    # 安全收敛：mock 回调默认拒绝，仅 DEBUG 模式或 ADMIN/MANAGER 可调用（B2）
    if not settings.DEBUG and me.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="mock 回调仅允许 ADMIN/MANAGER 角色或 DEBUG 模式调用")
    third_party = (body.third_party_trade_no if body else None)
    result = await svc.mock_notify(payment_no, third_party_trade_no=third_party)
    return ok(data=result.model_dump(mode="json"))


@router.post("/payment-notifications/mock", summary="mock 回调（body {payment_no, third_party_trade_no}，仅 mock 渠道）")
async def mock_notify_body(
    body: MockNotifyInput,
    me: CurrentUser = Depends(get_current_user),
):
    # 安全收敛：mock 回调默认拒绝，仅 DEBUG 模式或 ADMIN/MANAGER 可调用（B2）
    if not settings.DEBUG and me.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="mock 回调仅允许 ADMIN/MANAGER 角色或 DEBUG 模式调用")
    result = await svc.mock_notify(body.payment_no, third_party_trade_no=body.third_party_trade_no)
    return ok(data=result.model_dump(mode="json"))


@router.post("/payment-notifications/channel", summary="真实渠道回调（alipay/wechat_pay：验商户+验签+验金额闸门）")
async def channel_notify(body: ChannelNotifyInput):
    # 服务端对服务端回调：渠道服务器无法持 JWT，鉴权 = 闸门三关
    # （验商户 + RSA2 验签 + 验金额；缺 key → 50301 fail closed，任何一关不过拒绝+审计）。
    # mock 渠道不走本入口（mock 回调走既有 mock-notify 端点，鉴权语义零变化）。
    result = await svc.channel_notify(
        body.channel, body.payment_no,
        payload=body.payload, signature=body.signature, merchant_id=body.merchant_id,
        notify_amount=body.notify_amount, third_party_trade_no=body.third_party_trade_no,
    )
    return ok(data=result.model_dump(mode="json"))


@router.get("/api/trade/payments", summary="支付分页查询")
@router.get("/api/payments", summary="支付分页查询（alias）", include_in_schema=False)
async def list_payments(
    status: Optional[str] = Query(None, description="支付状态过滤：pending/paid/failed/closed/refunded"),
    order_no: Optional[str] = Query(None, description="按订单号过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.list_payments(payment_status=status, order_no=order_no, page=page, page_size=page_size)
    return ok(data=data.model_dump(mode="json"))


@router.post("/api/trade/payment/{payment_no}/cancel", summary="取消支付")
@router.post("/api/payments/{payment_no}/cancel", summary="取消支付（alias）", include_in_schema=False)
async def cancel_payment(
    payment_no: str,
    user: CurrentUser = Depends(get_current_user),
):
    result = await svc.cancel_payment(user.user_id, payment_no)
    return ok(data=result.model_dump(mode="json"))


@router.post("/api/trade/payment/{payment_no}/retry", summary="重试支付")
@router.post("/api/payments/{payment_no}/retry", summary="重试支付（alias）", include_in_schema=False)
async def retry_payment(
    payment_no: str,
    user: CurrentUser = Depends(get_current_user),
):
    payment = await svc.retry_payment(user.user_id, payment_no)
    return ok(data=payment.model_dump(mode="json"))


@router.post("/api/trade/payments/reconcile", summary="对账任务（无重复入账报告）")
@router.post("/api/payments/reconcile", summary="对账任务（alias）", include_in_schema=False)
async def reconcile(
    user: CurrentUser = Depends(get_current_user),
):
    result = await svc.run_reconcile(institution_id=0)
    return ok(data=result.model_dump(mode="json"))


@router.get("/api/trade/payments/reconcile", summary="对账报告")
async def reconcile_report(
    user: CurrentUser = Depends(get_current_user),
):
    result = await svc.run_reconcile(institution_id=0)
    return ok(data=result.model_dump(mode="json"))