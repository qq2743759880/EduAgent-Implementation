# -*- coding: utf-8 -*-
"""task113 后端安全加固包 —— 七项收敛的契约测试。

覆盖 B1/B2/B3/P1 证据项与 task113-be-security.md 的 GWT：
① award 端点 require_role(ADMIN, MANAGER)
② mock-notify 两端点默认拒绝（仅 DEBUG=true 或 ADMIN/MANAGER）
③ quiz 下发模型排除 correct（保留服务端判分）
④ metrics 三端点加 ADMIN 鉴权
⑤ /api/memory/admin 前缀进 ADMIN_PREFIXES
⑥ COMMUNITY_REACT_INVALID 拆分新码 40024

测试策略：
- ①/②/③/⑥ 用 TestClient + dependency_overrides（不依赖 live backend，可在无服务环境跑）
- ② 的 deny 分支需 DEBUG=False，用 monkeypatch.settings.DEBUG 控制，并断言 deny 分支
- ④/⑤ 经 AdminAuthMiddleware（强制真实 token），用 live backend（127.0.0.1:8000）实跑；
  后端不可达时由 conftest 自动 skip（标注 expected）。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.schemas import UserInfo, UserRole
from app.common.error_codes import COMMUNITY_REACT_INVALID, TRADE_ORDER_STATUS_INVALID
from app.config import settings


def _user(role: UserRole, uid: int = 1) -> UserInfo:
    return UserInfo(user_id=uid, nickname="t", real_name="t", mobile=None,
                   email="t@e", gender=None, avatar_url=None, role=role)


def _client_with(user=None):
    from app.main import app

    app.dependency_overrides.clear()
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ══════════════════════════════════════════════════════════════
# 离线 TestClient 测试（①/②/③/⑥）—— 不依赖 live backend
# ══════════════════════════════════════════════════════════════
# ── ① award require_role（B1） ──
class TestAwardRoleGuard:
    def test_student_forbidden(self, monkeypatch):
        called = {}
        import app.gamification.service as gs

        async def fake_admin_award(*a, **k):
            called["hit"] = True
            return {"ok": True}

        monkeypatch.setattr(gs, "admin_award", fake_admin_award)
        c = _client_with(_user(UserRole.STUDENT))
        r = c.post("/api/gamification/me/award?point_type=QUIZ_CORRECT&delta=100&biz_key=z")
        assert r.status_code == 403, r.text
        assert "hit" not in called, "越权请求不应触达 service（DB 积分不变）"

    def test_admin_allowed(self, monkeypatch):
        called = {}
        import app.gamification.service as gs

        async def fake_admin_award(*a, **k):
            called["hit"] = True
            return {"ok": True}

        monkeypatch.setattr(gs, "admin_award", fake_admin_award)
        c = _client_with(_user(UserRole.ADMIN))
        r = c.post("/api/gamification/me/award?point_type=QUIZ_CORRECT&delta=10&biz_key=z")
        assert r.status_code == 200, r.text
        assert called.get("hit") is True

    def test_manager_allowed(self, monkeypatch):
        import app.gamification.service as gs

        async def fake_admin_award(*a, **k):
            return {"ok": True}

        monkeypatch.setattr(gs, "admin_award", fake_admin_award)
        c = _client_with(_user(UserRole.MANAGER))
        r = c.post("/api/gamification/me/award?point_type=QUIZ_CORRECT&delta=10&biz_key=z")
        assert r.status_code == 200, r.text


# ── ② mock-notify 默认拒绝（B2） ──
class _FakeNotifyResult:
    def model_dump(self, *a, **k):
        return {"ok": True}


async def _fake_mock_notify(*a, **k):
    return _FakeNotifyResult()


class TestMockNotifyGuard:
    def test_debug_false_student_forbidden(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        import app.domains.trade.payment.router as pr

        monkeypatch.setattr(pr.svc, "mock_notify", _fake_mock_notify)
        c = _client_with(_user(UserRole.STUDENT))
        r = c.post("/api/trade/payment/P-x/mock-notify")
        assert r.status_code == 403, r.text
        r2 = c.post("/payment-notifications/mock", json={"payment_no": "P-x", "third_party_trade_no": "T"})
        assert r2.status_code == 403, r2.text

    def test_debug_false_admin_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", False)
        import app.domains.trade.payment.router as pr

        monkeypatch.setattr(pr.svc, "mock_notify", _fake_mock_notify)
        c = _client_with(_user(UserRole.ADMIN))
        r = c.post("/api/trade/payment/P-x/mock-notify")
        assert r.status_code == 200, r.text

    def test_debug_true_student_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", True)
        import app.domains.trade.payment.router as pr

        monkeypatch.setattr(pr.svc, "mock_notify", _fake_mock_notify)
        c = _client_with(_user(UserRole.STUDENT))
        r = c.post("/api/trade/payment/P-x/mock-notify")
        assert r.status_code == 200, r.text


# ── ③ quiz 下发排除 correct，判分仍可用（B3） ──
def test_quiz_next_excludes_correct(monkeypatch):
    from app.interactive.quiz import service as qs
    from app.interactive.quiz.schemas import Question

    q = Question(custom_code="Q1", subject_code="math", question_type="SINGLE",
                 title="t", choices=[{"key": "A", "text": "a"}], correct="SECRET")

    async def fake_next(*a, **k):
        return q

    monkeypatch.setattr(qs, "next_question", fake_next)
    c = _client_with(_user(UserRole.STUDENT))
    r = c.get("/api/interactive/quiz/next")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "correct" not in body, f"下发 JSON 仍含 correct: {body}"


def test_quiz_correct_excluded_but_gradable():
    from app.interactive.quiz import service as qs
    from app.interactive.quiz.schemas import Question

    q = Question(custom_code="Q1", subject_code="math", question_type="SINGLE",
                 title="t", choices=[{"key": "A", "text": "a"}], correct="A")
    assert "correct" not in q.model_dump(), "correct 应从序列化中排除（防 C 端泄漏）"
    is_correct, score, _ = qs._grade(q, "A")
    assert is_correct is True and score == 5.0
    is_correct2, _, _ = qs._grade(q, "B")
    assert is_correct2 is False


# ── ⑥ 错误码拆分 ──
def test_community_react_invalid_split():
    assert COMMUNITY_REACT_INVALID == "40024"
    assert COMMUNITY_REACT_INVALID != TRADE_ORDER_STATUS_INVALID
    assert TRADE_ORDER_STATUS_INVALID == "40021"  # 仍归交易域独占，不再被社区域复用


# ══════════════════════════════════════════════════════════════
# ④/⑤ live backend 集成测试（经 AdminAuthMiddleware，需真实 token）
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
        with _OPENER.open(req, timeout=20) as r:
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


class TestMetricsAuthLive:
    def test_no_token_401(self):
        s, _ = _api("GET", "/api/metrics/otel")
        assert s == 401, f"无 token 应 401，实得 {s}"

    def test_student_forbidden(self):
        tok = _token("user000001")
        s, _ = _api("GET", "/api/metrics/otel", token=tok)
        assert s == 403, f"student 应 403，实得 {s}"
        s2, _ = _api("GET", "/api/metrics/cache-context-dashboard", token=tok)
        assert s2 == 403
        s3, _ = _api("GET", "/api/metrics/trace/abc", token=tok)
        assert s3 == 403

    def test_admin_allowed(self):
        tok = _token("adm02test")
        s, _ = _api("GET", "/api/metrics/otel", token=tok)
        assert s == 200, f"admin 应 200，实得 {s}"
        s2, _ = _api("GET", "/api/metrics/cache-context-dashboard", token=tok)
        assert s2 == 200


class TestMemoryAdminPrefixLive:
    def test_no_token_401(self):
        s, _ = _api("POST", "/api/memory/admin/dream/run", json_body={"user_id": 999})
        assert s == 401, f"无 token 应 401，实得 {s}"

    def test_student_forbidden(self):
        tok = _token("user000001")
        s, _ = _api("POST", "/api/memory/admin/dream/run", json_body={"user_id": 999}, token=tok)
        assert s == 403, f"student 应 403，实得 {s}"

    def test_admin_allowed(self):
        tok = _token("adm02test")
        s, _ = _api("POST", "/api/memory/admin/dream/run", json_body={"user_id": 999}, token=tok)
        assert s not in (401, 403), f"admin 不应被鉴权拦截，实得 {s}"


class TestAwardLive:
    def test_student_forbidden(self):
        tok = _token("user000001")
        s, _ = _api("POST", "/api/gamification/me/award?point_type=QUIZ_CORRECT&delta=100&biz_key=z", token=tok)
        assert s == 403, f"student 应 403，实得 {s}"


class TestQuizNextLive:
    def test_next_excludes_correct(self):
        tok = _token("user000001")
        s, j = _api("GET", "/api/interactive/quiz/next", token=tok)
        body = j.get("data", j) if isinstance(j, dict) else j
        if isinstance(body, dict):
            assert "correct" not in body, f"下发 JSON 含 correct: {body}"
        assert s in (200, 404, 400), f"unexpected status {s}"
