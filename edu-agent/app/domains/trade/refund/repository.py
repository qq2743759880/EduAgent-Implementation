# -*- coding: utf-8 -*-
"""trade/refund 域 repository：refund_request 读写 + 退款单事务。

资金安全红线（task19 hard）：
- 金额服务端强制校验：申请金额 ≤ 实付（订单有效 / 实际 paid 支付），绝不信任前端（GWT①）
- 幂等：refund_no（institution_id, refund_no）唯一键 + 同订单已有 pending 退款单则复用（业务幂等）
- 状态机条件更新：仅 pending 可撤销/审批（GWT②）；审批用条件更新幂等
- refund_request 表 `order` 无关，但 order_item/payment 均为 NOT NULL（联表取真实 id）
"""
from __future__ import annotations

import uuid
from datetime import datetime

from app.database import fetch_all, fetch_one, execute_write


class RefundRepo:
    """只读/单语句查询。"""

    async def get_order_for_refund(self, order_no: str, user_id: int) -> dict | None:
        """取可退款订单（paid/completed/partial_refunded + paid 支付 + order_item）。
        返回：order_id/order_item_id/payment_id/institution_id/student_id/payable_amount/paid_amount/order_status。"""
        return await fetch_one(
            "SELECT o.id AS order_id, o.institution_id, o.user_id, o.student_id,"
            " o.order_status, o.payable_amount, o.paid_amount,"
            " oi.id AS order_item_id,"
            " (SELECT MIN(p.id) FROM payment_record p WHERE p.order_id=o.id AND p.payment_status='paid') AS payment_id,"
            " (SELECT COALESCE(SUM(p.amount),0) FROM payment_record p WHERE p.order_id=o.id AND p.payment_status='paid') AS paid_total"
            " FROM `order` o JOIN order_item oi ON oi.order_id=o.id"
            " WHERE o.order_no=%s AND o.user_id=%s ORDER BY oi.id ASC LIMIT 1",
            (order_no, int(user_id)),
        )

    async def get_refund(self, refund_id: int, user_id: int | None = None) -> dict | None:
        """按 id 查退款单（+ 订单号聚合并联）。user_id 空=管理端（不校验归属）。"""
        where = "r.id=%s"
        args: list = [refund_id]
        if user_id is not None:
            where += " AND r.user_id=%s"
            args.append(int(user_id))
        return await fetch_one(
            "SELECT r.id, r.institution_id, r.refund_no, r.order_id, r.order_item_id, r.payment_id,"
            " r.user_id, r.student_id, r.refund_type, r.refund_reason, r.refund_status,"
            " r.apply_amount, r.approved_amount, r.approver_user_id, r.remark, r.yn,"
            " r.applied_at, r.approved_at, r.refunded_at, r.created_at, r.updated_at,"
            " o.order_no"
            f" FROM refund_request r JOIN `order` o ON o.id=r.order_id WHERE {where} LIMIT 1",
            tuple(args),
        )

    async def get_pending_refund_by_order(self, order_id: int, user_id: int) -> dict | None:
        """同订单已有 pending 退款单则返回（业务幂等：防重复申请）。"""
        return await fetch_one(
            "SELECT id FROM refund_request WHERE order_id=%s AND user_id=%s AND refund_status='pending' AND yn=1 LIMIT 1",
            (order_id, int(user_id)),
        )

    async def list_refunds(
        self, user_id: int, *, refund_status: str | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """我的退款（倒序，默认仅非撤销 yn=1）。"""
        where = ["r.user_id=%s", "r.yn=1"]
        args: list = [int(user_id)]
        if refund_status:
            where.append("r.refund_status=%s")
            args.append(refund_status)
        base = (" FROM refund_request r JOIN `order` o ON o.id=r.order_id"
                f" WHERE {' AND '.join(where)}")
        cnt = await fetch_one(f"SELECT COUNT(*) c {base}", tuple(args))
        total = int(cnt["c"]) if cnt else 0
        rows = await fetch_all(
            "SELECT r.id, r.refund_no, r.order_id, r.refund_type, r.refund_reason, r.refund_status,"
            " r.apply_amount, r.approved_amount, r.approver_user_id, r.remark, r.yn,"
            " r.applied_at, r.approved_at, r.refunded_at, r.created_at,"
            " o.order_no"
            f"{base} ORDER BY r.id DESC LIMIT %s OFFSET %s",
            tuple(args + [page_size, (page - 1) * page_size]),
        )
        return rows, total

    async def list_refunds_admin(
        self, *, refund_status: str | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """管理端退款列表（过渡 stub，HITL 上线前可查全部）。"""
        where = ["r.yn=1"]
        args: list = []
        if refund_status:
            where.append("r.refund_status=%s")
            args.append(refund_status)
        base = " FROM refund_request r JOIN `order` o ON o.id=r.order_id WHERE " + " AND ".join(where)
        cnt = await fetch_one(f"SELECT COUNT(*) c {base}", tuple(args))
        total = int(cnt["c"]) if cnt else 0
        rows = await fetch_all(
            "SELECT r.id, r.refund_no, r.order_id, r.refund_type, r.refund_reason, r.refund_status,"
            " r.apply_amount, r.approved_amount, r.approver_user_id, r.remark, r.yn,"
            " r.applied_at, r.approved_at, r.refunded_at, r.created_at, o.order_no"
            f"{base} ORDER BY r.id DESC LIMIT %s OFFSET %s",
            tuple(args + [page_size, (page - 1) * page_size]),
        )
        return rows, total


class RefundWriteRepo:
    """事务内写：申请 / 撤销 / 审批。"""

    @staticmethod
    def new_refund_no(institution_id: int) -> str:
        """生成唯一 refund_no：`{institution}-{yymmddHHMMSS}-{uuid6}`（(institution_id, refund_no) 唯一键）。"""
        return f"{institution_id}-{datetime.now().strftime('%y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    async def create_refund(
        self, *, conn, cur, institution_id: int, order_id: int, order_item_id: int, payment_id: int,
        user_id: int, student_id: int, refund_no: str, refund_type: str, refund_reason: str,
        apply_amount: float, now: datetime,
    ) -> int:
        """事务内 INSERT refund_request（pending），返回 id。"""
        await cur.execute(
            "INSERT INTO refund_request (institution_id, refund_no, order_id, order_item_id, payment_id,"
            " user_id, student_id, refund_type, refund_reason, refund_status, apply_amount,"
            " yn, applied_at, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, 1, %s, %s, %s)",
            (institution_id, refund_no, order_id, order_item_id, payment_id,
             int(user_id), int(student_id), refund_type, refund_reason, apply_amount,
             now, now, now),
        )
        return int(cur.lastrowid)

    async def cancel_refund(self, *, conn, cur, refund_id: int, user_id: int, now: datetime) -> int:
        """撤销（仅 pending）：条件更新 yn=1→0 幂等（GWT②）。0 行=非 pending 或已撤销。"""
        await cur.execute(
            "UPDATE refund_request SET yn=0, updated_at=%s WHERE id=%s AND user_id=%s"
            " AND refund_status='pending' AND yn=1",
            (now, refund_id, int(user_id)),
        )
        return int(cur.rowcount) if cur.rowcount else 0

    async def approve_refund(
        self, *, conn, cur, refund_id: int, approver_user_id: int, approved_amount: float,
        remark: str | None, now: datetime,
    ) -> int:
        """审批通过（HITL stub，task28 替换为 LangGraph interrupt）：pending → approved。"""
        await cur.execute(
            "UPDATE refund_request SET refund_status='approved', approved_amount=%s,"
            " approver_user_id=%s, remark=%s, approved_at=%s, updated_at=%s"
            " WHERE id=%s AND refund_status='pending' AND yn=1",
            (approved_amount, approver_user_id, remark, now, now, refund_id),
        )
        return int(cur.rowcount) if cur.rowcount else 0

    async def approve_and_refund(
        self, *, conn, cur, refund_id: int, order_id: int, order_item_id: int,
        approver_user_id: int | None, approved_amount: float, refund_amount: float,
        remark: str | None, now: datetime,
    ) -> int:
        """HITL 审批通过并**原子执行退款**（task28 GWT②）：refund→refunded + order→refunded + student_cohort_rel→refunded。

        单事务三表条件更新；refund 行 `WHERE refund_status='pending'` 幂等（0 行 = 非 pending / 已处理）。
        资金安全红线：此处仅在事务内写，金额校验在 service/apply 层服务端强制（≤ 实付，禁信任前端）。
        """
        await cur.execute(
            "UPDATE refund_request SET refund_status='refunded', approved_amount=%s,"
            " approver_user_id=%s, remark=%s, approved_at=%s, refunded_at=%s, updated_at=%s"
            " WHERE id=%s AND refund_status='pending' AND yn=1",
            (approved_amount, approver_user_id, remark, now, now, now, refund_id),
        )
        affected = int(cur.rowcount) if cur.rowcount else 0
        if affected == 0:
            return 0  # 非 pending / 已处理：不继续写 order/cohort（不扩散）
        await cur.execute(
            "UPDATE `order` SET order_status='refunded', refund_amount=%s, updated_at=%s"
            " WHERE id=%s",
            (refund_amount, now, order_id),
        )
        await cur.execute(
            "UPDATE student_cohort_rel SET enroll_status='refunded', updated_at=%s"
            " WHERE order_item_id=%s AND enroll_status <> 'refunded'",
            (now, order_item_id),
        )
        return affected

    async def reject_refund(
        self, *, conn, cur, refund_id: int, approver_user_id: int, remark: str | None, now: datetime,
    ) -> int:
        """审批拒绝（HITL stub）：pending → rejected + approver remark（GWT③）。"""
        await cur.execute(
            "UPDATE refund_request SET refund_status='rejected', approver_user_id=%s,"
            " remark=%s, approved_at=%s, updated_at=%s"
            " WHERE id=%s AND refund_status='pending' AND yn=1",
            (approver_user_id, remark, now, now, refund_id),
        )
        return int(cur.rowcount) if cur.rowcount else 0