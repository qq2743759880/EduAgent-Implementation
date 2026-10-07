# -*- coding: utf-8 -*-
"""trade/refund 域（task19 契约⑩）路由。

端点（对齐 task19 文档）：
- POST   /api/refunds                 申请退款（金额服务端 ≤ 实付校验，GWT①）
- GET    /api/refunds                 我的退款（倒序，status 过滤 + 分页）
- POST   /api/refunds/{refund_id}/cancel  撤销（仅 pending，GWT②）
- POST   /api/admin/refunds/{id}/approve  审批通过（HITL：LangGraph interrupt + Command(resume)，GWT②）
- POST   /api/admin/refunds/{id}/reject   审批拒绝（含 remark 拒绝理由，GWT③）
- GET    /api/admin/refunds           管理端退款列表（过渡）

响应壳沿用契约① ok()；失败 AppException → 全局 handler。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth import CurrentUser, get_current_user, require_role
from app.auth.schemas import UserRole
from app.core.resp import ok
from app.domains.trade.refund import service as svc
from app.domains.trade.refund.schemas import RefundApproveInput, RefundCreateInput

router = APIRouter(prefix="/api/refunds", tags=["trade · 退款"])

_REFUND_STATUSES = ("pending", "approved", "rejected", "refunded")


@router.post("", summary="申请退款（金额服务端强制校验）")
async def create_refund(
    body: RefundCreateInput,
    user: CurrentUser = Depends(get_current_user),
):
    refund = await svc.create_refund(
        user.user_id, order_no=body.order_no, refund_type=body.refund_type,
        apply_amount=body.apply_amount, reason=body.reason,
    )
    return ok(data=refund.model_dump(mode="json"))


@router.get("", summary="我的退款（倒序）")
async def list_refunds(
    status: Optional[str] = Query(None, description=f"状态过滤：{'/'.join(_REFUND_STATUSES)}"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.list_refunds(user.user_id, refund_status=status, page=page, page_size=page_size)
    return ok(data=data.model_dump(mode="json"))


@router.post("/{refund_id}/cancel", summary="撤销退款（仅 pending）")
async def cancel_refund(
    refund_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    result = await svc.cancel_refund(user.user_id, refund_id)
    return ok(data=result.model_dump(mode="json"))


# ═══════════════════════════════════════════════════════
# 管理端审批（task28：LangGraph interrupt + Command(resume)）
#   HITL_REFUND_ENABLED=True → hitl_graph.resume_refund_approval
#   HITL_REFUND_ENABLED=False → 退回 task19 stub（svc.approve/reject_refund）
# ═══════════════════════════════════════════════════════
admin_router = APIRouter(
    prefix="/api/admin/refunds",
    tags=["trade · 退款·管理审批（HITL）"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.MANAGER]))],
)


def _hitl_enabled() -> bool:
    try:
        from app.config import settings
        return bool(settings.HITL_REFUND_ENABLED)
    except Exception:
        return False


@admin_router.get("", summary="管理端·退款列表（过渡）")
async def admin_list_refunds(
    status: Optional[str] = Query(None, description=f"状态过滤：{'/'.join(_REFUND_STATUSES)}"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    me: CurrentUser = Depends(get_current_user),
):
    rows, total = await svc.list_refunds_admin(refund_status=status, page=page, page_size=page_size)
    return ok(data={"total": total, "page": page, "page_size": page_size,
                    "items": [r.model_dump(mode="json") for r in rows]})


@admin_router.post("/{refund_id}/approve", summary="审批通过（HITL interrupt-resume，原子退款 GWT②）")
async def admin_approve(
    refund_id: int,
    body: RefundApproveInput | None = None,
    me: CurrentUser = Depends(get_current_user),
):
    if _hitl_enabled():
        from app.domains.trade.refund.hitl_graph import resume_refund_approval
        result = await resume_refund_approval(
            refund_id,
            decision="approved",
            approved_amount=(body.approved_amount if body else None),
            remark=(body.remark if body else None),
            approver_user_id=me.user_id,
        )
        return ok(data=result)
    result = await svc.approve_refund(
        me.user_id, refund_id,
        approved_amount=(body.approved_amount if body else None),
        remark=(body.remark if body else None),
    )
    return ok(data=result.model_dump(mode="json"))


@admin_router.post("/{refund_id}/reject", summary="审批拒绝（HITL，含 remark 拒绝理由 GWT③）")
async def admin_reject(
    refund_id: int,
    body: RefundApproveInput | None = None,
    me: CurrentUser = Depends(get_current_user),
):
    if _hitl_enabled():
        from app.domains.trade.refund.hitl_graph import resume_refund_approval
        result = await resume_refund_approval(
            refund_id,
            decision="rejected",
            remark=(body.remark if body else None),
            approver_user_id=me.user_id,
        )
        return ok(data=result)
    result = await svc.reject_refund(
        me.user_id, refund_id, remark=(body.remark if body else None),
    )
    return ok(data=result.model_dump(mode="json"))