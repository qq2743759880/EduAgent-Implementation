# -*- coding: utf-8 -*-
"""after_sales/ticket 域（task22 契约⑫）service。

安全红线：
- user_id 隔离（GWT②）：详情/列表对非本人 → 404（不泄漏存在性）；管理员/经理可见全部
- 满意度幂等（GWT③）：ticket_id 唯一，重复评分返回 submitted=False 且不改写
- first_response_at 空 = 等待受理态（GWT①）；ticket_no 唯一键幂等（并发/重试回查）
- 契约① 响应壳 ok()；失败 AppException → 全局 handler
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.common.exceptions import AppException
from app.database import transaction
from app.domains.after_sales.repository import TicketRepo, TicketWriteRepo
from app.domains.after_sales.schemas import (
    Ticket, TicketPage, TicketSatisfactionResult,
)

logger = logging.getLogger(__name__)

_ticket_repo = TicketRepo()
_ticket_write = TicketWriteRepo()

VALID_TICKET_TYPES = {"consult", "appeal", "refund", "other"}
VALID_TICKET_STATUS = {"open", "processing", "resolved", "closed"}


def _norm_type(t: str | None) -> str:
    """规整 ticket_type 到前端 TicketType 枚举（edu.sql 历史值映射：after_sales/complaint→other）。"""
    if t in VALID_TICKET_TYPES:
        return t
    return "other"


def _norm_status(s: str | None) -> str:
    """规整 ticket_status 到前端 TicketStatus（edu.sql 历史值：pending→open、in_progress→processing）。"""
    if s in VALID_TICKET_STATUS:
        return s
    if s == "pending":
        return "open"
    if s == "in_progress":
        return "processing"
    return "open"


def _ticket_from_row(r: dict) -> Ticket:
    return Ticket(
        ticket_id=int(r["ticket_id"]),
        ticket_no=r["ticket_no"],
        user_id=int(r["user_id"]),
        order_no=r.get("order_no") or None,
        ticket_type=_norm_type(r["ticket_type"]),
        title=r["title"],
        content=r.get("content") or r.get("ticket_content") or "",
        status=_norm_status(r["status"]),
        reply=None,
        satisfaction_score=int(r["satisfaction_score"]) if r.get("satisfaction_score") is not None else None,
        satisfaction_comment=r.get("satisfaction_comment"),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        closed_at=r.get("closed_at"),
    )


def _is_admin(role_name: str) -> bool:
    return role_name in ("admin", "manager")


# ═══════════════════════════════════════════════════════
# 创建工单（GWT① appeal 人工申诉；first_response_at 空）
# ═══════════════════════════════════════════════════════
async def create_ticket(user_id: int, *, ticket_type: str, title: str, content: str,
                        order_no: str | None) -> Ticket:
    if ticket_type not in VALID_TICKET_TYPES:
        raise AppException("42200", f"非法工单类型：{ticket_type}")

    ord_item = await _ticket_repo.resolve_order_item(user_id, order_no)
    if ord_item is None:
        if order_no:
            raise AppException("40442", "订单不存在或不属于你")
        raise AppException("40040", "需先有购课订单才能发起工单")
    student_id = await _ticket_repo.resolve_student_id(user_id)
    institution_id = int(ord_item["institution_id"])
    now = datetime.now()

    try:
        async with transaction() as (conn, cur):
            ticket_no = _ticket_write.new_ticket_no(institution_id)
            ticket_id = await _ticket_write.create_ticket(
                conn=conn, cur=cur, institution_id=institution_id, ticket_no=ticket_no,
                user_id=user_id, student_id=student_id,
                order_item_id=int(ord_item["order_item_id"]),
                ticket_type=ticket_type, title=title, content=content, now=now,
            )
    except Exception as exc:
        if "1062" in str(exc) or "duplicate" in str(exc).lower():
            # ticket_no 唯一键冲突（并发/重试）→ 业务幂等：返回该用户最近工单（不重复建单）
            rows, _ = await _ticket_repo.list_tickets(user_id, page=1, page_size=1)
            if rows:
                return _ticket_from_row(rows[0])
        logger.exception("[ticket] 创建工单事务失败：%s", exc)
        raise

    row = await _ticket_repo.get_ticket(ticket_id, user_id)
    if row is None:
        raise AppException("50000", "工单创建失败，请重试")
    return _ticket_from_row(row)


# ═══════════════════════════════════════════════════════
# 列表（GWT④ status/type 过滤 + 分页；user 隔离）
# ═══════════════════════════════════════════════════════
async def list_tickets(user_id: int, role_name: str | None = None, *,
                       ticket_status: str | None = None, ticket_type: str | None = None,
                       page: int = 1, page_size: int = 20) -> TicketPage:
    if ticket_status and ticket_status not in VALID_TICKET_STATUS:
        raise AppException("42200", f"非法工单状态：{ticket_status}")
    if ticket_type and ticket_type not in VALID_TICKET_TYPES:
        raise AppException("42200", f"非法工单类型：{ticket_type}")
    scope_user = None if _is_admin(role_name or "") else user_id
    rows, total = await _ticket_repo.list_tickets(
        scope_user, ticket_status=ticket_status, ticket_type=ticket_type,
        page=page, page_size=page_size,
    )
    return TicketPage(total=total, page=page, page_size=page_size,
                      items=[_ticket_from_row(r) for r in rows])


# ═══════════════════════════════════════════════════════
# 详情（GWT② 越权 404；管理员可见全部）
# ═══════════════════════════════════════════════════════
async def get_ticket_detail(ticket_id: int, user_id: int, role_name: str | None = None) -> Ticket:
    req_user = None if _is_admin(role_name or "") else user_id
    row = await _ticket_repo.get_ticket(ticket_id, req_user)
    if row is None:
        # 非本人（或因 yn=0）→ 404（不泄漏他人工单存在性）
        raise AppException("40441", "工单不存在")
    return _ticket_from_row(row)


# ═══════════════════════════════════════════════════════
# 满意度评价（GWT③ 幂等，不可重复评分）
# ═══════════════════════════════════════════════════════
async def submit_satisfaction(user_id: int, ticket_id: int, *,
                              score: int, comment: str | None) -> TicketSatisfactionResult:
    row = await _ticket_repo.get_ticket(ticket_id, user_id)
    if row is None:
        raise AppException("40441", "工单不存在")

    existing = await _ticket_repo.get_satisfaction(ticket_id)
    if existing is not None:
        # 已评过 → 幂等返回 submitted=False（不可重复评分）
        return TicketSatisfactionResult(
            ticket_id=ticket_id, satisfaction_score=int(existing["score_value"]), submitted=False,
        )

    student_id = await _ticket_repo.resolve_student_id(user_id)
    now = datetime.now()
    try:
        async with transaction() as (conn, cur):
            await _ticket_write.insert_satisfaction(
                conn=conn, cur=cur, user_id=user_id, student_id=student_id,
                ticket_id=ticket_id, score_value=score, comment_text=comment, now=now,
            )
    except Exception as exc:
        if "1062" in str(exc) or "duplicate" in str(exc).lower():
            existing2 = await _ticket_repo.get_satisfaction(ticket_id)
            return TicketSatisfactionResult(
                ticket_id=ticket_id,
                satisfaction_score=int(existing2["score_value"]) if existing2 else score,
                submitted=False,
            )
        logger.exception("[ticket] 满意度评价事务失败：%s", exc)
        raise

    return TicketSatisfactionResult(ticket_id=ticket_id, satisfaction_score=score, submitted=True)