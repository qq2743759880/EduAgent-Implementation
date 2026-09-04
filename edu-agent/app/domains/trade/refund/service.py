# -*- coding: utf-8 -*-
"""trade/refund 域（task19 契约⑩）service。

资金安全红线（hard）：
- 金额服务端强制校验：apply_amount ≤ 实付（订单 payable / 实际 paid 支付），绝不信任前端（GWT①）
- 幂等：refund_no（(institution_id, refund_no)）唯一键 + 同订单已有 pending 退款单则复用（防重复申请）
- 状态机条件更新：仅 pending 可撤销/审批（GWT②）；撤销 = 软删 yn=0（枚举无 cancelled，保留 refund_status）
- 审批 HITL 挂载点预留：approve/reject stub，task28 替换为 LangGraph interrupt，task20 接续退款执行
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.common.error_codes import (
    TRADE_ORDER_NOT_FOUND, TRADE_ORDER_STATUS_INVALID,
    TRADE_REFUND_EXCEED, TRADE_REFUND_STATUS_INVALID,
)
from app.common.exceptions import AppException
from app.database import transaction
from app.domains.trade.refund.repository import RefundRepo, RefundWriteRepo
from app.domains.trade.refund.schemas import Refund, RefundPage, RefundCancelResult, RefundApproveResult

logger = logging.getLogger(__name__)

_refund_repo = RefundRepo()
_refund_write = RefundWriteRepo()

VALID_REFUND_TYPES = {"personal_reason", "course_unsatisfied", "schedule_conflict", "duplicate_purchase"}
VALID_REFUND_STATUS = {"pending", "approved", "rejected", "refunded"}
# 可退款订单状态集（必须有 paid 支付已到账）
REFUNDABLE_ORDER_STATUS = {"paid", "completed", "partial_refunded"}

# HITL 挂载点预留：审批 stub 开关（task28 用 LangGraph interrupt 替换时置 False 并接入 interrupt）
HITL_STUB_MODE = True


def _refund_from_row(r: dict) -> Refund:
    return Refund(
        id=int(r["id"]),
        refund_no=r["refund_no"],
        order_no=r.get("order_no") or "",
        refund_type=r["refund_type"],
        refund_status=r["refund_status"],
        apply_amount=float(r.get("apply_amount") or 0),
        approved_amount=float(r["approved_amount"]) if r.get("approved_amount") is not None else None,
        refund_reason=r.get("refund_reason") or "",
        remark=r.get("remark"),
        approver_user_id=int(r["approver_user_id"]) if r.get("approver_user_id") else None,
        applied_at=r["applied_at"],
        approved_at=r.get("approved_at"),
        refunded_at=r.get("refunded_at"),
        created_at=r["created_at"],
        cancelled=(int(r["yn"]) if r.get("yn") is not None else 1) == 0,
    )


# ═══════════════════════════════════════════════════════
# 申请退款（金额服务端强制 ≤ 实付）
# ═══════════════════════════════════════════════════════
async def create_refund(user_id: int, *, order_no: str, refund_type: str,
                        apply_amount: float, reason: str) -> Refund:
    """申请退款。金额服务端校验（GWT①），refund_no 唯一键幂等 + 同订单 pending 复用。"""
    if refund_type not in VALID_REFUND_TYPES:
        raise AppException("42200", f"非法退款类型：{refund_type}")

    order = await _refund_repo.get_order_for_refund(order_no, user_id)
    if order is None:
        raise AppException(TRADE_ORDER_NOT_FOUND, "订单不存在")
    if order["order_status"] not in REFUNDABLE_ORDER_STATUS:
        raise AppException(TRADE_ORDER_STATUS_INVALID, f"订单状态 {order['order_status']} 不支持退款（需已支付）")

    payment_id = order.get("payment_id")
    if payment_id is None:
        raise AppException(TRADE_REFUND_STATUS_INVALID, "订单无已到账支付记录，无法退款")

    # 实付金额（服务端权威）：实际 paid 支付总额兜底用订单应付
    paid_total = float(order.get("paid_total") or 0)
    payable = float(order.get("payable_amount") or 0)
    effective_paid = paid_total if paid_total > 0 else payable
    # 浮点等值容忍（分位误差），避免等额误拒；超支一律拒绝（GWT①）
    if apply_amount > effective_paid + 1e-6:
        raise AppException(TRADE_REFUND_EXCEED, f"退款金额超出实付金额（实付 {effective_paid:.2f}）")

    institution_id = int(order["institution_id"])
    order_id = int(order["order_id"])
    order_item_id = int(order["order_item_id"])
    student_id = int(order["student_id"])
    now = datetime.now()

    # 业务幂等：同订单已有 pending 退款单 → 复用返回（快速路径，非并发）
    existing = await _refund_repo.get_pending_refund_by_order(order_id, user_id)
    if existing is not None:
        row = await _refund_repo.get_refund(int(existing["id"]), user_id)
        if row is not None:
            return _refund_from_row(row)

    refund_no = None
    refund_id = None
    already_pending = False
    try:
        async with transaction() as (conn, cur):
            # H1 资金安全红线 R2：`FOR UPDATE` 锁订单行，将同订单并发申请串行化，
            # 再在锁内重查 pending → 防并发双 pending 双退款（CHECK-THEN-INSERT 原子化）。
            await cur.execute("SELECT id FROM `order` WHERE id=%s FOR UPDATE", (order_id,))
            await cur.execute(
                "SELECT id FROM refund_request WHERE order_id=%s AND user_id=%s"
                " AND refund_status='pending' AND yn=1 LIMIT 1",
                (order_id, int(user_id)),
            )
            locked = await cur.fetchone()
            if locked is not None:
                # 并发竞态方：锁内发现已有 pending → 不插入，锁外重查复用
                already_pending = True
            else:
                refund_no = _refund_write.new_refund_no(institution_id)
                refund_id = await _refund_write.create_refund(
                    conn=conn, cur=cur, institution_id=institution_id, order_id=order_id,
                    order_item_id=order_item_id, payment_id=int(payment_id),
                    user_id=user_id, student_id=student_id, refund_no=refund_no,
                    refund_type=refund_type, refund_reason=reason, apply_amount=apply_amount, now=now,
                )
    except Exception as exc:
        # refund_no 唯一键冲突（并发/重试）→ 回查同订单 pending 退款单（业务幂等返回）
        if "1062" in str(exc) or "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            row = await _refund_repo.get_pending_refund_by_order(order_id, user_id)
            if row is not None:
                detail = await _refund_repo.get_refund(int(row["id"]), user_id)
                if detail is not None:
                    return _refund_from_row(detail)
        logger.exception("[refund] 申请退款事务失败：%s", exc)
        raise

    # 竞态方（锁内发现 pending）：锁外重查返回已有 pending → 幂等
    if already_pending:
        row = await _refund_repo.get_pending_refund_by_order(order_id, user_id)
        if row is not None:
            detail = await _refund_repo.get_refund(int(row["id"]), user_id)
            if detail is not None:
                return _refund_from_row(detail)
        raise AppException(TRADE_REFUND_STATUS_INVALID, "退款申请失败，请重试")

    if refund_id is None:
        raise AppException(TRADE_REFUND_STATUS_INVALID, "退款申请失败，请重试")
    row = await _refund_repo.get_refund(refund_id, user_id)
    if row is None:
        raise AppException(TRADE_REFUND_STATUS_INVALID, "退款申请失败，请重试")
    return _refund_from_row(row)


# ═══════════════════════════════════════════════════════
# 撤销（仅 pending）
# ═══════════════════════════════════════════════════════
async def cancel_refund(user_id: int, refund_id: int) -> RefundCancelResult:
    """撤销退款（GWT②）：仅 pending 可撤销；状态不再 pending 后不可再次撤销。"""
    row = await _refund_repo.get_refund(refund_id, user_id)
    if row is None:
        raise AppException("40420", "退款单不存在")
    now = datetime.now()
    async with transaction() as (conn, cur):
        affected = await _refund_write.cancel_refund(conn=conn, cur=cur, refund_id=refund_id,
                                                     user_id=user_id, now=now)
        if affected == 0:
            cur_status = row["refund_status"]
            cur_yn = int(row["yn"]) if row.get("yn") is not None else 1
            if cur_yn == 0:
                return RefundCancelResult(cancelled=True, refund_no=row["refund_no"])  # 幂等：已撤销
            # 非 pending（approved/rejected/refunded）→ 不可撤销
            raise AppException(TRADE_REFUND_STATUS_INVALID, f"退款状态 {cur_status} 不允许撤销")
    return RefundCancelResult(cancelled=True, refund_no=row["refund_no"])


# ═══════════════════════════════════════════════════════
# 列表（用户倒序）
# ═══════════════════════════════════════════════════════
async def list_refunds(user_id: int, *, refund_status: str | None = None,
                       page: int = 1, page_size: int = 20) -> RefundPage:
    if refund_status and refund_status not in VALID_REFUND_STATUS:
        raise AppException("42200", f"非法退款状态：{refund_status}")
    rows, total = await _refund_repo.list_refunds(
        user_id, refund_status=refund_status, page=page, page_size=page_size,
    )
    return RefundPage(total=total, page=page, page_size=page_size,
                      items=[_refund_from_row(r) for r in rows])


# ═══════════════════════════════════════════════════════
# 管理端审批（HITL 挂载点预留）
# ═══════════════════════════════════════════════════════
async def list_refunds_admin(*, refund_status: str | None = None,
                             page: int = 1, page_size: int = 20) -> tuple[list[Refund], int]:
    """管理端退款列表（过渡），返回 (items, total)。"""
    if refund_status and refund_status not in VALID_REFUND_STATUS:
        raise AppException("42200", f"非法退款状态：{refund_status}")
    rows, total = await _refund_repo.list_refunds_admin(refund_status=refund_status, page=page, page_size=page_size)
    return [_refund_from_row(r) for r in rows], total


async def approve_refund(approver_user_id: int, refund_id: int, *,
                         approved_amount: float | None, remark: str | None) -> RefundApproveResult:
    """审批通过（HITL stub）：pending → approved。task28 以 LangGraph interrupt 替换本 stub 后接续退款执行。"""
    row = await _refund_repo.get_refund(refund_id)
    if row is None:
        raise AppException("40420", "退款单不存在")
    final_amount = float(approved_amount) if approved_amount is not None else float(row["apply_amount"])
    now = datetime.now()
    async with transaction() as (conn, cur):
        affected = await _refund_write.approve_refund(
            conn=conn, cur=cur, refund_id=refund_id, approver_user_id=approver_user_id,
            approved_amount=final_amount, remark=remark, now=now,
        )
        if affected == 0:
            cur_status = row["refund_status"]
            raise AppException(TRADE_REFUND_STATUS_INVALID, f"退款状态 {cur_status} 不允许审批（需 pending）")
    return RefundApproveResult(refund_no=row["refund_no"], refund_status="approved")


async def reject_refund(approver_user_id: int, refund_id: int, *, remark: str | None) -> RefundApproveResult:
    """审批拒绝（HITL stub）：pending → rejected + approver remark（GWT③）。"""
    row = await _refund_repo.get_refund(refund_id)
    if row is None:
        raise AppException("40420", "退款单不存在")
    now = datetime.now()
    async with transaction() as (conn, cur):
        affected = await _refund_write.reject_refund(
            conn=conn, cur=cur, refund_id=refund_id, approver_user_id=approver_user_id,
            remark=remark, now=now,
        )
        if affected == 0:
            cur_status = row["refund_status"]
            raise AppException(TRADE_REFUND_STATUS_INVALID, f"退款状态 {cur_status} 不允许拒绝（需 pending）")
    return RefundApproveResult(refund_no=row["refund_no"], refund_status="rejected")