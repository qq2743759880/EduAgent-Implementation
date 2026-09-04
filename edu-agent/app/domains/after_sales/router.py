# -*- coding: utf-8 -*-
"""after_sales/ticket 域（task22 契约⑫）路由。

端点（对齐前端 tickets.ts + api-request §7，权威）：
- POST /api/trade/after_sales/ticket                       创建工单（类型含 appeal 人工申诉）
- GET  /api/trade/after_sales/tickets                      我的工单（status/type 过滤 + 分页）
- GET  /api/trade/after_sales/ticket/{ticket_id}           工单详情（越权 404；管理员可见全部）
- POST /api/trade/after_sales/ticket/{ticket_id}/satisfaction  满意度评价（1-5 星，幂等）

响应壳沿用契约① ok()；失败 AppException → 全局 handler。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.resp import ok
from app.domains.after_sales import service as svc
from app.domains.after_sales.schemas import TicketCreateInput, TicketSatisfactionInput

router = APIRouter(prefix="/api/trade/after_sales", tags=["after_sales · 工单"])

_TICKET_TYPES = ("consult", "appeal", "refund", "other")
_TICKET_STATUS = ("open", "processing", "resolved", "closed")


@router.post("/ticket", summary="创建工单（含 appeal 人工申诉）")
async def create_ticket(
    body: TicketCreateInput,
    user: CurrentUser = Depends(get_current_user),
):
    ticket = await svc.create_ticket(
        user.user_id, ticket_type=body.ticket_type, title=body.title,
        content=body.content, order_no=body.order_no,
    )
    return ok(data=ticket.model_dump(mode="json"))


@router.get("/tickets", summary="我的工单（过滤 + 分页）")
async def list_tickets(
    status: Optional[str] = Query(None, description=f"状态过滤：{'/'.join(_TICKET_STATUS)}"),
    ticket_type: Optional[str] = Query(None, description=f"类型过滤：{'/'.join(_TICKET_TYPES)}"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.list_tickets(
        user.user_id, role_name=user.role.value,
        ticket_status=status, ticket_type=ticket_type, page=page, page_size=page_size,
    )
    return ok(data=data.model_dump(mode="json"))


@router.get("/ticket/{ticket_id}", summary="工单详情（越权 404）")
async def get_ticket_detail(
    ticket_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_ticket_detail(ticket_id, user.user_id, role_name=user.role.value)
    return ok(data=data.model_dump(mode="json"))


@router.post("/ticket/{ticket_id}/satisfaction", summary="满意度评价（1-5 星，幂等）")
async def submit_satisfaction(
    ticket_id: int,
    body: TicketSatisfactionInput,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.submit_satisfaction(
        user.user_id, ticket_id, score=body.satisfaction_score, comment=body.satisfaction_comment,
    )
    return ok(data=data.model_dump(mode="json"))