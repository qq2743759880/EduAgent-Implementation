# -*- coding: utf-8 -*-
"""after_sales/ticket 域 repository（task22 契约⑫）。

资金/安全红线：
- user_id 隔离：详情/列表按 st.user_id 过滤；越权 → 404（GWT②）；管理员可见全部
- 满意度幂等：service_ticket_satisfaction_survey.ticket_id 唯一，重复评分 → submitted=False 不改写（GWT③）
- ticket_no 唯一键 (institution_id, ticket_no)；first_response_at 空 = 等待受理态（GWT①）
- service_ticket.order_item_id NOT NULL+FK → 从 order_no 或该用户最近 order_item 解析
"""
from __future__ import annotations

import uuid
from datetime import datetime

from app.database import fetch_all, fetch_one


class TicketRepo:
    """只读查询。"""

    async def resolve_order_item(self, user_id: int, order_no: str | None) -> dict | None:
        """从 order_no 或该用户最近订单解析 order_item（service_ticket.order_item_id NOT NULL）。"""
        if order_no:
            return await fetch_one(
                "SELECT oi.id AS order_item_id, o.id AS order_id, o.order_no, o.institution_id"
                " FROM `order` o JOIN order_item oi ON oi.order_id = o.id"
                " WHERE o.order_no=%s AND o.user_id=%s LIMIT 1",
                (order_no, int(user_id)),
            )
        return await fetch_one(
            "SELECT oi.id AS order_item_id, o.id AS order_id, o.order_no, o.institution_id"
            " FROM order_item oi JOIN `order` o ON o.id = oi.order_id"
            " WHERE o.user_id=%s ORDER BY oi.id DESC LIMIT 1",
            (int(user_id),),
        )

    async def resolve_student_id(self, user_id: int) -> int:
        """取 student_profile.id（按订单的 student 优先，兜底最小档案）。"""
        row = await fetch_one(
            "SELECT oi.student_id FROM order_item oi JOIN `order` o ON o.id=oi.order_id"
            " WHERE o.user_id=%s ORDER BY oi.id DESC LIMIT 1", (int(user_id),),
        )
        if row and row.get("student_id"):
            return int(row["student_id"])
        prof = await fetch_one("SELECT id FROM student_profile WHERE user_id=%s AND yn=1 LIMIT 1", (int(user_id),))
        if prof:
            return int(prof["id"])
        from app.database import execute_write
        sid = await execute_write(
            "INSERT INTO student_profile (user_id, learner_identity_id, learning_goal_id, yn, created_at, updated_at)"
            " VALUES (%s, 1, 1, 1, NOW(), NOW())", (int(user_id),),
        )
        return int(sid)

    async def get_ticket(self, ticket_id: int, user_id: int | None = None) -> dict | None:
        """按 id 查工单（+ 满意度）。user_id=None = 管理员/任何；否则校验归属（越权返回 None）。"""
        where = "st.id=%s AND st.yn=1"
        args: list = [ticket_id]
        if user_id is not None:
            where += " AND st.user_id=%s"
            args.append(int(user_id))
        row = await fetch_one(
            "SELECT st.id AS ticket_id, st.ticket_no, st.user_id, st.title, st.ticket_content AS content,"
            " st.ticket_type, st.ticket_status AS status, st.priority_level,"
            " st.first_response_at, st.closed_at, st.created_at, st.updated_at,"
            " o.order_no, st.institution_id, st.student_id"
            f" FROM service_ticket st LEFT JOIN order_item oi ON oi.id = st.order_item_id"
            f" LEFT JOIN `order` o ON o.id = oi.order_id WHERE {where} LIMIT 1",
            tuple(args),
        )
        if row is None:
            return None
        sat = await self.get_satisfaction(ticket_id)
        if sat:
            row["satisfaction_score"] = sat["score_value"]
            row["satisfaction_comment"] = sat["comment_text"]
        return row

    async def get_satisfaction(self, ticket_id: int) -> dict | None:
        # 不过滤 yn：D2 兜底，保证 1062 幂等回查能取到真实已存分（软删历史亦实现 idempotent 语义）
        return await fetch_one(
            "SELECT score_value, comment_text FROM service_ticket_satisfaction_survey"
            " WHERE ticket_id=%s LIMIT 1", (ticket_id,),
        )

    async def list_tickets(
        self, user_id: int | None, *, ticket_status: str | None = None,
        ticket_type: str | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """我的工单（user_id=None=管理端全部）。status/type 过滤 + 分页 + 满意度。"""
        where = ["st.yn=1"]
        args: list = []
        if user_id is not None:
            where.append("st.user_id=%s")
            args.append(int(user_id))
        if ticket_status:
            where.append("st.ticket_status=%s")
            args.append(ticket_status)
        if ticket_type:
            where.append("st.ticket_type=%s")
            args.append(ticket_type)
        base = (" FROM service_ticket st"
                " LEFT JOIN order_item oi ON oi.id = st.order_item_id"
                " LEFT JOIN `order` o ON o.id = oi.order_id"
                f" WHERE {' AND '.join(where)}")
        cnt = await fetch_one(f"SELECT COUNT(*) c {base}", tuple(args))
        total = int(cnt["c"]) if cnt else 0
        rows = await fetch_all(
            "SELECT st.id AS ticket_id, st.ticket_no, st.user_id, st.title,"
            " st.ticket_content AS content, st.ticket_type, st.ticket_status AS status,"
            " st.priority_level, st.first_response_at, st.closed_at, st.created_at, st.updated_at,"
            " o.order_no"
            f"{base} ORDER BY st.id DESC LIMIT %s OFFSET %s",
            tuple(args + [page_size, (page - 1) * page_size]),
        )
        return rows, total


class TicketWriteRepo:
    """事务内写：创建 + 满意度（幂等）。"""

    @staticmethod
    def new_ticket_no(institution_id: int) -> str:
        return f"T-{institution_id}-{datetime.now().strftime('%y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    @staticmethod
    def new_survey_no() -> str:
        return f"SV-{datetime.now().strftime('%y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    async def create_ticket(
        self, *, conn, cur, institution_id: int, ticket_no: str, user_id: int, student_id: int,
        order_item_id: int, ticket_type: str, title: str, content: str, now: datetime,
    ) -> int:
        """INSERT service_ticket（open + priority medium + source user_app + first_response_at 空=等待受理）。"""
        await cur.execute(
            "INSERT INTO service_ticket (institution_id, ticket_no, user_id, student_id, order_item_id,"
            " ticket_type, ticket_source, priority_level, ticket_status, title, ticket_content,"
            " yn, first_response_at, created_at, updated_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,'user_app','medium','open',%s,%s,1,NULL,%s,%s)",
            (institution_id, ticket_no, int(user_id), int(student_id), int(order_item_id),
             ticket_type, title, content, now, now),
        )
        return int(cur.lastrowid)

    async def insert_satisfaction(
        self, *, conn, cur, user_id: int, student_id: int, ticket_id: int,
        score_value: int, comment_text: str | None, now: datetime,
    ) -> int:
        """满意度评价（ticket_id 唯一键；重复评分由 service 捕获 1062 → 幂等拦截，GWT③）。"""
        await cur.execute(
            "INSERT INTO service_ticket_satisfaction_survey (survey_no, user_id, student_id, ticket_id,"
            " score_value, comment_text, yn, surveyed_at, created_at, updated_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,1,%s,%s,%s)",
            (self.new_survey_no(), int(user_id), int(student_id), int(ticket_id),
             score_value, comment_text, now, now, now),
        )
        return int(cur.lastrowid)