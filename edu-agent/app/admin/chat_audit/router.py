"""
[REWORK P0-5] 管理端「会话审计」只读视图 router（FEAT-WIRE #8 隔离修复的显式授权面）。

- 全量 require_role([ADMIN])（服务端角色硬校验，student/manager 一律 403）；
- 只读：仅 GET 列表（分页 + user_id 过滤）与历史；无任何写端点；
- 用途标注：运营/内容审核巡检学员会话（audit 用途，页面需显式标注「审计用途」）。

契约：响应壳 {code:0,message,data}；列表裸 DTO {total,page,page_size,items}。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth import UserRole, require_role
from app.core.resp import ok
from app.database import fetch_all, fetch_one

router = APIRouter(
    prefix="/api/admin/chat-audit",
    tags=["admin-chat-audit（会话审计·只读）"],
    dependencies=[Depends(require_role([UserRole.ADMIN]))],
)


class AuditSessionItem(BaseModel):
    session_id: str
    user_id: int
    title: str
    visibility: str
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    yn: int


def _ok_list(items: list[AuditSessionItem], total: int, page: int, page_size: int) -> dict:
    return ok(data={
        "total": total, "page": page, "page_size": page_size,
        "items": [i.model_dump(mode="json") for i in items],
    })


@router.get("/sessions", summary="管理端·会话审计列表（只读·分页·user_id 过滤）")
async def audit_sessions(
    user_id: Optional[int] = Query(default=None, description="按学员 user_id 精确过滤"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    where = "yn = 1"
    args: list = []
    if user_id is not None:
        where += " AND user_id = %s"
        args.append(int(user_id))
    row = await fetch_one(f"SELECT COUNT(*) AS c FROM chat_session WHERE {where}", tuple(args))
    total = int(row["c"] or 0) if row else 0
    args2 = list(args) + [page_size, (page - 1) * page_size]  # LIMIT %s OFFSET %s（顺序对应）
    rows = await fetch_all(
        f"SELECT * FROM chat_session WHERE {where} "
        f"ORDER BY last_message_at DESC, created_at DESC LIMIT %s OFFSET %s",
        tuple(args2),
    )
    items = [
        AuditSessionItem(
            session_id=r["session_id"], user_id=int(r["user_id"]), title=r["title"] or "",
            visibility=r["visibility"] or "private", message_count=int(r["message_count"] or 0),
            last_message_at=r["last_message_at"], created_at=r["created_at"],
            updated_at=r["updated_at"], yn=int(r["yn"] or 1),
        )
        for r in rows
    ]
    return _ok_list(items, total, page, page_size)


@router.get("/sessions/{session_id}/history", summary="管理端·会话审计历史（只读，任意学员会话）")
async def audit_session_history(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    sess = await fetch_one(
        "SELECT session_id, user_id, title, message_count FROM chat_session "
        "WHERE session_id = %s AND yn = 1",
        (session_id,),
    )
    if not sess:
        return ok(data=None, message="会话不存在或已删除")
    rows = await fetch_all(
        "SELECT message_id, session_id, user_id, role, content, rag_final_count, created_at "
        "FROM chat_message WHERE session_id = %s ORDER BY created_at ASC LIMIT %s",
        (session_id, int(limit)),
    )
    return ok(data={
        "session_id": sess["session_id"], "user_id": int(sess["user_id"]),
        "title": sess["title"], "message_count": int(sess["message_count"] or 0),
        "items": [
            {
                "message_id": r["message_id"], "role": r["role"], "content": r["content"],
                "rag_final_count": r["rag_final_count"], "created_at": r["created_at"],
            }
            for r in rows
        ],
    })
