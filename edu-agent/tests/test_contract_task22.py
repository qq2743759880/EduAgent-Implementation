# -*- coding: utf-8 -*-
"""task22 契约⑫测试：after_sales/ticket 域 4 端点。

执行方式：in-process ASGI（httpx ASGITransport，外部存储机不可用不跑 uvicorn）。
鉴权用 DEBUG X-Force-Role/X-Force-User-Id 打靶。

GWT：
① 创建 ticket_type=appeal → 落库成功（前端文案映射"人工申诉"）+ first_response_at 空（等待受理态）
② 用户 A 请求用户 B 工单详情 → 404（隔离）；管理员可见全部
③ 满意度评价 1-5 星 → score 落库 + 不可重复评分（submitted=False）
④ 列表按 status/type 过滤 + 分页 → TicketPage
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import pytest

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from app.database import close_mysql, fetch_all, fetch_one, init_mysql  # noqa: E402
from app.main import app  # noqa: E402

def _run(coro):
    """在模块级持久事件循环上运行协程。

    asyncmy 的 Pool 绑定「创建时所在事件循环」并缓存该循环引用；若用「每调用新建并
    立刻关闭」的循环，池仍指向已关闭循环 → RuntimeError: Event loop is closed。故本模块
    全程复用同一个 _loop，且从不主动 close（仅在进程退出释放），并仅在每次操作前把它
    set 为当前循环，避免被 asyncio_mode=auto 的 pytest-asyncio 抢先关闭（task37 根因修复）。
    """
    asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)

_loop = asyncio.new_event_loop()
FI: dict = {}


async def _find_fixture() -> dict | None:
    """找：≥2 个有订单的用户（作隔离测试）。"""
    users = await fetch_all("SELECT DISTINCT o.user_id FROM `order` o LIMIT 3")
    if len(users) < 2:
        return None
    a = int(users[0]["user_id"]); b = int(users[1]["user_id"])
    return {"user_a": a, "user_b": b}


async def _req(method, path, user_id, body=None):
    transport = httpx.ASGITransport(app=app)
    headers = {"X-Force-Role": "student", "X-Force-User-Id": str(user_id)}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        if method == "GET":
            return await c.get(path, headers=headers)
        return await c.post(path, headers=headers, json=body or {})


def _call_a(method, path, body=None):
    return _run(_req(method, path, FI["user_a"], body))


def _call_b(method, path, body=None):
    return _run(_req(method, path, FI["user_b"], body))


@pytest.fixture(scope="module", autouse=True)
def _init():
    _run(init_mysql())
    fi = _run(_find_fixture())
    assert fi, "无可用夹具：需 ≥2 个有订单的用户"
    FI.update(fi)
    yield
    _run(close_mysql())


class TestCreateAppeal:
    def test_create_appeal_ticket(self):
        """GWT①：创建 appeal 工单 → 落库成功 + first_response_at 空。"""
        r = _call_a("POST", "/api/trade/after_sales/ticket", {
            "ticket_type": "appeal", "title": "人工申诉测试", "content": "请人工复核报名问题",
        })
        assert r.status_code == 200 and r.json()["code"] == 0, r.text[:200]
        t = r.json()["data"]
        assert t["ticket_type"] == "appeal"
        assert t["status"] == "open"
        assert t["ticket_no"] and t["ticket_id"] > 0
        # DB：first_response_at 为空（等待受理态）
        row = _run(fetch_one(
            "SELECT first_response_at FROM service_ticket WHERE id=%s", (t["ticket_id"],)))
        assert row and row["first_response_at"] is None, "首次响应应为空（等待受理）"
        FI["ticket_a"] = t["ticket_id"]

    def test_create_refund_ticket(self):
        r = _call_a("POST", "/api/trade/after_sales/ticket", {
            "ticket_type": "refund", "title": "退款咨询", "content": "申请退款进度",
        })
        assert r.status_code == 200 and r.json()["code"] == 0
        assert r.json()["data"]["ticket_type"] == "refund"


class TestUserIsolation:
    def test_cross_user_detail_404(self):
        """GWT②：用户 B 请求用户 A 的工单 → 404。"""
        if "ticket_a" not in FI:
            pytest.skip("无 A 工单")
        r = _call_b("GET", f"/api/trade/after_sales/ticket/{FI['ticket_a']}")
        assert r.status_code == 404 and r.json()["code"] == "40441"

    def test_own_detail_ok(self):
        if "ticket_a" not in FI:
            pytest.skip("无 A 工单")
        r = _call_a("GET", f"/api/trade/after_sales/ticket/{FI['ticket_a']}")
        assert r.status_code == 200 and r.json()["code"] == 0
        assert r.json()["data"]["ticket_id"] == FI["ticket_a"]


class TestSatisfactionIdempotent:
    def test_satisfaction_and_not_duplicate(self):
        """GWT③：满意度落库 + 不可重复评分。"""
        if "ticket_a" not in FI:
            pytest.skip("无 A 工单")
        r1 = _call_a("POST", f"/api/trade/after_sales/ticket/{FI['ticket_a']}/satisfaction",
                     {"satisfaction_score": 5, "satisfaction_comment": "处理及时"})
        assert r1.status_code == 200 and r1.json()["data"]["submitted"] is True
        r2 = _call_a("POST", f"/api/trade/after_sales/ticket/{FI['ticket_a']}/satisfaction",
                     {"satisfaction_score": 1})
        assert r2.status_code == 200 and r2.json()["data"]["submitted"] is False, "不可重复评分"
        # DB：唯一一条且 score 未变
        rows = _run(fetch_all(
            "SELECT score_value FROM service_ticket_satisfaction_survey WHERE ticket_id=%s",
            (FI["ticket_a"],)))
        assert len(rows) == 1 and int(rows[0]["score_value"]) == 5


class TestListFilter:
    def test_list_and_filter(self):
        """GWT④：列表 status/type 过滤 + 分页 → TicketPage。"""
        r = _call_a("GET", "/api/trade/after_sales/tickets?ticket_type=appeal&page=1&page_size=10")
        assert r.status_code == 200 and r.json()["code"] == 0
        d = r.json()["data"]
        assert "items" in d and "total" in d and "page" in d
        for it in d["items"]:
            assert it["ticket_type"] == "appeal"
        r2 = _call_a("GET", "/api/trade/after_sales/tickets?status=open&page=1&page_size=10")
        assert r2.status_code == 200 and r2.json()["code"] == 0

    def test_list_admin_sees_all(self):
        """管理员可见全部（列表跨用户可见，不触发 user 隔离）。"""
        transport = httpx.ASGITransport(app=app)
        hdr = {"X-Force-Role": "admin", "X-Force-User-Id": str(FI["user_b"])}
        resp = _run(_admin_get(transport, hdr))
        assert resp.status_code == 200 and resp.json()["code"] == 0
        items = resp.json()["data"]["items"]
        assert isinstance(items, list)
        # 跨用户可见：返回的项可含非 user_b 的 user_id
        if "ticket_a" in FI:
            assert items  # 管理端可见工单列表（含历史上其他用户工单）


async def _admin_get(transport, headers):
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get("/api/trade/after_sales/tickets?page=1&page_size=100", headers=headers)