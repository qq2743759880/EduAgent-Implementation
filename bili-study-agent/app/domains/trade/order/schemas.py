# -*- coding: utf-8 -*-
"""trade/order 域（task17 契约⑧）schemas：订单 + 明细 + 支付。

前端对齐（task40 api-client orders.ts + 冻结 status.ts order_status）：
- 路径 /api/trade/order*（api-request.md §5，幂等中间件前缀）
- Order 字段 snake_case；OrderPage 平铺分页 {total,page,page_size,items}
- order_status 状态机枚举（status.ts 权威）：pending→paid→completed / cancelled / partial_refunded→refunded
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# order_status 状态机（status.ts 冻结 + edu.sql order.order_status 权威）
OrderStatus = Literal["pending", "paid", "completed", "cancelled", "partial_refunded", "refunded"]
OrderItemStatus = Literal["pending", "paid", "completed", "cancelled", "refunded"]
PaymentStatus = Literal["pending", "paid", "failed", "closed", "partial_refunded", "refunded"]


class OrderItem(BaseModel):
    """订单明细（GWT② 嵌套返回）。"""
    order_item_id: int
    cohort_id: int
    item_name: str
    unit_price: float
    discount_amount: float = 0
    payable_amount: float
    order_item_status: OrderItemStatus = "pending"


class PaymentItem(BaseModel):
    """支付记录（GWT② 嵌套返回）。"""
    payment_no: str
    payment_channel: str
    payment_status: PaymentStatus
    amount: float
    paid_at: datetime | None = None


class Order(BaseModel):
    """订单（前端 Order 字段全集 + GWT② 嵌套 items/payments）。"""
    order_no: str
    user_id: int
    series_id: int
    cohort_id: int
    series_title: str | None = None
    order_amount: float                       # = order.total_amount
    discount_amount: float = 0                # = order.discount_amount
    pay_amount: float                         # = order.payable_amount
    coupon_id: int | None = None              # = order.coupon_receive_record_id
    status: OrderStatus = "pending"
    created_at: datetime
    paid_at: datetime | None = None
    cancelled_at: datetime | None = None
    # GWT② 嵌套（列表/简版不填，详情填）
    items: list[OrderItem] = Field(default_factory=list)
    payments: list[PaymentItem] = Field(default_factory=list)


class OrderCreateInput(BaseModel):
    """下单请求体（前端 OrderCreateInput）。coupon_id = 领券记录 id（task16 Coupon.coupon_id 语义）。"""
    series_id: int = Field(..., ge=1)
    cohort_id: int = Field(..., ge=1)
    coupon_id: int | None = Field(None, ge=1, description="优惠券领券记录 id（coupon_receive_record.id）")


class OrderCancelResult(BaseModel):
    """取消订单响应（前端 OrderCancelResult）。"""
    cancelled: bool
    order_no: str


class OrderPage(BaseModel):
    """订单分页（前端 OrderPage 平铺壳）。"""
    total: int
    page: int
    page_size: int
    items: list[Order]