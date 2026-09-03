# -*- coding: utf-8 -*-
"""Season-2 后端缺口契约测试：管理端交易运营聚合 + 课程评价 CRUD。

覆盖：
① 管理端守卫：trade overview 与 reviews admin 共同依赖 require_role([ADMIN, MANAGER])（离线单测）
② 评价 service 业务规则：未报名 403 / 重复评价 ConflictError(STUDY_REVIEW_DUPLICATE)（monkeypatch，离线）
③ 真实 HTTP 独立实证（live backend）：overview 200/403 + 评价 CRUD 全链 / 分页壳 / 防刷 / 软删

测试策略（对齐 task113）：
- ①/② 离线（不依赖 live backend）；/api/admin/* 前缀被 AdminAuthMiddleware 强制真实 token
  （AGENTS 教训⑤），离线侧直接单测 require_role 守卫，端到端权限由 ③ 真实 HTTP 保证
- ③ 用 live backend（127.0.0.1:8000）经真实 HTTP 实跑；后端不可达由 conftest 自动 skip
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import sys as _sys  # noqa: E402
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.auth.schemas import UserInfo, UserRole  # noqa: E402
from app.common.error_codes import STUDY_REVIEW_DUPLICATE  # noqa: E402


def _user(role: UserRole, uid: int = 1) -> UserInfo:
    return UserInfo(user_id=uid, nickname="t", real_name="t", mobile=None,
                   email="t@e", gender=None, avatar_url=None, role=role)


# ══════════════════════════════════════════════════════════════
# 离线 TestClient 权限测试（monkeypatch，不依赖 live backend）
# ══════════════════════════════════════════════════════════════
class TestAdminRoleGate:
    """需求 A/B：管理端着陆 require_role([ADMIN, MANAGER]) 同一守卫直接单测。

    说明：/api/admin/* 前缀被 AdminAuthMiddleware 强制真实 token（AGENTS 教训⑤），
    TestClient dependency_overrides 无法覆盖它（离线调用返回 401）。因此离线侧
    直接单测 require_role 守卫工厂（两个 admin 路由都用它的返回值），端到端权限
    由下方 Live HTTP 实证（admin 200 / student 403）保证。
    """

    async def _assert_gate(self, role, allowed: bool):
        from fastapi import HTTPException
        from app.auth import require_role

        check = require_role([UserRole.ADMIN, UserRole.MANAGER])
        try:
            await check(_user(role))
        except HTTPException as exc:
            assert not allowed, f"{role} 应放行却 403"
            assert exc.status_code == 403
            return
        assert allowed, f"{role} 应 403 却放行"

    def test_trade_overview_gate(self):
        import asyncio
        asyncio.run(self._assert_gate(UserRole.STUDENT, allowed=False))
        asyncio.run(self._assert_gate(UserRole.ADMIN, allowed=True))
        asyncio.run(self._assert_gate(UserRole.MANAGER, allowed=True))

    def test_reviews_admin_gate(self):
        import asyncio
        asyncio.run(self._assert_gate(UserRole.STUDENT, allowed=False))
        asyncio.run(self._assert_gate(UserRole.ADMIN, allowed=True))
        asyncio.run(self._assert_gate(UserRole.MANAGER, allowed=True))


class TestReviewServiceRules:
    """需求 B：评价提交业务规则（未报名 403 / 重复评价 409）。"""

    def test_not_enrolled_forbidden(self, monkeypatch):
        import app.domains.review.service as svc
        from app.common.exceptions import PermissionDeniedError

        class FakeRepo:
            async def get_series(self, sid):
                return {"id": sid, "series_name": "x", "sale_status": "on_sale"}

            async def is_enrolled(self, sid, uid):
                return False

        monkeypatch.setattr(svc, "repo", FakeRepo())
        with pytest.raises(PermissionDeniedError):
            import asyncio
            asyncio.run(svc.create_review(1, 1, 5, "good"))

    def test_duplicate_review_conflict(self, monkeypatch):
        import asyncio
        import app.domains.review.service as svc
        from app.common.exceptions import ConflictError

        class FakeRepo:
            async def get_series(self, sid):
                return {"id": sid, "series_name": "x", "sale_status": "on_sale"}

            async def is_enrolled(self, sid, uid):
                return True

            async def get_active(self, sid, uid):
                return {"id": 9, "rating": 5, "content": "old", "yn": 1}

        monkeypatch.setattr(svc, "repo", FakeRepo())
        with pytest.raises(ConflictError) as exc:
            asyncio.run(svc.create_review(1, 1, 4, "again"))
        assert exc.value.code == STUDY_REVIEW_DUPLICATE


# ══════════════════════════════════════════════════════════════
# 真实 HTTP 独立实证（live backend，需真实 token + 真实 DB）
# ══════════════════════════════════════════════════════════════
_BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:8000")
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")


def _api(method, path, token=None, json_body=None):
    data = json.dumps(json_body).encode() if json_body is not None else None
    req = urllib.request.Request(f"{_BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with _OPENER.open(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def _login(account, password="Test@123456"):
    return _api("POST", "/api/auth/login", json_body={"account": account, "password": password})


def _token(account):
    s, j = _login(account)
    assert s == 200 and isinstance(j, dict) and j.get("code") == 0, f"登录失败 {account}: {s} {j}"
    return j["data"]["access_token"]


# 实证用固定系列：user000001(user_id=1) 已报名 series 1（DB 实测 enroll_status=active）
_REVIEW_SERIES = 1


class TestTradeOverviewLive:
    def test_admin_overview_200(self):
        tok = _token("adm02test")
        s, j = _api("GET", f"/api/admin/trade/overview?top_n=5", token=tok)
        assert s == 200, f"overview 应 200，实得 {s} {j}"
        assert j.get("code") == 0, j
        data = j.get("data") or {}
        for key in ("top_series", "revenue", "orders"):
            assert key in data, f"overview 缺字段 {key}"
        assert isinstance(data["orders"].get("by_status"), dict), "orders.by_status 应为 dict"

    def test_student_overview_forbidden(self):
        tok = _token("user000001")
        s, _ = _api("GET", "/api/admin/trade/overview", token=tok)
        assert s == 403, f"student 应 403，实得 {s}"

    def test_bad_token_denied(self):
        s, _ = _api("GET", "/api/admin/trade/overview", token="Bearer-garbage.invalid.token")
        assert s in (401, 403), f"无效 token 应 401/403，实得 {s}"


class TestReviewCrudLive:
    """评价 CRUD 全链（真实 HTTP + 真实 DB，series 1，student user000001）。"""

    def _cleanup(self):
        import asyncio
        import asyncmy

        async def _run():
            conn = await asyncmy.connect(host="localhost", port=3306, user="root",
                                         password="123456", db="edu", charset="utf8mb4")
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM course_review WHERE series_id=%s AND user_id=%s",
                    (1, 1),
                )
            await conn.commit()

        asyncio.run(_run())

    def test_full_crud_chain(self):
        self._cleanup()  # 清残留，保证可重复
        student_tok = _token("user000001")
        admin_tok = _token("adm02test")

        # 1. POST 评价 → 200（已报名 series 1）
        s, j = _api("POST", f"/api/courses/{_REVIEW_SERIES}/reviews",
                    token=student_tok, json_body={"rating": 5, "content": "课程很棒"})
        assert s == 200, f"POST 评价应 200，实得 {s} {j}"
        review_id = (j.get("data") or {}).get("id")

        # 2. 重复 POST → 409（防刷）
        s2, j2 = _api("POST", f"/api/courses/{_REVIEW_SERIES}/reviews",
                      token=student_tok, json_body={"rating": 4, "content": "再来一次"})
        assert s2 == 409, f"重复评价应 409，实得 {s2} {j2}"
        assert j2.get("code") == STUDY_REVIEW_DUPLICATE, j2

        # 3. GET 列表分页壳正确（{total,page,page_size,items} + 昵称联表）
        s3, j3 = _api("GET", f"/api/courses/{_REVIEW_SERIES}/reviews?page=1&page_size=10", token=student_tok)
        assert s3 == 200 and j3.get("code") == 0, j3
        data = j3.get("data") or {}
        assert "total" in data and "items" in data, f"分页壳缺字段: {list(data.keys())}"
        assert data["total"] >= 1
        if data["items"]:
            assert "nickname" in data["items"][0], "列表应含昵称联表"

        # 4. 管理端列表过滤（series_id=1）
        s4, j4 = _api("GET", f"/api/admin/reviews?series_id={_REVIEW_SERIES}", token=admin_tok)
        assert s4 == 200 and j4.get("code") == 0, j4

        # 5. 管理端软删 → deleted
        s5, j5 = _api("DELETE", f"/api/admin/reviews/{review_id}", token=admin_tok)
        assert s5 == 200 and j5.get("code") == 0, f"软删应 200，实得 {s5} {j5}"
        assert (j5.get("data") or {}).get("deleted") is True

        # 6. 软删后同用户可重新评价（复活）
        s6, _ = _api("POST", f"/api/courses/{_REVIEW_SERIES}/reviews",
                     token=student_tok, json_body={"rating": 4, "content": "复活评价"})
        assert s6 == 200, f"软删后重新评价应 200，实得 {s6}"

        self._cleanup()