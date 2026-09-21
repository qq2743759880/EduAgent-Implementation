# -*- coding: utf-8 -*-
"""REWORK P0-5：管理端会话审计（只读·ADMIN-only）契约测试。

- 路由依赖 require_role([ADMIN])（服务端角色硬校验）→ student 直连 403；
- 列表：分页壳 {total,page,page_size,items} + user_id 精确过滤；
- 历史：admin 可读任意学员会话（审计用途），只读无写端点；
- 隔离边界：审计是显式授权面（admin-only 端点），不回退用户端 /api/chat/sessions 的按人过滤。

liveliness：打 127.0.0.1:9988（TEST_BASE 可覆盖，与全仓口径一致）。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:9988")


def _login(account: str, password: str = "Test@123456") -> str:
    req = urllib.request.Request(BASE + "/api/auth/login", data=json.dumps(
        {"account": account, "password": password}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["data"]["access_token"]


def _get(path: str, token: str):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body[:200].decode("utf-8", "replace")}


ADMIN_TOKEN = None
STUDENT_TOKEN = None


def setup_module(module):
    global ADMIN_TOKEN, STUDENT_TOKEN
    ADMIN_TOKEN = _login("adm02test")
    STUDENT_TOKEN = _login("user000001")


def test_student_forbidden_on_audit_list():
    """① student 访问审计列表 → 403（服务端角色硬校验）。"""
    status, body = _get("/api/admin/chat-audit/sessions?page=1&page_size=5", STUDENT_TOKEN)
    assert status == 403, f"student 竟然通过: {status} {body}"


def test_student_forbidden_on_audit_history():
    """② student 访问审计历史 → 403。"""
    status, body = _get("/api/admin/chat-audit/sessions/s_x/history", STUDENT_TOKEN)
    assert status == 403


def test_admin_list_pagination_and_user_filter():
    """③ admin 列表：分页壳 + user_id 过滤（全部行属目标学员）。"""
    status, body = _get("/api/admin/chat-audit/sessions?page=1&page_size=5", ADMIN_TOKEN)
    assert status == 200
    data = body["data"]
    assert set(data.keys()) >= {"total", "page", "page_size", "items"}
    assert data["page"] == 1 and data["page_size"] == 5
    assert len(data["items"]) <= 5
    assert data["total"] >= len(data["items"])
    for it in data["items"]:
        assert set(it.keys()) >= {"session_id", "user_id", "title", "message_count"}

    # user_id 过滤：过滤自身会话（admin=100003）→ 所有行 user_id 全等于该值
    status2, body2 = _get("/api/admin/chat-audit/sessions?user_id=100003&page=1&page_size=10", ADMIN_TOKEN)
    assert status2 == 200
    items2 = body2["data"]["items"]
    assert items2, "admin 自身应有会话"
    assert all(int(it["user_id"]) == 100003 for it in items2), "user_id 过滤泄漏他人会话"
    total_all = data["total"]
    total_100003 = body2["data"]["total"]
    assert total_100003 <= total_all, "过滤后 total 应 ≤ 全量"


def test_admin_reads_student_history_readonly():
    """④ admin 读任意学员会话历史（审计用途）+ 只读端点面（无写方法）。"""
    # 先取一个学员会话
    status, body = _get("/api/admin/chat-audit/sessions?user_id=1&page=1&page_size=1", ADMIN_TOKEN)
    assert status == 200
    items = body["data"]["items"]
    assert items, "student user_id=1 应有会话"
    sid = items[0]["session_id"]
    status2, body2 = _get(f"/api/admin/chat-audit/sessions/{sid}/history?limit=10", ADMIN_TOKEN)
    assert status2 == 200
    data = body2["data"]
    assert data["session_id"] == sid and int(data["user_id"]) == 1
    assert isinstance(data["items"], list) and len(data["items"]) <= 10
    for m in data["items"]:
        assert set(m.keys()) >= {"message_id", "role", "content", "created_at"}


def test_history_404_shell():
    """⑤ 不存在的会话 → 壳式空数据（不 500）。"""
    status, body = _get("/api/admin/chat-audit/sessions/s_not_exist_xyz/history", ADMIN_TOKEN)
    assert status == 200 and (body["data"] is None)
