# -*- coding: utf-8 -*-
"""trade/refund 域（task19 契约⑩）schemas：退款申请 / 撤销 / 列表 / 审批 stub。

对齐：
- 端点 POST /api/refunds、GET /api/refunds、POST /api/refunds/{id}/cancel（task19 文档权威）
- 管理端审批 stub：POST /api/admin/refunds/{id}/approve|reject（task19 HITL 挂载点预留，task28 替换为 LangGraph interrupt；task72 后续对齐 /api/admin/refunds）
- 字段/枚举以 edu.sql refund_request 权威：
  refund_type = personal_reason/course_unsatisfied/schedule_conflict/duplicate_purchase
  refund_status = pending/approved/rejected/refunded
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RefundType = Literal["personal_reason", "course_unsatisfied", "schedule_conflict", "duplicate_purchase"]
RefundStatus = Literal["pending", "approved", "rejected", "refunded"]


class RefundCreateInput(BaseModel):
    """退款申请（金额服务端强制校验 ≤ 实付，不信前端）。"""
    order_no: str = Field(..., description="订单号")
    refund_type: RefundType = Field(..., description="退款类型：personal_reason/course_unsatisfied/schedule_conflict/duplicate_purchase")
    apply_amount: float = Field(..., gt=0, description="申请退款金额，须 ≤ 实付金额")
    reason: str = Field(..., min_length=1, max_length=2000, description="退款原因/说明")


class Refund(BaseModel):
    """退款单（edu.sql refund_request 字段 + order_no 聚合并联）。"""
    id: int
    refund_no: str
    order_no: str
    refund_type: RefundType
    refund_status: RefundStatus
    apply_amount: float
    approved_amount: float | None = None
    refund_reason: str
    remark: str | None = None            # approver 备注（拒绝理由，GWT③）
    approver_user_id: int | None = None
    applied_at: datetime
    approved_at: datetime | None = None
    refunded_at: datetime | None = None
    created_at: datetime
    cancelled: bool = False              # 撤销 = 软删 yn=0（撤销后不再展示为待处理）


class RefundCancelResult(BaseModel):
    """撤销退款。"""
    cancelled: bool
    refund_no: str


class RefundPage(BaseModel):
    """退款分页（倒序）。"""
    total: int
    page: int
    page_size: int
    items: list[Refund]


class RefundApproveInput(BaseModel):
    """管理端审批（HITL 过渡 stub，task28 替换）。"""
    approved_amount: float | None = Field(None, gt=0, description="审批通过金额，缺省=申请金额")
    remark: str | None = Field(None, max_length=2000, description="审批备注（拒绝理由必填，GWT③）")


class RefundApproveResult(BaseModel):
    """管理端审批结果。"""
    refund_no: str
    refund_status: RefundStatus