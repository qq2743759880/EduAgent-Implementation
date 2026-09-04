# -*- coding: utf-8 -*-
"""trade/payment 域（task18 契约⑨）service。

资金安全红线（hard）：
- 回调幂等：payment_no 唯一键 + `WHERE payment_status='pending'` 条件更新 → 同 payment_no 并发回调仅一次生效（GWT①）
- 回调成功单事务：payment paid + order paid + student_cohort_rel active + 券 used 原子一致（GWT②）
- 线下转账（offline_transfer）：状态停留 pending + 「到账审核中」，无即时回调；mock 回调仅限模拟渠道（GWT③）
- 对账报告无重复入账（GWT④）
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.common.error_codes import TRADE_ORDER_NOT_FOUND
from app.common.exceptions import AppException
from app.database import transaction
from app.domains.trade.payment.repository import PaymentReconcileRepo, PaymentRepo, PaymentWriteRepo
from app.domains.trade.payment.schemas import (
    MockNotifyResult, Payment, PaymentCancelResult, PaymentLaunchResult,
    PaymentPage, PaymentReconcileResult,
)

logger = logging.getLogger(__name__)

_payment_repo = PaymentRepo()
_payment_write = PaymentWriteRepo()
_reconcile_repo = PaymentReconcileRepo()

# 渠道枚举（edu.sql 权威）＋ mock 模拟渠道
VALID_CHANNELS = {
    "wechat_pay", "alipay", "bank_card", "offline_transfer",
    "public_account", "campus_cashier", "mock",
}
# 前端缩略名 → edu.sql 权威名（api-request.md §6 前端 PayChannel 缩略）
CHANNEL_ALIAS = {
    "wechat": "wechat_pay",
    "alipay": "alipay",
    "balance": "bank_card",
    "mock": "mock",
    "campus": "campus_cashier",
}

# 线下转账「到账审核中」——无即时回调、状态停留 pending
_OFFLINE_CHANNEL = "offline_transfer"
# mock 回调仅限模拟渠道（wechat_pay 等真实渠道不接受 mock 通知）
_SIMULATION_CHANNELS = {"mock"}

VALID_PAYMENT_STATUS = {"pending", "paid", "failed", "closed", "partial_refunded", "refunded"}


def _norm_channel(raw: str) -> str:
    """归一化渠道：别名 → 权威名。"""
    if raw in VALID_CHANNELS:
        return raw
    if raw in CHANNEL_ALIAS:
        return CHANNEL_ALIAS[raw]
    raise AppException("42200", f"非法支付渠道：{raw}")


def _payment_from_row(r: dict) -> Payment:
    return Payment(
        payment_no=r["payment_no"],
        order_no=r.get("order_no") or "",
        pay_amount=float(r.get("amount") or r.get("payable_amount") or 0),
        pay_channel=r["payment_channel"],
        status=r["payment_status"],
        channel_trade_no=r.get("third_party_trade_no"),
        created_at=r["created_at"],
        finished_at=r["paid_at"] or r.get("refund_at"),
    )


async def launch_payment(user_id: int, order_no: str, pay_channel: str) -> PaymentLaunchResult:
    """发起支付（POST /api/trade/payment/{order_no}）。线下转账 → pending + 到账审核中。"""
    channel = _norm_channel(pay_channel)
    order = await _payment_repo.get_order_for_payment(order_no)
    if order is None:
        raise AppException(TRADE_ORDER_NOT_FOUND, "订单不存在")
    if int(order["user_id"]) != int(user_id):
        raise AppException("40320", "无权为该订单发起支付")
    if order["order_status"] != "pending":
        raise AppException("40021", f"订单状态 {order['order_status']} 不允许支付（需 pending）")
    if order["order_status"] == "cancelled":
        raise AppException("40021", "订单已取消，无法支付")

    institution_id = int(order["institution_id"])
    order_id = int(order["id"])
    amount = float(order["payable_amount"])
    now = datetime.now()

    # 幂等：同订单已有 pending 支付 → 返回已有 payment（避免重复建单）
    existing = await _payment_repo.get_payment_by_order(order_id)
    for e in existing:
        if e["payment_status"] == "pending":
            # D4：audit_pending 以已有支付的实际渠道为准（避免第二次用他渠道 launch 误报非线下）
            res = PaymentLaunchResult(
                payment_no=e["payment_no"], order_no=order_no, status=e["payment_status"],
                pay_url=None, qr_code_url=None,
                audit_pending=(e["payment_channel"] == _OFFLINE_CHANNEL),
            )
            return res

    payment_no = None
    try:
        async with transaction() as (conn, cur):
            payment_no = _payment_write.new_payment_no(institution_id)
            await _payment_write.create_payment(
                conn=conn, cur=cur, institution_id=institution_id, order_id=order_id,
                payment_no=payment_no, pay_channel=channel, amount=amount, now=now,
            )
    except Exception as exc:
        if "1062" in str(exc) or "duplicate" in str(exc).lower():
            # payment_no 唯一键冲突（并发）→ 回查已有
            e = await _payment_repo.get_payment_by_order(order_id)
            pend = next((p for p in e if p["payment_status"] == "pending"), None)
            if pend:
                return PaymentLaunchResult(
                    payment_no=pend["payment_no"], order_no=order_no, status=pend["payment_status"],
                    pay_url=None, qr_code_url=None,
                    audit_pending=(pend["payment_channel"] == _OFFLINE_CHANNEL),
                )
        logger.exception("[payment] 发起支付事务失败：%s", exc)
        raise

    return PaymentLaunchResult(
        payment_no=payment_no, order_no=order_no, status="pending",
        pay_url=None, qr_code_url=None,
        audit_pending=(channel == _OFFLINE_CHANNEL),
    )


async def get_payment(user_id: int, payment_no: str) -> Payment:
    """支付详情/轮询（GET /api/trade/payment/{payment_no}）。"""
    row = await _payment_repo.get_payment(payment_no)
    if row is None:
        raise AppException("40420", "支付记录不存在")
    return _payment_from_row(row)


async def mock_notify(payment_no: str, third_party_trade_no: str | None) -> MockNotifyResult:
    """
    mock 回调（仅模拟渠道）：单事务支付成功 + 订单 paid + 报名 active + 券 used。
    幂等：同 payment_no 并发 → 条件更新仅一次生效。
    """
    p = await _payment_repo.get_payment(payment_no)
    if p is None:
        raise AppException("40420", "支付记录不存在")
    if p["payment_channel"] not in _SIMULATION_CHANNELS:
        raise AppException("40021", "mock 回调仅限 mock 模拟渠道（真实渠道不接受）")

    now = datetime.now()
    try:
        async with transaction() as (conn, cur):
            result = await _payment_write.settle_payment(
                conn=conn, cur=cur, payment_no=payment_no,
                third_party_trade_no=third_party_trade_no, now=now,
            )
    except Exception as exc:
        if "1062" in str(exc) or "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            # 并发唯一键冲突（学生报名/券核销）→ 视为已处理（事务退出自动回滚）
            result = {"applied": False, "order_status_change": False}
        else:
            logger.exception("[payment] mock 回调事务失败：%s", exc)
            raise AppException("50000", "支付回调处理失败")

    order_no = p.get("order_no")
    if result["applied"]:
        return MockNotifyResult(applied=True, payment_no=payment_no, order_no=order_no, message="支付成功")
    return MockNotifyResult(applied=False, payment_no=payment_no, order_no=order_no, message="已处理（幂等）")


async def cancel_payment(user_id: int, payment_no: str) -> PaymentCancelResult:
    """取消支付（pending → closed）。已 paid 不可取消。"""
    p = await _payment_repo.get_payment(payment_no)
    if p is None:
        raise AppException("40420", "支付记录不存在")
    now = datetime.now()
    async with transaction() as (conn, cur):
        if await _payment_write.cancel_payment(conn=conn, cur=cur, payment_no=payment_no, now=now) == 0:
            cur_status = p["payment_status"]
            if cur_status in ("paid", "refunded"):
                raise AppException("40021", f"支付状态 {cur_status} 不可取消")
    return PaymentCancelResult(cancelled=True, payment_no=payment_no)


async def retry_payment(user_id: int, payment_no: str) -> Payment:
    """重试（closed/failed → pending），返回重试后支付记录。"""
    p = await _payment_repo.get_payment(payment_no)
    if p is None:
        raise AppException("40420", "支付记录不存在")
    now = datetime.now()
    async with transaction() as (conn, cur):
        await _payment_write.retry_payment(conn=conn, cur=cur, payment_no=payment_no, now=now)
    row = await _payment_repo.get_payment(payment_no)
    return _payment_from_row(row)


async def list_payments(
    *, payment_status: str | None = None, order_no: str | None = None, page: int = 1, page_size: int = 20,
) -> PaymentPage:
    """支付分页查询。"""
    if payment_status and payment_status not in VALID_PAYMENT_STATUS:
        raise AppException("42200", f"非法支付状态：{payment_status}")
    rows, total = await _payment_repo.list_payments(
        payment_status=payment_status, order_no=order_no, page=page, page_size=page_size,
    )
    items = [_payment_from_row(r) for r in rows]
    return PaymentPage(total=total, page=page, page_size=page_size, items=items)


async def run_reconcile(institution_id: int = 0) -> PaymentReconcileResult:
    """对账（GWT④）：比对 payment_record 与订单，报告重复入账/金额不一致。"""
    result = await _reconcile_repo.run_reconcile(institution_id=institution_id)
    return PaymentReconcileResult(
        report_no=f"RCL-{datetime.now().strftime('%y%m%d%H%M%S')}",
        total_paid_payments=result["total_paid_payments"],
        total_reconciled_orders=result["total_reconciled_orders"],
        reconciled_amount=result["reconciled_amount"],
        anomalies=result["anomalies"],
        ok=result["ok"],
    )