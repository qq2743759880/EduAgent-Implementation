# -*- coding: utf-8 -*-
"""after_sales/ticket 域（task22 契约⑫）schemas。

对齐前端 tickets.ts（权威，task40 已封装）+ api-request §7：
- ticket_type ∈ {consult,appeal,refund,other}（前端 TicketType；appeal=人工申诉）
- ticket_status ∈ {open,processing,resolved,closed}（前端 TicketStatus）
- 4 端点：POST /api/trade/after_sales/ticket、GET .../tickets、GET .../ticket/{id}、POST .../ticket/{id}/satisfaction
- 满意度：satisfaction_score(1-5) + satisfaction_comment，不可重复评分（service_ticket_satisfaction_survey.ticket_id 唯一）
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TicketType = Literal["consult", "appeal", "refund", "other"]
TicketStatus = Literal["open", "processing", "resolved", "closed"]


class TicketCreateInput(BaseModel):
    """创建工单（ticket_type 含 appeal 人工申诉）。"""
    ticket_type: TicketType = Field(..., description="工单类型：consult/appeal/refund/other")
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=4000)
    order_no: str | None = Field(None, description="关联订单号（可选）")


class Ticket(BaseModel):
    """工单（对齐前端 Ticket 类型）。"""
    ticket_id: int
    ticket_no: str
    user_id: int
    order_no: str | None = None
    ticket_type: TicketType
    title: str
    content: str
    status: TicketStatus
    reply: str | None = None
    satisfaction_score: int | None = None
    satisfaction_comment: str | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None


class TicketPage(BaseModel):
    """我的工单分页（对齐前端 TicketPage，cmd 箱壳）。"""
    total: int
    page: int
    page_size: int
    items: list[Ticket] = []


class TicketSatisfactionInput(BaseModel):
    """满意度评价（1-5 星 + 可选评语）。"""
    satisfaction_score: int = Field(..., ge=1, le=5, description="满意度评分 1-5")
    satisfaction_comment: str | None = Field(None, max_length=2000)


class TicketSatisfactionResult(BaseModel):
    """满意度结果。"""
    ticket_id: int
    satisfaction_score: int
    submitted: bool