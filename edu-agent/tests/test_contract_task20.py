# -*- coding: utf-8 -*-
"""task20 契约⑪ 前段测试：enrollment 域只读 4 端点 + 状态过滤 + 进度聚合。

执行方式：in-process ASGI（httpx ASGITransport）。外部存储机(192.168.85.101)不可用
导致服务起服挂，故不跑 uvicorn。用单例事件循环承载 DB 池 + 请求（避免 loop 所有权冲突）。
鉴权用 DEBUG X-Force-Role 打靶。

GWT：
① 满班并发控制（条件更新 occupy_seat）→ scripts/_verify_task20_full.py（DB 层攻防）
② GET /api/enrollments/me/cohorts?status=active → 班次 + 模块/课次进度聚合（真实非 MOCK）；
   refunded 过滤、详情、进度快照、状态查询
③ 报名记录由支付回调联动（task18 已验）——本域校验记录正确读出
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
from app.database import close_mysql, fetch_one, init_mysql  # noqa: E402
from app.main import app  # noqa: E402

_loop = asyncio.new_event_loop()
FI: dict = {}


def _run(coro):
    """模块级持久循环上运行协程（task37 根因修复，同 test_contract_task22/21）：
    asyncmy Pool 绑定创建循环；asyncio_mode=auto 的 pytest-asyncio 会关闭当前循环。
    复用同一 _loop 且每次操作前 set 为当前，避免 Event loop is closed。"""
    asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)


async def _find_fixture() -> dict | None:
    return await fetch_one(
        "SELECT scr.user_id, scr.cohort_id, c.series_id FROM student_cohort_rel scr"
        " JOIN series_cohort c ON c.id = scr.cohort_id"
        " WHERE scr.enroll_status='active'"
        " AND EXISTS (SELECT 1 FROM series_cohort_course ccc WHERE ccc.cohort_id=scr.cohort_id)"
        " AND EXISTS (SELECT 1 FROM series_cohort_course ccc"
        "   JOIN series_cohort_session scs ON scs.series_cohort_course_id=ccc.id"
        "   WHERE ccc.cohort_id=scr.cohort_id)"
        " LIMIT 1")


async def _get(path: str, user_id: int):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, headers={"X-Force-Role": "admin", "X-Force-User-Id": str(user_id)})


def _call(path: str):
    return _run(_get(path, FI["user_id"]))


@pytest.fixture(scope="module", autouse=True)
def _init():
    _run(init_mysql())
    row = _run(_find_fixture())
    assert row, "无可用夹具：需一个在有课程结构的班次上 active 报名的用户"
    FI.update({"user_id": int(row["user_id"]), "cohort_id": int(row["cohort_id"]),
               "series_id": int(row["series_id"])})
    yield
    _run(close_mysql())


class TestMeCohorts:
    def test_list_active_with_progress(self):
        r = _call("/api/enrollments/me/cohorts?status=active")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        items = body["data"]
        assert isinstance(items, list)
        target = [it for it in items if it["cohort_id"] == FI["cohort_id"]]
        assert target, f"夹具班次 {FI['cohort_id']} 应出现在 active 列表"
        it = target[0]
        assert it["enroll_status"] == "active"
        assert it["session_total"] is not None and it["session_total"] >= 1
        assert it["module_total"] is not None and it["module_total"] >= 1
        assert isinstance(it["overall_ratio"], (int, float))
        assert it["enrollment_id"] > 0 and it["series_id"] == FI["series_id"]

    def test_invalid_status_422(self):
        r = _call("/api/enrollments/me/cohorts?status=bogus")
        assert r.status_code == 422 and r.json()["code"] == "42200"

    def test_all_list(self):
        r = _call("/api/enrollments/me/cohorts")
        assert r.status_code == 200 and r.json()["code"] == 0
        assert isinstance(r.json()["data"], list)


class TestEnrollmentDetail:
    def test_detail(self):
        r = _call(f"/api/enrollments/me/cohorts/{FI['cohort_id']}")
        assert r.status_code == 200 and r.json()["code"] == 0
        d = r.json()["data"]
        assert d["enroll_status"] in ("active", "completed", "cancelled", "refunded")
        assert d["session_total"] >= 1 and d["module_total"] >= 1

    def test_detail_not_enrolled_404(self):
        r = _call("/api/enrollments/me/cohorts/9999999")
        assert r.status_code == 404 and r.json()["code"] == "40430"


class TestEnrollmentStatus:
    def test_status(self):
        r = _call(f"/api/enrollments/me/cohorts/{FI['cohort_id']}/status")
        assert r.status_code == 200 and r.json()["code"] == 0
        s = r.json()["data"]
        assert s["enroll_status"] == "active"
        assert s["cohort_id"] == FI["cohort_id"]


class TestProgressSnapshot:
    def test_snapshot_modules(self):
        r = _call(f"/api/enrollments/me/cohorts/{FI['cohort_id']}/progress")
        assert r.status_code == 200 and r.json()["code"] == 0
        d = r.json()["data"]
        assert d["session_total"] >= 1 and d["module_total"] >= 1
        assert isinstance(d["modules"], list) and len(d["modules"]) >= 1
        first = d["modules"][0]
        assert "sessions" in first and "done_count" in first and "total_count" in first