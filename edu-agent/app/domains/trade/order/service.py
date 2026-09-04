# -*- coding: utf-8 -*-
"""trade/order 域（task17 契约⑧）service。

资金安全红线（hard）：
- 金额服务端重算：total=series_cohort.sale_price，discount=实际券面额，payable=total-discount
  （绝不信任客户端传价；篡改请求价格无效）
- 下单 / 取消：单事务（order + order_item + 券核销/回滚 + 余位占/释），任一失败整体回滚
- 幂等三层纵深：① 中间件 Idempotency-Key 缓存 ② order_no 唯一键冲突回查 ③ 状态机条件更新
- `order` 为 MySQL 保留字 → SQL 一律反引号
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.common.error_codes import (
    TRADE_COUPON_EXPIRED, TRADE_COUPON_EXHAUSTED, TRADE_ORDER_NOT_FOUND, TRADE_ORDER_STATUS_INVALID,
)
from app.common.exceptions import AppException
from app.database import transaction
from app.domains.trade.order.repository import OrderRepo, OrderWriteRepo
from app.domains.trade.order.schemas import (
    Order, OrderCancelResult, OrderItem, OrderPage, PaymentItem,
)

logger = logging.getLogger(__name__)

_order_repo = OrderRepo()
_order_write = OrderWriteRepo()

# 班次服务周期（天），本实现取固定默认（edu.sql order_item.service_period_days NOT NULL）
DEFAULT_SERVICE_PERIOD_DAYS = 365

# 合法状态机（值域校验）
VALID_ORDER_STATUS = {"pending", "paid", "completed", "cancelled", "partial_refunded", "refunded"}


# ═══════════════════════════════════════════════════════
# 工具：行 → Order / OrderItem / Payment
# ═══════════════════════════════════════════════════════
def _order_from_row(row: dict, *, series_title: str | None = None, cohort_id: int | None = None,
                    items: list | None = None, payments: list | None = None) -> Order:
    return Order(
        order_no=row["order_no"],
        user_id=int(row["user_id"]),
        series_id=int(row.get("series_id") or 0),
        cohort_id=int(cohort_id or row.get("cohort_id") or 0),
        series_title=series_title or row.get("series_name"),
        order_amount=float(row.get("total_amount") or 0),
        discount_amount=float(row.get("discount_amount") or 0),
        pay_amount=float(row.get("payable_amount") or 0),
        coupon_id=int(row["coupon_receive_record_id"]) if row.get("coupon_receive_record_id") else None,
        status=row["order_status"],
        created_at=row["created_at"],
        paid_at=row.get("paid_at"),
        cancelled_at=row.get("cancel_at"),
        items=items or [],
        payments=payments or [],
    )


# ═══════════════════════════════════════════════════════
# 下单（防篡改价格 + 防超卖 + 幂等）
# ═══════════════════════════════════════════════════════
async def create_order(user_id: int, *, series_id: int, cohort_id: int, coupon_id: int | None) -> Order:
    """下单。单事务 order+order_item+券核销+余位占用。金额服务端重算。"""
    cohort = await _order_repo.get_cohort(cohort_id)
    if cohort is None or cohort.get("yn") != 1 or cohort.get("series_sale_status") != "on_sale":
        raise AppException(TRADE_ORDER_NOT_FOUND, "班次不存在或已下架")
    if int(cohort.get("series_id")) != series_id:
        raise AppException(TRADE_ORDER_STATUS_INVALID, "班次不属于该系列")
    if int(cohort.get("current_student_count", 0)) >= int(cohort.get("max_student_count", 0)):
        raise AppException(TRADE_COUPON_EXHAUSTED, "该班次已满员")

    institution_id = int(cohort["institution_id"])
    total_amount = float(cohort["sale_price"])  # 服务端唯一价源
    discount_amount = 0.0
    coupon_receive_record_id: int | None = None

    # 券（可选）：服务端核验面额/有效期/门槛，重算 discount
    if coupon_id is not None:
        c = await _order_repo.get_coupon_for_receive(coupon_id, user_id)
        if c is None:
            raise AppException(TRADE_COUPON_EXPIRED, "优惠券不存在或不属于当前用户")
        if c["receive_status"] == "used":
            raise AppException(TRADE_COUPON_EXPIRED, "优惠券已使用")
        now = datetime.now()
        if c.get("valid_from") and c["valid_from"] > now:
            raise AppException(TRADE_COUPON_EXPIRED, "优惠券未到使用时间")
        if c.get("valid_to") and c["valid_to"] < now:
            raise AppException(TRADE_COUPON_EXPIRED, "优惠券已过期")
        # 门槛校验：total >= threshold_amount 才可用
        threshold = float(c.get("threshold_amount") or 0)
        if total_amount < threshold:
            raise AppException(TRADE_COUPON_EXPIRED, f"未达使用门槛（需满 {threshold:.2f}）")
        discount_amount = _compute_discount(c["coupon_type"], c, total_amount)
        if discount_amount >= total_amount:
            discount_amount = total_amount
        coupon_receive_record_id = coupon_id

    payable_amount = total_amount - discount_amount
    student_id = await _order_repo.resolve_student_id(user_id)
    user_id_int = int(user_id)
    cohort_id_int = int(cohort_id)
    institution_id_int = int(institution_id)
    now = datetime.now()

    order_no = None
    order_id = None
    try:
        async with transaction() as (conn, cur):
            # 余位占用（条件更新防超卖，0 行=满员）
            affected = await _order_write.occupy_seat(cur=cur, cohort_id=cohort_id_int)
            if affected == 0:
                raise AppException(TRADE_COUPON_EXHAUSTED, "该班次已满员")
            # 生成 order_no，写 order + order_item
            order_no = _order_write.new_order_no(institution_id_int)
            order_id = await _order_write.create_order(
                conn=conn, cur=cur, institution_id=institution_id_int,
                student_id=student_id, order_no=order_no, user_id=user_id_int,
                coupon_receive_record_id=coupon_receive_record_id,
                total_amount=total_amount, discount_amount=discount_amount, payable_amount=payable_amount,
                cohort_id=cohort_id_int, cohort_name=cohort.get("cohort_name") or f"班次{cohort_id_int}",
                service_period_days=DEFAULT_SERVICE_PERIOD_DAYS, now=now,
            )
            # 券核销
            if coupon_receive_record_id is not None:
                await _order_write.mark_coupon_used(cur=cur, receive_record_id=coupon_receive_record_id, now=now)
    except AppException:
        raise  # 业务异常（满员/券问题）——事务已回滚
    except Exception as exc:
        # 唯一键冲突（order_no 相同，幂等）→ 回查原单
        if _is_duplicate_key(exc):
            logger.warning("[order] order_no 唯一键冲突，回查原单（语义幂等）")
            existing = await _order_write.get_order(order_no, user_id_int) if order_no else None
            if existing is not None:
                return await _assemble_order(existing)
        logger.exception("[order] 下单事务失败：%s", exc)
        raise

    # 幂等返回：重查落库订单
    if order_no is not None:
        fresh = await _order_write.get_order(order_no, user_id_int)
        if fresh is not None:
            return await _assemble_order(fresh)
    raise AppException(TRADE_ORDER_NOT_FOUND, "订单创建失败，请重试")


def _compute_discount(coupon_type: str, c: dict, total: float) -> float:
    """服务端重算券折扣：cash/trial/gift → discount_amount；discount → discount_rate×total。"""
    if coupon_type == "discount":
        rate = float(c.get("discount_rate") or 0)
        if rate <= 0:
            return 0.0
        return round(total * (1 - rate), 2)
    return float(c.get("discount_amount") or 0)


async def _assemble_order(order_row: dict, *, detail: bool = False) -> Order:
    """聚合订单（列表：查 cohort/series 标题/cohort_id；详情：+items/payments）。"""
    order_id = int(order_row["id"])
    itm = await _order_write.get_order_item_for_order(order_id)
    cohort_id = itm.get("cohort_id") if itm else None
    series = await _order_write.get_order_series(order_id) if (itm is not None or detail) else None
    series_id = series.get("series_id") if series else None
    series_title = series.get("series_name") if series else None
    cohort_id_coerced = int(cohort_id) if cohort_id else None
    order = _order_from_row(
        order_row,
        series_title=series_title,
        cohort_id=cohort_id_coerced,
    )
    if series_id:
        order.series_id = int(series_id)
    if detail:
        order.items = [_order_item_from_row(itm)] if itm else []
        order.payments = await _load_payments(order_id)
    return order


def _order_item_from_row(itm: dict) -> OrderItem:
    return OrderItem(
        order_item_id=int(itm.get("id") or 0),
        cohort_id=int(itm.get("cohort_id") or 0),
        item_name=itm.get("item_name") or "",
        unit_price=float(itm.get("unit_price") or 0),
        discount_amount=float(itm.get("discount_amount") or 0),
        payable_amount=float(itm.get("payable_amount") or 0),
        order_item_status=itm.get("order_item_status") or "pending",
    )


async def _load_payments(order_id: int) -> list:
    from app.database import fetch_all
    rows = await fetch_all(
        "SELECT payment_no, payment_channel, payment_status, amount, paid_at"
        " FROM payment_record WHERE order_id=%s ORDER BY id ASC",
        (order_id,),
    )
    return [PaymentItem(
        payment_no=r["payment_no"], payment_channel=r["payment_channel"],
        payment_status=r["payment_status"], amount=float(r.get("amount") or 0),
        paid_at=r.get("paid_at"),
    ) for r in rows]


# ═══════════════════════════════════════════════════════
# 订单列表 / 详情
# ═══════════════════════════════════════════════════════
async def list_orders(user_id: int, *, order_status: str | None = None, refundable: bool = False,
                      page: int = 1, page_size: int = 20) -> OrderPage:
    """订单分页（status 过滤 / refundable 过滤 + 分页）。order_status 须在白名单。"""
    if order_status and order_status not in VALID_ORDER_STATUS:
        raise AppException("42200", f"非法订单状态：{order_status}")
    if refundable:
        order_status = None  # refundable 走多值（可退款状态集）
        rows, total = await _order_write.list_orders(
            user_id, order_status=None, refundable=True, page=page, page_size=page_size,
        )
    else:
        rows, total = await _order_write.list_orders(
            user_id, order_status=order_status, page=page, page_size=page_size,
        )
    items = [await _assemble_order(r) for r in rows]
    return OrderPage(total=total, page=page, page_size=page_size, items=items)


async def get_order_detail(user_id: int, order_no: str) -> Order:
    """订单详情（GWT②：含 items + payments 嵌套）。"""
    row = await _order_write.get_order(order_no, user_id)
    if row is None:
        raise AppException(TRADE_ORDER_NOT_FOUND, "订单不存在")
    return await _assemble_order(row, detail=True)


async def cancel_order(user_id: int, order_no: str) -> OrderCancelResult:
    """取消订单（仅 pending）：券回滚 unused + 班次余位释放。单事务。
    状态机条件更新（WHERE order_status='pending'）→ 幂等；paid 单取消 → 409 冲突。"""
    row = await _order_write.get_order(order_no, user_id)
    if row is None:
        raise AppException(TRADE_ORDER_NOT_FOUND, "订单不存在")
    order_id = int(row["id"])
    coupon_receive_record_id = row.get("coupon_receive_record_id")
    cohort_id = None

    # 取 cohort_id（取消后需释放余位）
    itm = await _order_write.get_order_item_for_order(order_id)
    if itm is not None:
        cohort_id = int(itm["cohort_id"])

    now = datetime.now()
    try:
        async with transaction() as (conn, cur):
            # 状态机条件更新（幂等三层第 3 层）：仅 pending → cancelled
            await cur.execute(
                "UPDATE `order` SET order_status='cancelled', cancel_at=%s, updated_at=%s"
                " WHERE order_no=%s AND user_id=%s AND order_status='pending'",
                (now, now, order_no, int(user_id)),
            )
            if cur.rowcount == 0:
                # 未更新：校验当前状态决定幂等 or 非法迁移
                cur_status = row["order_status"]
                if cur_status == "cancelled":
                    return OrderCancelResult(cancelled=True, order_no=order_no)  # 幂等
                # paid/completed/… → 非法状态迁移（409 冲突；code 语义=订单状态不允许操作）
                raise AppException(TRADE_ORDER_STATUS_INVALID, f"订单状态 {cur_status} 不允许取消", http_status=409)
            # 释放班次余位
            if cohort_id is not None:
                await _order_write.release_seat(cur=cur, cohort_id=cohort_id)
            # 券回滚 unused
            if coupon_receive_record_id is not None:
                await _order_write.rollback_coupon(cur=cur, receive_record_id=int(coupon_receive_record_id), now=now)
    except AppException:
        raise
    except Exception as exc:
        logger.exception("[order] 取消订单事务失败：%s", exc)
        raise AppException(TRADE_ORDER_STATUS_INVALID, "订单取消失败，请稍后重试")

    return OrderCancelResult(cancelled=True, order_no=order_no)


def _is_duplicate_key(exc: Exception) -> bool:
    """判断数据库唯一键冲突（asyncmy/pymysql IntegrityError：errno 1062）。"""
    msg = str(exc)
    return "1062" in msg or "Duplicate entry" in msg or "duplicate" in msg.lower()