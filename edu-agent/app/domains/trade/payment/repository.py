# -*- coding: utf-8 -*-
"""trade/payment 域 repository：payment_record 读写 + 支付成功单事务（三表原子一致）。

资金安全红线（task18 hard）：
- 回调幂等：payment_no（institution_id, payment_no）唯一键 + `WHERE payment_status='pending'` 条件更新
- 回调成功单事务：payment paid + order paid + student_cohort_rel active + 券 used 原子一致（GWT②）
- 对账无重复入账（GWT④）
"""
from __future__ import annotations

import uuid
from datetime import datetime

from app.database import fetch_all, fetch_one, transaction


class PaymentRepo:
    """只读/单语句查询。"""

    async def get_payment(self, payment_no: str) -> dict | None:
        """按 payment_no 查支付记录（含订单号聚合）。"""
        return await fetch_one(
            "SELECT p.id, p.institution_id, p.payment_no, p.order_id, p.payment_channel,"
            " p.payment_status, p.amount, p.third_party_trade_no, p.paid_at, p.refund_at,"
            " p.created_at, p.updated_at, o.order_no, o.order_status, o.payable_amount"
            " FROM payment_record p JOIN `order` o ON o.id = p.order_id"
            " WHERE p.payment_no = %s LIMIT 1",
            (payment_no,),
        )

    async def get_payment_by_order(self, order_id: int, user_ok: bool = True) -> list[dict]:
        """按订单查支付记录（列表）。"""
        return await fetch_all(
            "SELECT id, institution_id, payment_no, order_id, payment_channel, payment_status,"
            " amount, third_party_trade_no, paid_at, refund_at, created_at, updated_at"
            " FROM payment_record WHERE order_id=%s ORDER BY id ASC",
            (order_id,),
        )

    async def get_order_for_payment(self, order_no: str) -> dict | None:
        """按 order_no 查订单（发起支付需订单存在且 pending）。"""
        return await fetch_one(
            "SELECT id, institution_id, order_no, user_id, student_id, coupon_receive_record_id,"
            " order_status, total_amount, discount_amount, payable_amount, paid_at"
            " FROM `order` WHERE order_no=%s LIMIT 1",
            (order_no,),
        )

    async def get_order_item_id(self, order_id: int) -> int | None:
        """取订单明细 id（报名联动 student_cohort_rel.order_item_id 唯一键）。"""
        row = await fetch_one(
            "SELECT id, cohort_id, student_id, institution_id FROM order_item WHERE order_id=%s LIMIT 1",
            (order_id,),
        )
        if row is None:
            return None
        return dict(row)

    async def list_payments(
        self, *, payment_status: str | None = None, order_no: str | None = None,
        page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """支付分页（status / order_no 过滤）。"""
        where = ["1=1"]
        args: list = []
        if payment_status:
            where.append("p.payment_status=%s")
            args.append(payment_status)
        if order_no:
            where.append("o.order_no=%s")
            args.append(order_no)
        base = (
            " FROM payment_record p JOIN `order` o ON o.id=p.order_id"
            f" WHERE {' AND '.join(where)}"
        )
        cnt = await fetch_one(f"SELECT COUNT(*) c {base}", tuple(args))
        total = int(cnt["c"]) if cnt else 0
        rows = await fetch_all(
            "SELECT p.id, p.payment_no, p.order_id, p.payment_channel, p.payment_status,"
            " p.amount, p.third_party_trade_no, p.paid_at, p.refund_at, p.created_at,"
            " o.order_no, o.payable_amount"
            f"{base} ORDER BY p.id DESC LIMIT %s OFFSET %s",
            tuple(args + [page_size, (page - 1) * page_size]),
        )
        return rows, total


class PaymentWriteRepo:
    """事务内发起支付 / 回调成功（三表原子） / 对账。"""

    @staticmethod
    def new_payment_no(institution_id: int) -> str:
        """生成唯一 payment_no：`{institution}-{yymmddHHMMSS}-{uuid6}`."""
        return f"P-{institution_id}-{datetime.now().strftime('%y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    async def create_payment(self, *, conn, cur, institution_id: int, order_id: int,
                             payment_no: str, pay_channel: str, amount: float, now: datetime) -> int:
        """事务内 INSERT payment_record（pending）。"""
        await cur.execute(
            "INSERT INTO payment_record (institution_id, order_id, payment_no, payment_channel,"
            " payment_status, amount, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s)",
            (institution_id, order_id, payment_no, pay_channel, amount, now, now),
        )
        return int(cur.lastrowid)

    async def settle_payment(
        self, *, conn, cur, payment_no: str, third_party_trade_no: str | None, now: datetime,
    ) -> dict:
        """
        回调成功单事务核心（GWT①②）：
        1. 条件更新 payment paid（WHERE payment_status='pending'）→ 幂等；0 行=已处理
        2. 仅当本次成功将该 payment 置为 paid → 联动 order paid + enroll active + 券 used
        """
        # 1) 幂等条件更新：仅 pending → paid
        await cur.execute(
            "UPDATE payment_record SET payment_status='paid', third_party_trade_no=%s, paid_at=%s, updated_at=%s"
            " WHERE payment_no=%s AND payment_status='pending'",
            (third_party_trade_no, now, now, payment_no),
        )
        if cur.rowcount == 0:
            # 唯一键/条件更新幂等：非 pending（已 paid/closed）→ 不重复生效
            await conn.rollback()
            return {"applied": False, "order_status_change": False}

        # 2) 查该 payment 对应订单（事务内读）
        await cur.execute(
            "SELECT p.order_id, p.amount, o.coupon_receive_record_id, o.order_status,"
            " o.student_id, o.institution_id, o.user_id"
            " FROM payment_record p JOIN `order` o ON o.id=p.order_id WHERE p.payment_no=%s",
            (payment_no,),
        )
        prow = await cur.fetchone()
        if prow is None:
            await conn.rollback()
            return {"applied": False, "order_status_change": False}
        # 事务内 raw cursor 返回 tuple → 按 description 列名转 dict
        prow = dict(zip([d[0] for d in cur.description], prow))
        order_id = int(prow["order_id"])
        coupon_rec_id = prow.get("coupon_receive_record_id")
        student_id = int(prow["student_id"])
        institution_id = int(prow["institution_id"])
        order_user_id = int(prow["user_id"])
        order_status = prow["order_status"]

        # 3) order pending → paid（条件更新幂等）
        await cur.execute(
            "UPDATE `order` SET order_status='paid', paid_at=%s, paid_amount=%s, updated_at=%s"
            " WHERE id=%s AND order_status='pending'",
            (now, prow["amount"], now, order_id),
        )
        order_changed = cur.rowcount > 0

        # D1（资金安全红线 R2）：payment 置 paid 必须与 order 置 paid 同成败。
        # 若订单已非 pending（被取消/他途改态）而联动失败，整笔回滚，callback 视为未生效（可重试）。
        if not order_changed:
            await conn.rollback()
            return {"applied": False, "order_status_change": False}

        # 取 order_item（报名联动 student_cohort_rel.order_item_id）
        await cur.execute(
            "SELECT id AS order_item_id, cohort_id, student_id, institution_id, user_id"
            " FROM order_item WHERE order_id=%s LIMIT 1", (order_id,),
        )
        oi = await cur.fetchone()
        if oi is not None and order_changed:
            oi = dict(zip([d[0] for d in cur.description], oi))
            order_item_id = int(oi["order_item_id"])
            cohort_id = int(oi["cohort_id"])
            stu_id = int(oi["student_id"])
            oi_institution = int(oi["institution_id"])
            # 报名联动：student_cohort_rel active（唯一键 order_item_id / (student_id, cohort_id)）
            # ON DUPLICATE（同学生同班次重复购买）→ 更新为 active 且 order_item_id 指向本次支付订单明细
            await cur.execute(
                "INSERT INTO student_cohort_rel (institution_id, user_id, student_id, cohort_id,"
                " order_item_id, enroll_status, enroll_at, created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s)"
                " ON DUPLICATE KEY UPDATE enroll_status='active', order_item_id=VALUES(order_item_id),"
                " enroll_at=VALUES(enroll_at), updated_at=VALUES(updated_at)",
                (oi_institution, order_user_id, stu_id, cohort_id,
                 order_item_id, now, now, now),
            )
            # 券核销 used（幂等）
            if coupon_rec_id is not None:
                await cur.execute(
                    "UPDATE coupon_receive_record SET receive_status='used', used_at=%s, updated_at=%s"
                    " WHERE id=%s AND receive_status='unused'",
                    (now, now, coupon_rec_id),
                )

        return {"applied": True, "order_status_change": order_changed}


    async def cancel_payment(self, *, conn, cur, payment_no: str, now: datetime) -> int:
        """取消支付：pending → closed（幂等；已 paid 不可取消）。"""
        await cur.execute(
            "UPDATE payment_record SET payment_status='closed', updated_at=%s"
            " WHERE payment_no=%s AND payment_status='pending'",
            (now, payment_no),
        )
        return int(cur.rowcount) if cur.rowcount else 0

    async def retry_payment(self, *, conn, cur, payment_no: str, now: datetime) -> int:
        """重试支付：closed/failed → pending 重新发起（模拟）。"""
        await cur.execute(
            "UPDATE payment_record SET payment_status='pending', updated_at=%s"
            " WHERE payment_no=%s AND payment_status IN ('closed','failed')",
            (now, payment_no),
        )
        return int(cur.rowcount) if cur.rowcount else 0


class PaymentReconcileRepo:
    """对账：比对 payment_record 与订单，找重复入账/金额不一致。"""

    async def run_reconcile(self, institution_id: int = 0) -> dict:
        """对账报告（GWT④）：统计 paid 支付 + 重复入账 + 金额不一致。"""
        # 全部 paid 支付
        if institution_id:
            paid = await fetch_all(
                "SELECT p.payment_no, p.order_id, p.amount, o.order_no, o.payable_amount, o.order_status"
                " FROM payment_record p JOIN `order` o ON o.id=p.order_id"
                " WHERE p.payment_status='paid' AND p.institution_id=%s",
                (institution_id,),
            )
        else:
            paid = await fetch_all(
                "SELECT p.payment_no, p.order_id, p.amount, o.order_no, o.payable_amount, o.order_status"
                " FROM payment_record p JOIN `order` o ON o.id=p.order_id WHERE p.payment_status='paid'",
            )

        def _cents(x) -> int:
            """金额转分（整数）：规避浮点尾差（0.1+0.05 求和 vs 0.15 直存）导致误报 AMOUNT_MISMATCH。
            对账金额比较一律用分单位整数，对齐支付平台"金额以分为单位"的资金口径。"""
            return round(float(x) * 100)

        anomalies: list[dict] = []
        order_amounts: dict[int, float] = {}
        payment_count_per_order: dict[int, int] = {}
        total_amount = 0.0
        for r in paid:
            oid = int(r["order_id"])
            amt = float(r["amount"])
            total_amount += amt
            payment_count_per_order[oid] = payment_count_per_order.get(oid, 0) + 1
            order_amounts[oid] = float(r["payable_amount"])
            # 金额不一致：payment.amount != order.payable_amount（退款除外）。
            # 用分单位整数比较，规避浮点尾差误报（critique round4 竞品对标修复）。
            if _cents(r["amount"]) != _cents(r["payable_amount"]) and r["order_status"] not in ("partial_refunded", "refunded"):
                anomalies.append({
                    "type": "AMOUNT_MISMATCH",
                    "payment_no": r["payment_no"],
                    "order_no": r["order_no"],
                    "pay_amount": amt,
                    "order_payable": float(r["payable_amount"]),
                })

        # 重复入账：同一订单 >1 笔 paid 支付
        for oid, cnt in payment_count_per_order.items():
            if cnt > 1:
                anomalies.append({
                    "type": "DUPLICATE_PAYMENT",
                    "order_id": oid,
                    "paid_payments": cnt,
                })

        return {
            "total_paid_payments": len(paid),
            "total_reconciled_orders": len(order_amounts),
            "reconciled_amount": round(total_amount, 2),
            "anomalies": anomalies,
            "ok": len(anomalies) == 0,
        }