# -*- coding: utf-8 -*-
"""trade/order 域 repository：班次/券/学生 profile 校验 + order/order_item 读写。

资金安全红线（task17 hard）：
- amount 服务端重算：只信任 series_cohort.sale_price / 券面额，绝不信任客户端价格
- `order` 是 MySQL 保留字，所有 SQL 用反引号 `` `order` ``
- order_no（institution_id, order_no）唯一键 → 唯一键冲突回查返回原单（语义幂等）
"""
from __future__ import annotations

import uuid
from datetime import datetime

from app.database import fetch_all, fetch_one


class OrderRepo:
    """只读/单语句查询（跨表聚合用 fetch_all/fetch_one）。"""

    async def get_cohort(self, cohort_id: int) -> dict | None:
        """班次 + 关联系列标题（on_sale）。"""
        return await fetch_one(
            "SELECT c.id AS cohort_id, c.institution_id, c.series_id, c.cohort_name,"
            " c.sale_price, c.max_student_count, c.current_student_count, c.yn,"
            " s.series_name, s.sale_status AS series_sale_status"
            " FROM series_cohort c JOIN series s ON s.id = c.series_id"
            " WHERE c.id = %s LIMIT 1",
            (cohort_id,),
        )

    async def get_coupon_for_receive(self, receive_record_id: int, user_id: int) -> dict | None:
        """领券记录 + 券面额（校验归属 + 未使用 + 未过期）。"""
        return await fetch_one(
            "SELECT r.id AS receive_record_id, r.coupon_id, r.receive_status, r.expired_at,"
            " c.coupon_type, c.discount_amount, c.discount_rate, c.threshold_amount,"
            " c.valid_from, c.valid_to"
            " FROM coupon_receive_record r JOIN coupon c ON c.id = r.coupon_id"
            " WHERE r.id = %s AND r.user_id = %s AND r.yn = 1 LIMIT 1",
            (receive_record_id, user_id),
        )

    async def resolve_student_id(self, user_id: int) -> int:
        """取真实 student_profile.id；不存在自动建最小档案（对齐 task14 模式）。"""
        row = await fetch_one(
            "SELECT id FROM student_profile WHERE user_id=%(uid)s AND yn=1 LIMIT 1",
            {"uid": user_id},
        )
        if row:
            return int(row["id"])
        from app.database import execute_write
        sid = await execute_write(
            "INSERT INTO student_profile (user_id, learner_identity_id, learning_goal_id, yn, created_at, updated_at)"
            " VALUES (%(uid)s, 1, 1, 1, NOW(), NOW())",
            {"uid": user_id},
        )
        return int(sid)


class OrderWriteRepo:
    """事务内下单/取消（order + order_item + 券核销 + 余位）。"""

    @staticmethod
    def new_order_no(institution_id: int) -> str:
        """生成唯一 order_no：`{institution}-{yymmddHHMMSS}-{uuid6}`."""
        return f"{institution_id}-{datetime.now().strftime('%y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    async def create_order(
        self, *, conn, cur, institution_id: int, student_id: int,
        order_no: str, user_id: int, coupon_receive_record_id: int | None,
        total_amount: float, discount_amount: float, payable_amount: float,
        cohort_id: int, cohort_name: str, service_period_days: int, now: datetime,
    ) -> int:
        """事务内 INSERT order + order_item，返回 order id。"""
        await cur.execute(
            "INSERT INTO `order` (institution_id, order_no, user_id, student_id,"
            " coupon_receive_record_id, order_status, total_amount, discount_amount,"
            " payable_amount, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s)",
            (institution_id, order_no, user_id, student_id,
             coupon_receive_record_id, total_amount, discount_amount, payable_amount,
             now, now),
        )
        order_id = int(cur.lastrowid)
        await cur.execute(
            "INSERT INTO order_item (institution_id, order_id, user_id, student_id,"
            " cohort_id, order_item_status, item_name, unit_price, discount_amount,"
            " payable_amount, service_period_days, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s)",
            (institution_id, order_id, user_id, student_id, cohort_id,
             cohort_name, total_amount, discount_amount, payable_amount,
             service_period_days, now, now),
        )
        return order_id

    async def mark_coupon_used(self, *, cur, receive_record_id: int, now: datetime) -> None:
        """券核销：receive_status 'unused' → 'used'（状态机条件更新，幂等）。"""
        await cur.execute(
            "UPDATE coupon_receive_record SET receive_status='used', used_at=%s, updated_at=%s"
            " WHERE id=%s AND receive_status='unused'",
            (now, now, receive_record_id),
        )

    async def rollback_coupon(self, *, cur, receive_record_id: int, now: datetime) -> None:
        """券回滚：receive_status 'used' → 'unused'，清 used_at（取消订单）。"""
        await cur.execute(
            "UPDATE coupon_receive_record SET receive_status='unused', used_at=NULL, updated_at=%s"
            " WHERE id=%s AND receive_status='used'",
            (now, receive_record_id),
        )

    async def occupy_seat(self, *, cur, cohort_id: int) -> int:
        """班次余位占用：current_student_count +1（条件更新防超卖）。返回受影响行数。"""
        await cur.execute(
            "UPDATE series_cohort SET current_student_count = current_student_count + 1, updated_at=NOW()"
            " WHERE id=%s AND current_student_count < max_student_count",
            (cohort_id,),
        )
        return int(cur.rowcount)

    async def release_seat(self, *, cur, cohort_id: int) -> None:
        """班次余位释放：current_student_count -1（取消订单）。"""
        await cur.execute(
            "UPDATE series_cohort SET current_student_count = GREATEST(0, current_student_count - 1), updated_at=NOW()"
            " WHERE id=%s",
            (cohort_id,),
        )

    async def get_order(self, order_no: str, user_id: int) -> dict | None:
        """查订单（归属校验）。"""
        return await fetch_one(
            "SELECT id, institution_id, order_no, user_id, student_id, coupon_receive_record_id,"
            " order_status, total_amount, discount_amount, payable_amount, paid_amount,"
            " cancel_at, paid_at, created_at, updated_at"
            " FROM `order` WHERE order_no=%s AND user_id=%s LIMIT 1",
            (order_no, user_id),
        )

    async def get_order_item_for_order(self, order_id: int) -> dict | None:
        """查订单明细（取 id/cohort_id/item_name 用于聚合）。"""
        return await fetch_one(
            "SELECT id, order_id, cohort_id, item_name, unit_price, discount_amount,"
            " payable_amount, order_item_status FROM order_item WHERE order_id=%s LIMIT 1",
            (order_id,),
        )

    async def get_order_series(self, order_id: int) -> dict | None:
        """经 order_item → series_cohort → series 取系列标题。"""
        return await fetch_one(
            "SELECT s.id AS series_id, s.series_name"
            " FROM order_item oi"
            " JOIN series_cohort c ON c.id = oi.cohort_id"
            " JOIN series s ON s.id = c.series_id"
            " WHERE oi.order_id=%s LIMIT 1",
            (order_id,),
        )

    async def list_orders(
        self, user_id: int, *, order_status: str | None = None, refundable: bool = False,
        page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """订单分页（status 过滤 / refundable 过滤 + 系列标题聚合）。"""
        where = ["o.user_id=%s"]
        args: list = [user_id]
        if order_status:
            where.append("o.order_status=%s")
            args.append(order_status)
        elif refundable:
            # 可退款状态集：已支付/已完成/部分退款（pending 未支付不可退，cancelled/refunded 已终态）
            where.append("o.order_status IN ('paid','completed','partial_refunded')")
        base = f" FROM `order` o WHERE {' AND '.join(where)}"
        cnt = await fetch_one(f"SELECT COUNT(*) AS c {base}", tuple(args))
        total = int(cnt["c"]) if cnt else 0
        rows = await fetch_all(
            "SELECT o.id, o.institution_id, o.order_no, o.user_id, o.coupon_receive_record_id,"
            " o.order_status, o.total_amount, o.discount_amount, o.payable_amount,"
            " o.paid_at, o.cancel_at, o.created_at,"
            " (SELECT co.series_id FROM order_item oi"
            "   JOIN series_cohort co ON co.id=oi.cohort_id WHERE oi.order_id=o.id LIMIT 1) AS series_id,"
            " (SELECT s.series_name FROM order_item oi"
            "   JOIN series_cohort co ON co.id=oi.cohort_id"
            "   JOIN series s ON s.id=co.series_id WHERE oi.order_id=o.id LIMIT 1) AS series_name,"
            " (SELECT oi.cohort_id FROM order_item oi WHERE oi.order_id=o.id LIMIT 1) AS cohort_id"
            f"{base} ORDER BY o.id DESC LIMIT %s OFFSET %s",
            tuple(args + [page_size, (page - 1) * page_size]),
        )
        return rows, total