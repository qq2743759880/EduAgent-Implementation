# -*- coding: utf-8 -*-
"""FEAT-WIRE-V2 缺陷#8：chat 会话列表隔离回归测试。

背景（用户实测）：管理员对话列表混入他人会话——旧版 list_sessions 对 ADMIN 角色返回
全库所有用户会话（"admin 全局"分支）。修复后一律按当前 user_id 过滤；admin 全局审计
视图应另立管理端页面（登记，不在本单）。

零数据库依赖：monkeypatch fetch_all 打桩，断言 SQL 必须带 user_id 过滤且参数为当前用户。
"""
from __future__ import annotations

import asyncio

from app.auth import UserRole
from app.chat import service as chat_service


def _row(uid: int, sid: str) -> dict:
    from datetime import datetime

    return {
        "session_id": sid,
        "user_id": uid,
        "title": "会话" + sid,
        "visibility": "private",
        "message_count": 0,
        "last_message_at": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "yn": 1,
    }


def test_admin_list_is_filtered_by_own_user_id(monkeypatch):
    """admin 会话列表必须按 user_id 过滤（旧版 admin 全局分支已废除）。"""
    captured: dict = {}

    async def _fake_fetch_all(sql: str, args: tuple | None = None):
        captured["sql"] = str(sql)
        captured["args"] = tuple(args or ())
        return [_row(100003, "s_admin_own")]

    monkeypatch.setattr(chat_service, "fetch_all", _fake_fetch_all)

    async def _run():
        return await chat_service.list_sessions(100003, UserRole.ADMIN, limit=50)

    rows = asyncio.run(_run())
    assert "user_id = %s" in captured["sql"], "admin 列表 SQL 缺 user_id 过滤（#8 回归）"
    assert "yn = 1" in captured["sql"]
    assert captured["args"][0] == 100003, f"过滤参数应为当前 admin user_id，实际 {captured['args']}"
    assert len(rows) == 1 and rows[0].user_id == 100003


def test_student_list_still_filtered(monkeypatch):
    """student 列表过滤语义保持不变。"""
    captured: dict = {}

    async def _fake_fetch_all(sql: str, args: tuple | None = None):
        captured["sql"] = str(sql)
        captured["args"] = tuple(args or ())
        return [_row(2, "s_student")]

    monkeypatch.setattr(chat_service, "fetch_all", _fake_fetch_all)

    async def _run():
        return await chat_service.list_sessions(2, UserRole.STUDENT, limit=50)

    rows = asyncio.run(_run())
    assert "user_id = %s" in captured["sql"]
    assert captured["args"][0] == 2
    assert len(rows) == 1 and rows[0].user_id == 2
