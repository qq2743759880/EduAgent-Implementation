# -*- coding: utf-8 -*-
"""
be-task01：chat DELETE 软删 单元测试。

覆盖（对齐 be-task01 验收标准 + task05-challenge #3 事务问题）：
- 本人删除 → 软删语义：UPDATE chat_session SET yn=0，禁止物理 DELETE（PRD §12.2 约束 12）
- 学生删他人会话 → 403（ValidationError CHAT_SESSION_FORBIDDEN，跨用户）
- 会话不存在 / 已软删（重复删除幂等）→ 404（NotFoundError）
- admin 删他人 → 允许（角色语义：admin 全局可见可删）
- router._translate_exception：CHAT_SESSION_FORBIDDEN → 403 错误壳、NotFoundError → 404 CHAT_SESSION_NOT_FOUND
- 事务内禁止嵌套 execute_write()（task05-challenge #3 / task04 #1 根因回归）

环境说明：不依赖 pytest-asyncio（asyncio_mode 配置缺失时 async 测试不收集），
异步逻辑统一用 asyncio.run() 在同步测试内执行。
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.auth import UserRole
from app.chat import router as chat_router
from app.chat import service as chat_service
from app.chat.schemas import ChatMessage, ChatSession
from app.common.exceptions import NotFoundError, ValidationError


# ============================================================
# 工具
# ============================================================
def _fake_row(uid: int, sid: str = "s_test1") -> dict:
    """模拟 chat_session 表的行（_ensure_session_owner 的 SELECT * 结果）。"""
    now = datetime.now()
    return {
        "session_id": sid,
        "user_id": uid,
        "title": "测试会话",
        "visibility": "private",
        "message_count": 0,
        "last_message_at": None,
        "created_at": now,
        "updated_at": now,
        "yn": 1,
    }


def _make_session(sid: str = "s_test1", uid: int = 2, title: str = "新会话 abcd") -> ChatSession:
    now = datetime.now()
    return ChatSession(
        session_id=sid,
        user_id=uid,
        title=title,
        visibility="private",
        message_count=0,
        last_message_at=None,
        created_at=now,
        updated_at=now,
        yn=1,
    )


def _make_msg(mid: str, role: str, content: str, sid: str = "s_test1") -> ChatMessage:
    return ChatMessage(
        message_id=mid,
        session_id=sid,
        user_id=2,
        role=role,  # type: ignore[arg-type]
        content=content,
        created_at=datetime.now(),
    )


# ============================================================
# 1. delete_session：本人删除 → 软删 UPDATE yn=0（禁止物理 DELETE）
# ============================================================
def test_delete_session_own_soft_delete(monkeypatch):
    calls: list[tuple[str, object]] = []

    async def _fake_fetch_one(sql: str, args: tuple | None = None):
        # 归属校验必须带 yn=1 过滤 —— 幂等（已删会话 404）的前提
        assert "yn = 1" in sql
        return _fake_row(uid=2)

    monkeypatch.setattr(chat_service, "fetch_one", _fake_fetch_one)

    async def _fake_execute_write(sql: str, args: tuple | None = None):
        calls.append((sql, args))

    monkeypatch.setattr(chat_service, "execute_write", _fake_execute_write)

    async def _run():
        await chat_service.delete_session(2, "s_test1", UserRole.STUDENT)

    asyncio.run(_run())

    assert len(calls) == 1, f"期望只执行 1 条 UPDATE，实际 {len(calls)}"
    sql = str(calls[0][0])
    assert "UPDATE chat_session" in sql
    assert "yn = 0" in sql
    # 红线约束 12：会话删除禁止物理 DELETE
    assert "DELETE FROM" not in sql.upper()


# ============================================================
# 2. delete_session：学生删他人会话 → 403 CHAT_SESSION_FORBIDDEN
# ============================================================
def test_delete_session_cross_user_forbidden(monkeypatch):
    async def _fake_fetch_one(sql: str, args: tuple | None = None):
        return _fake_row(uid=99)

    monkeypatch.setattr(chat_service, "fetch_one", _fake_fetch_one)

    async def _run():
        with pytest.raises(ValidationError) as ei:
            await chat_service.delete_session(2, "s_test1", UserRole.STUDENT)
        return ei.value

    exc = asyncio.run(_run())
    # service 层语义：detail 必须携带 CHAT_SESSION_FORBIDDEN 子码；
    # http_status 403 由 router._translate_exception 单一事实源映射（见
    # test_router_translate_forbidden_to_403_shell）——service 层异常本身
    # 是 40000/400，靠子码字符串联动 router，不得在 service 层重复映射（L14）。
    assert "CHAT_SESSION_FORBIDDEN" in (exc.detail or "")
    # 越权删除不得落任何写 SQL
    assert not hasattr(exc, "_writes")


# ============================================================
# 3. delete_session：会话不存在 / 已软删 → 404（幂等：重复删除天然 404）
# ============================================================
def test_delete_session_not_found_idempotent(monkeypatch):
    async def _fake_fetch_one(sql: str, args: tuple | None = None):
        return None

    monkeypatch.setattr(chat_service, "fetch_one", _fake_fetch_one)

    async def _run():
        with pytest.raises(NotFoundError) as ei:
            await chat_service.delete_session(2, "s_test1", UserRole.STUDENT)
        return ei.value

    exc = asyncio.run(_run())
    assert exc.http_status == 404
    assert "会话" in exc.message


# ============================================================
# 4. delete_session：admin 删他人会话 → 允许（角色语义，非 403）
# ============================================================
def test_delete_session_admin_can_delete_any(monkeypatch):
    calls: list[str] = []

    async def _fake_fetch_one(sql: str, args: tuple | None = None):
        return _fake_row(uid=99)

    async def _fake_execute_write(sql: str, args: tuple | None = None):
        calls.append(str(sql))

    monkeypatch.setattr(chat_service, "fetch_one", _fake_fetch_one)
    monkeypatch.setattr(chat_service, "execute_write", _fake_execute_write)

    async def _run():
        await chat_service.delete_session(1, "s_test1", UserRole.ADMIN)

    asyncio.run(_run())
    assert len(calls) == 1, "admin 删他人会话应执行软删 UPDATE"


# ============================================================
# 5. router._translate_exception：CHAT_SESSION_FORBIDDEN → 403 错误壳
# ============================================================
def test_router_translate_forbidden_to_403_shell():
    with pytest.raises(HTTPException) as ei:
        chat_router._translate_exception(
            ValidationError("无权限访问该会话", detail="CHAT_SESSION_FORBIDDEN")
        )
    assert ei.value.status_code == 403
    detail = ei.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "CHAT_SESSION_FORBIDDEN"
    assert "message" in detail


# ============================================================
# 6. router._translate_exception：NotFoundError → 404 CHAT_SESSION_NOT_FOUND
# ============================================================
def test_router_translate_not_found_to_404_shell():
    with pytest.raises(HTTPException) as ei:
        chat_router._translate_exception(NotFoundError("会话", "s_test1"))
    assert ei.value.status_code == 404
    detail = ei.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "CHAT_SESSION_NOT_FOUND"
    assert "message" in detail


# ============================================================
# 7. _append_messages_and_bump_session：事务内必须用共享 cur，
#    禁止嵌套 execute_write()（task05-challenge #3 / task04 #1 根因回归）
# ============================================================
def test_append_messages_uses_shared_cur(monkeypatch):
    # 若事务块内嵌套 execute_write（独立连接+自动提交）→ 立刻断言失败
    def _forbid_execute_write(*args, **kwargs):
        raise AssertionError("transaction() 块内禁止嵌套 execute_write()（task04 #1 根因）")

    monkeypatch.setattr(chat_service, "execute_write", _forbid_execute_write)

    executed: list[str] = []

    class _FakeCur:
        async def execute(self, sql: str, args: tuple | None = None):
            executed.append(str(sql))

    @contextlib.asynccontextmanager
    async def _fake_transaction():
        yield None, _FakeCur()

    monkeypatch.setattr(chat_service, "transaction", _fake_transaction)

    session = _make_session()
    user_msg = _make_msg("m_u1", "user", "第一个问题：什么是特征向量？")
    asst_msg = _make_msg("m_a1", "assistant", "特征向量是…")

    async def _run():
        await chat_service._append_messages_and_bump_session(
            session, user_msg=user_msg, assistant_msg=asst_msg
        )

    asyncio.run(_run())

    # user insert + assistant insert + session count bump = 3 条 SQL 全部走共享 cur
    assert len(executed) == 3, f"期望 3 条 SQL 走共享 cur，实际 {len(executed)}"
    kinds = []
    for sql in executed:
        upper = sql.upper().strip()
        if upper.startswith("INSERT"):
            kinds.append("INSERT")
        elif upper.startswith("UPDATE"):
            kinds.append("UPDATE")
        else:
            kinds.append("OTHER:" + sql)
    assert kinds.count("INSERT") == 2 and kinds.count("UPDATE") == 1, f"SQL 类型不符：{kinds}"


# ============================================================
# 8. 消息落库 SQL 必须带 `AND yn = 1`（软删会话并发落库时空更新，不复活已删会话）
# ============================================================
def test_append_messages_update_guards_yn1(monkeypatch):
    executed: list[str] = []

    class _FakeCur:
        async def execute(self, sql: str, args: tuple | None = None):
            executed.append(str(sql))

    @contextlib.asynccontextmanager
    async def _fake_transaction():
        yield None, _FakeCur()

    monkeypatch.setattr(chat_service, "transaction", _fake_transaction)
    monkeypatch.setattr(chat_service, "execute_write", lambda *a, **k: None)

    session = _make_session()
    user_msg = _make_msg("m_u2", "user", "第二个问题")

    async def _run():
        await chat_service._append_messages_and_bump_session(session, user_msg=user_msg, assistant_msg=None)

    asyncio.run(_run())

    update_sql = next(s for s in executed if s.strip().upper().startswith("UPDATE"))
    assert "yn = 1" in update_sql, "update_session_sql 必须带 AND yn = 1（task05 #4 竞态防线）"
