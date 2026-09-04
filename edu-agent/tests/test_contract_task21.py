# -*- coding: utf-8 -*-
"""task21 契约⑪ task21 段测试：study/learning 域（access 鉴权 + outline + session 详情）。

执行方式：in-process ASGI（httpx ASGITransport，不跑 lifespan——外部存储机不可用）。
鉴权用 DEBUG X-Force-Role / X-Force-User-Id 打靶。

GWT：
① 未报名用户请求 enrolled_only 资源 → 403（40330「需报名」）
② access 鉴权矩阵：enrolled_only 需 active；public/trial 开放
③ session 详情：session_asset 按 material_category + access_scope 过滤返回
④ 视频 transcode_status：pending/in_progress/completed/failed 与 task12 管线一致（url 仅 completed 给）
⑤ outline：模块/课次/进度聚合 + 资源过滤 + homework_done
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

_loop = asyncio.new_event_loop()
FI: dict = {}


def _run(coro):
    """模块级持久循环上运行协程。

    asyncmy 的 Pool 绑定创建时所在循环；且 asyncio_mode=auto 下 pytest-asyncio 会
    关闭当前线程循环。故复用同一 _loop 且每次操作前 set 为当前，避免 Event loop is
    closed（task37 根因修复，同 test_contract_task22）。
    """
    asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)


async def _find_fixture() -> dict | None:
    """找：一个有 active 报名的系列 + 该系列一个 enrolled_only 视频课次 + 一个未报名用户。"""
    enr = await fetch_one(
        "SELECT scr.user_id, c.series_id, c.id AS cohort_id FROM student_cohort_rel scr"
        " JOIN series_cohort c ON c.id = scr.cohort_id"
        " WHERE scr.enroll_status='active'"
        " AND EXISTS (SELECT 1 FROM session_asset sa"
        "   JOIN series_cohort_session scs ON scs.id = sa.session_id"
        "   JOIN series_cohort_course ccc ON ccc.id = scs.series_cohort_course_id"
        "   WHERE ccc.cohort_id = c.id AND sa.material_category='video')"
        " LIMIT 1")
    if not enr:
        return None
    # enrolled_only 课次
    sess = await fetch_one(
        "SELECT sa.session_id FROM session_asset sa"
        " JOIN series_cohort_session scs ON scs.id = sa.session_id"
        " JOIN series_cohort_course ccc ON ccc.id = scs.series_cohort_course_id"
        " JOIN series_cohort c ON c.id = ccc.cohort_id"
        " WHERE c.series_id=%s AND sa.material_category='video'"
        " AND sa.access_scope='enrolled_only' LIMIT 1", (int(enr["series_id"]),))
    return {
        "user_id": int(enr["user_id"]),
        "series_id": int(enr["series_id"]),
        "cohort_id": int(enr["cohort_id"]),
        "session_id": int(sess["session_id"]) if sess else None,
    }


async def _req(method: str, path: str, user_id: int | None, body=None):
    transport = httpx.ASGITransport(app=app)
    headers = {}
    if user_id is not None:
        headers = {"X-Force-Role": "admin", "X-Force-User-Id": str(user_id)}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        if method == "GET":
            return await c.get(path, headers=headers)
        return await c.post(path, headers=headers, json=body or {})


def _call(method: str, path: str, user_id: int | None = None, body=None):
    return _run(_req(method, path, user_id, body))


async def _find_non_enrolled_user(series_id: int) -> int:
    """找一个未报名该系列的用户。"""
    row = await fetch_one(
        "SELECT id FROM sys_user WHERE yn=1"
        " AND id NOT IN (SELECT scr.user_id FROM student_cohort_rel scr"
        "   JOIN series_cohort c ON c.id = scr.cohort_id WHERE c.series_id=%s)"
        " LIMIT 1", (series_id,))
    return int(row["id"]) if row else 0


@pytest.fixture(scope="module", autouse=True)
def _init():
    _run(init_mysql())
    row = _run(_find_fixture())
    assert row, "无可用夹具：需一个 active 报名 + enrolled_only 视频课次的系列"
    non_enr = _run(_find_non_enrolled_user(row["series_id"]))
    assert non_enr, "无未报名用户可测 403"
    FI.update({**row, "non_enrolled_user": non_enr})
    yield
    _run(close_mysql())


class TestAccessAuthz:
    def test_enrolled_accessible(self):
        """已报名用户 access → accessible=true。"""
        r = _call("GET", f"/api/study/courses/{FI['series_id']}/access", user_id=FI["user_id"])
        assert r.status_code == 200 and r.json()["code"] == 0
        d = r.json()["data"]
        assert d["accessible"] is True and d["series_id"] == FI["series_id"]

    def test_non_enrolled_403_detail(self):
        """GWT①：未报名用户请求 enrolled_only 课次视频 → 403（40330「需报名」）。"""
        if not FI.get("session_id"):
            pytest.skip("夹具系列无 enrolled_only 视频课次")
        r = _call("GET", f"/api/study/sessions/{FI['session_id']}", user_id=FI["non_enrolled_user"])
        assert r.status_code == 403, f"未报名应 403, got {r.status_code}: {r.text[:200]}"
        assert r.json()["code"] == "40330"

    def test_enrolled_can_view_detail(self):
        """已报名用户课次详情 → 200，assets/video 返回。"""
        if not FI.get("session_id"):
            pytest.skip("无 enrolled_only 视频课次")
        r = _call("GET", f"/api/study/sessions/{FI['session_id']}", user_id=FI["user_id"])
        assert r.status_code == 200 and r.json()["code"] == 0
        d = r.json()["data"]
        assert isinstance(d["assets"], list)
        assert d["session_id"] == FI["session_id"]


class TestSessionDetailAssets:
    def test_assets_filtered_by_scope(self):
        """GWT③：课次详情 assets 仅含该用户可访问 scope（不含 internal_only）。"""
        if not FI.get("session_id"):
            pytest.skip("无课次")
        r = _call("GET", f"/api/study/sessions/{FI['session_id']}", user_id=FI["user_id"])
        d = r.json()["data"]
        scopes = {a["access_scope"] for a in d["assets"]}
        assert "internal_only" not in scopes, "C 端不应返回 internal_only 资源"
        # material_category 枚举合法
        cats = {a["material_category"] for a in d["assets"]}
        assert cats <= {"video", "handout", "exercise", "reference", "image"}

    def test_transcode_status_valid(self):
        """GWT④：video.transcode_status ∈ {pending,in_progress,completed,failed}；url 仅 completed 给。"""
        if not FI.get("session_id"):
            pytest.skip("无课次")
        r = _call("GET", f"/api/study/sessions/{FI['session_id']}", user_id=FI["user_id"])
        d = r.json()["data"]
        v = d.get("video")
        if v:
            assert v["transcode_status"] in ("pending", "in_progress", "completed", "failed")
            if v["transcode_status"] != "completed":
                assert v["video_url"] is None, "非 completed 不应给可播 url"


class TestOutline:
    def test_outline_structure(self):
        """GWT②：outline 模块/课次/进度 + 资源过滤 + homework_done。"""
        r = _call("GET", f"/api/study/courses/{FI['series_id']}/outline", user_id=FI["user_id"])
        assert r.status_code == 200 and r.json()["code"] == 0
        d = r.json()["data"]
        assert d["series_id"] == FI["series_id"]
        assert d["total_sessions"] >= 1
        assert isinstance(d["overall_ratio"], (int, float))
        assert isinstance(d["modules"], list) and len(d["modules"]) >= 1
        sess = d["modules"][0]["sessions"]
        if sess:
            s0 = sess[0]
            assert "session_id" in s0 and "session_no" in s0 and "watch_ratio" in s0
            assert isinstance(s0["homework_done"], bool)
            if s0["transcode_status"] == "completed":
                assert s0["video_url"] is not None
            else:
                assert s0["video_url"] is None


class TestSessionComplete:
    def test_complete(self):
        """课次完成态（有播放会话 → completed=true）。"""
        if not FI.get("session_id"):
            pytest.skip("无课次")
        r = _call("POST", f"/api/study/sessions/{FI['session_id']}/complete", user_id=FI["user_id"])
        assert r.status_code == 200 and r.json()["code"] == 0
        assert isinstance(r.json()["data"]["completed"], bool)

    def test_complete_404(self):
        r = _call("POST", "/api/study/sessions/99999999/complete", user_id=FI["user_id"])
        assert r.status_code == 404