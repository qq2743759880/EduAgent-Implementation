# -*- coding: utf-8 -*-
"""trade/payment 域（task18 契约⑨）schemas：支付发起 / 详情 / 回调 / 对账。

对齐：api-request.md §6 + 前端 payments.ts（路由 /api/trade/payment），
但渠道枚举与状态以 edu.sql payment_record 为准（task18 GWT③ 要求 offline_transfer 线下审核）。
- 渠道 pay_channel：edu.sql 权威 `wechat_pay,alipay,bank_card,offline_transfer,public_account,campus_cashier` + `mock`
  （前端 task40 PayChannel 用 wechat/alipay/balance/mock 缩略，本域接受别名映射并在交接单说明）
- 状态 payment_status：edu.sql 权威 `pending,paid,failed,closed,partial_refunded,refunded`
  （前端 PaymentStatus 用 succeeded/expired，本域存储/暴露用 paid/failed 等 edu.sql 值，GWT② 即 payment_status=paid）
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PayChannel = Literal[
    "wechat_pay", "alipay", "bank_card", "offline_transfer",
    "public_account", "campus_cashier", "mock",
]
PaymentStatus = Literal["pending", "paid", "failed", "closed", "partial_refunded", "refunded"]


class Payment(BaseModel):
    """支付记录/详情轮询（前端 Payment 字段 + edu.sql 状态）。"""
    payment_no: str
    order_no: str
    pay_amount: float
    pay_channel: PayChannel
    status: PaymentStatus = "pending"
    channel_trade_no: str | None = None          # third_party_trade_no
    created_at: datetime
    finished_at: datetime | None = None          # paid_at / refund_at


class PaymentLaunchInput(BaseModel):
    """发起支付请求体（前端 PaymentLaunchInput：pay_channel）。"""
    pay_channel: str = Field(..., description="渠道：wechat_pay/alipay/bank_card/offline_transfer/public_account/campus_cashier/mock")


class PaymentLaunchResult(BaseModel):
    """发起支付结果（前端 PaymentLaunchResult）。线下转账无即时回调。"""
    payment_no: str
    order_no: str
    status: PaymentStatus = "pending"
    pay_url: str | None = None
    qr_code_url: str | None = None
    # 附加：线下转账「到账审核中」前端提示（GWT③）
    audit_pending: bool = False


class MockNotifyInput(BaseModel):
    """mock 回调请求体（独立 `/payment-notifications/mock`，payment_no 必填）。"""
    payment_no: str = Field(..., description="待模拟支付成功的 payment_no")
    third_party_trade_no: str | None = Field(None, max_length=128, description="模拟渠道交易号")


class MockNotifyPathBody(BaseModel):
    """mock 回调请求体（路径版 `/api/trade/payment/{payment_no}/mock-notify`，payment_no 来自路径）。"""
    third_party_trade_no: str | None = Field(None, max_length=128, description="模拟渠道交易号")


class ChannelNotifyInput(BaseModel):
    """真实渠道回调请求体（`/payment-notifications/channel`，W-NEXT-PAYGATE-001）。

    服务端对服务端回调（无 JWT），鉴权 = 闸门三关（验商户 + RSA2 验签 + 验金额）。
    - payload：渠道回调参数全集（参与 RSA2 验签；不含 sign 本身）
    - signature：渠道签名（base64）
    - notify_amount：回调金额（元），与订单 payable_amount 分单位比较
    - merchant_id：渠道商户号/app_id，与 PAY_MERCHANT_ID 精确匹配
    """
    channel: str = Field(..., description="回调渠道：alipay/wechat_pay（其余拒绝）")
    payment_no: str = Field(..., description="平台支付单号")
    payload: dict = Field(default_factory=dict, description="回调参数全集（参与验签）")
    signature: str | None = Field(None, max_length=4096, description="渠道签名（base64）")
    merchant_id: str | None = Field(None, max_length=128, description="渠道商户号/app_id")
    notify_amount: float | str | None = Field(None, description="回调金额（元）")
    third_party_trade_no: str | None = Field(None, max_length=128, description="渠道交易号")


class MockNotifyResult(BaseModel):
    """mock 回调结果。"""
    applied: bool
    payment_no: str
    order_no: str | None = None
    message: str


class PaymentCancelResult(BaseModel):
    """取消支付。"""
    cancelled: bool
    payment_no: str


class PaymentPage(BaseModel):
    """支付列表分页（查询）。"""
    total: int
    page: int
    page_size: int
    items: list[Payment]


class PaymentReconcileResult(BaseModel):
    """对账报告（GWT④ 无重复入账）。"""
    report_no: str
    total_paid_payments: int
    total_reconciled_orders: int
    reconciled_amount: float
    anomalies: list[dict] = Field(default_factory=list)   # 重复入账 / 金额不一致异常
    ok: bool = True