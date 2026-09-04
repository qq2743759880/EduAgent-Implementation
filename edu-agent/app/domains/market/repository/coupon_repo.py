# -*- coding: utf-8 -*-
"""优惠券仓储：coupon / coupon_receive_record。

防超发核心（GWT①）：
- 条件更新：`UPDATE coupon SET receive_count=receive_count+1 WHERE id=? AND receive_count<total_count`
  （受影响行数=0 → 已领完 → 不写 receive_record）
- receive_no 唯一键 uk_coupon_receive_record_no：幂等三层纵深，同一 receive_no 重复 INSERT 被 DB 拒绝
- 领券全程事务：条件更新 + 写记录同一连接原子提交
"""
from __future__ import annotations

import uuid
from datetime import datetime

from app.database import fetch_all, fetch_one, transaction


class CouponRepo:
    """coupon / coupon_receive_record 仓储。"""

    # ---------------- 读 ----------------

    async def get_coupon(self, coupon_id: int) -> dict | None:
        """按主键取券模板（yn=1）。"""
        return await fetch_one(
            "SELECT id, coupon_name, coupon_type, discount_amount, discount_rate,"
            " threshold_amount, total_count, per_user_limit, receive_count,"
            " valid_from, valid_to"
            " FROM coupon WHERE id = %s AND yn = 1 LIMIT 1",
            (coupon_id,),
        )

    async def list_templates(self, series_id: int | None = None) -> list[dict]:
        """
        可领券模板列表。
        - series_id 为空 → 全部 yn=1 券
        - series_id 非空 → 经 coupon_series_rel 过滤出该系列适用券
        """
        if series_id is not None:
            return await fetch_all(
                "SELECT c.id, c.coupon_name, c.coupon_type, c.discount_amount,"
                " c.discount_rate, c.threshold_amount, c.total_count,"
                " c.per_user_limit, c.receive_count, c.valid_from, c.valid_to"
                " FROM coupon c"
                " JOIN coupon_series_rel r ON r.coupon_id = c.id AND r.series_id = %s"
                " WHERE c.yn = 1 ORDER BY c.id ASC",
                (series_id,),
            )
        return await fetch_all(
            "SELECT id, coupon_name, coupon_type, discount_amount, discount_rate,"
            " threshold_amount, total_count, per_user_limit, receive_count,"
            " valid_from, valid_to FROM coupon WHERE yn = 1 ORDER BY id ASC",
        )

    async def list_my_coupons(
        self, user_id: int, *, status: str | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """
        我的券列表（coupon_receive_record JOIN coupon）。
        status ∈ {unused, used, expired} 过滤（GWT②：含过期时间）。
        """
        where = ["r.user_id = %s", "r.yn = 1"]
        args: list = [user_id]
        if status:
            # 逻辑 expired：券已过期（valid_to < NOW()）且未使用时按 expired 展示
            if status == "expired":
                where.append("r.receive_status = 'unused' AND c.valid_to < NOW()")
            else:
                where.append("(r.receive_status = %s OR (r.receive_status='unused' AND %s='used' AND r.used_at IS NOT NULL))")
                args.extend([status, status])

        base = (
            " FROM coupon_receive_record r"
            " JOIN coupon c ON c.id = r.coupon_id"
            f" WHERE {' AND '.join(where)}"
        )
        cnt = await fetch_one(f"SELECT COUNT(*) AS c {base}", tuple(args))
        total = int(cnt["c"]) if cnt else 0
        rows = await fetch_all(
            "SELECT r.id AS receive_record_id, r.coupon_id, r.user_id, r.receive_no,"
            " r.receive_status, r.received_at, r.used_at, r.expired_at,"
            " c.coupon_name, c.coupon_type, c.discount_amount, c.discount_rate,"
            " c.threshold_amount, c.valid_from, c.valid_to, c.total_count"
            f"{base} ORDER BY r.id DESC LIMIT %s OFFSET %s",
            tuple(args + [page_size, (page - 1) * page_size]),
        )
        return rows, total

    async def get_my_coupon(self, coupon_id: int, user_id: int) -> dict | None:
        """按券模板 id + 用户查已有领券记录（幂等判重：已领则返回原记录）。"""
        return await fetch_one(
            "SELECT r.id AS receive_record_id, r.coupon_id, r.user_id, r.receive_no,"
            " r.receive_status, r.received_at, r.used_at, r.expired_at,"
            " c.coupon_name, c.coupon_type, c.discount_amount, c.discount_rate,"
            " c.threshold_amount, c.valid_from, c.valid_to, c.total_count"
            " FROM coupon_receive_record r JOIN coupon c ON c.id = r.coupon_id"
            " WHERE r.coupon_id = %s AND r.user_id = %s AND r.yn = 1 LIMIT 1",
            (coupon_id, user_id),
        )

    # ---------------- 写（防超发：事务内条件更新 + 唯一键） ----------------

    @staticmethod
    def _new_receive_no(coupon_id: int, user_id: int) -> str:
        """生成唯一 receive_no：`{coupon}-{user}-{uuid8}`，命中 uk 唯一键。"""
        return f"{coupon_id}-{user_id}-{uuid.uuid4().hex[:8]}"

    async def receive_in_transaction(
        self, *, coupon_id: int, user_id: int, receive_source: str, expired_at: datetime, now: datetime,
    ) -> dict:
        """
        事务内完成「条件更新 + 写记录」，保证额度与记录原子；防超发。
        返回 {created, receive_no, receive_record_id}。
        - created=False：条件更新 0 行 → 券已领完（占位不产生记录）
        - 唯一键冲突（并发重复 receive_no）→ 依赖调用方捕获 pymysql IntegrityError 做幂等返回
        """
        receive_no = self._new_receive_no(coupon_id, user_id)
        async with transaction() as (conn, cur):
            await cur.execute(
                "UPDATE coupon SET receive_count = receive_count + 1"
                " WHERE id = %s AND receive_count < total_count AND yn = 1",
                (coupon_id,),
            )
            if cur.rowcount == 0:
                await conn.rollback()
                return {"created": False, "receive_no": None, "receive_record_id": None}
            await cur.execute(
                "INSERT INTO coupon_receive_record"
                " (coupon_id, user_id, receive_no, receive_source, receive_status,"
                "  yn, received_at, expired_at, created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, 'unused', 1, %s, %s, %s, %s)",
                (coupon_id, user_id, receive_no, receive_source, now, expired_at, now, now),
            )
            record_id = int(cur.lastrowid)
        return {"created": True, "receive_no": receive_no, "receive_record_id": record_id}