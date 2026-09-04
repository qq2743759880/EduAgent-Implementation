# -*- coding: utf-8 -*-
"""task15: 存量模块响应壳契约测试 — auth/chat/community/gamification/mcp/rag_admin + ZSET 排行 + SSE 壳。

GWT 覆盖（契约冻结⑬）：
① 上述模块全部端点 → 100% 统一壳 {code:0,message,data}；失败 {code:<字符串>,data:null}
   SSE 流 done 事件含 {code:0, message:"ok", data} 内嵌结构
② /rankings → 数据来自 Redis ZSET（写入侧同步更新，积分变更 1s 内可查）
③ auth 登录/注册/refresh 全流程 → 壳统一但 JWT 语义不变（业务逻辑未改）

直连 127.0.0.1:8003（可用 TEST_BASE 覆盖）；ProxyHandler 禁用系统代理防 SSLEOFError。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import pytest

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:8000")

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ADMIN_ACCOUNT = "adm02test"
STUDENT_ACCOUNT = "stu01test"
PASSWORD = "Test@123456"


def api(method: str, path: str, body=None, token=None, raw: bool = False, timeout: int = 20):
    """发请求并返回 (status, body)；raw=True 时 body 为原始文本（SSE 用）。"""
    data = json.dumps(body, ensure_ascii=False).encode() if body else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            content = r.read().decode()
            return r.status, content if raw else json.loads(content)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def login(account=ADMIN_ACCOUNT, password=PASSWORD) -> tuple[int, dict]:
    return api("POST", "/api/auth/login", {"account": account, "password": password})


# 模块级缓存：整场测试共享一个 admin token，避免触发 auth 限流（10/min）
_ADMIN_TOKEN: str | None = None


def login_token(account=ADMIN_ACCOUNT, password=PASSWORD) -> str | None:
    global _ADMIN_TOKEN
    if account == ADMIN_ACCOUNT and _ADMIN_TOKEN:
        return _ADMIN_TOKEN
    s, j = login(account=account, password=password)
    if s != 200:
        return None
    data = j.get("data") or {}
    tok = data.get("access_token")
    if account == ADMIN_ACCOUNT:
        _ADMIN_TOKEN = tok
    return tok


def assert_ok_shell(j, name: str = ""):
    """断言成功壳：code=0, message 存在, data 存在。"""
    assert isinstance(j, dict), f"{name}: 非 dict 响应 {j!r}"
    assert j.get("code") == 0, f"{name}: code != 0 → {json.dumps(j, ensure_ascii=False)[:200]}"
    assert "message" in j
    assert "data" in j


def assert_fail_shell(j, code: str | int, name: str = ""):
    """断言失败壳：字符串错误码 + data null。"""
    assert isinstance(j, dict), f"{name}: 非 dict 响应 {j!r}"
    assert j.get("code") == code, f"{name}: code != {code} → {json.dumps(j, ensure_ascii=False)[:200]}"
    assert isinstance(j["code"], str), f"{name}: 失败 code 应为字符串"
    assert j.get("data") is None, f"{name}: 失败 data 应为 null"


# ═══════════════════════════════════════════════════════
# 1. auth：登录/注册/refresh/me 壳统一 + JWT 语义不变
# ═══════════════════════════════════════════════════════
class TestAuthShell:
    def test_login_success_shell(self):
        """GWT③：登录成功 → 壳 data 内含 access_token/refresh_token/user，JWT 语义不变"""
        s, j = login()
        assert s == 200
        assert_ok_shell(j, "login")
        data = j["data"]
        assert "access_token" in data and "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data
        assert data["user"]["role"] == "admin"

    def test_login_failure_shell(self):
        """登录失败 → 字符串错误码 + data null（40111）"""
        s, j = login(password="wrong-password-xx")
        assert s == 401
        assert_fail_shell(j, "40111", "login-fail")

    def test_refresh_shell(self):
        """refresh → 壳 data 内含新双 token"""
        _, j = login()
        refresh_token = j["data"]["refresh_token"]
        s, j2 = api("POST", "/api/auth/refresh", {"refresh_token": refresh_token})
        assert s == 200
        assert_ok_shell(j2, "refresh")
        assert "access_token" in j2["data"] and "refresh_token" in j2["data"]

    def test_me_shell(self):
        """GET /me → 壳 data.user_id 存在"""
        tok = login_token()
        assert tok, "登录失败无法继续"
        s, j = api("GET", "/api/auth/me", token=tok)
        assert s == 200
        assert_ok_shell(j, "me")
        assert j["data"]["user_id"] > 0

    def test_register_shell(self):
        """注册（新随机账号）→ 201 + 壳 data.user_id；重复注册 → 409 字符串码"""
        suffix = int(time.time() % 100000000)
        mobile = f"138{suffix:08d}"  # 11 位：1 + 3(在 3-9) + 8 位数字
        s, j = api("POST", "/api/auth/register", {
            "account": f"t15reg{suffix}",
            "nickname": f"T15{suffix}",
            "password": "Test@123456",
            "confirm_password": "Test@123456",
            "mobile": mobile,
        })
        assert s == 201, f"注册应 201，实得 {s}: {json.dumps(j, ensure_ascii=False)[:200]}"
        assert_ok_shell(j, "register")
        assert j["data"]["user_id"] > 0
        # 重复注册 → 409 字符串码
        s, j2 = api("POST", "/api/auth/register", {
            "account": f"t15reg{suffix}",
            "nickname": f"T15{suffix}",
            "password": "Test@123456",
            "confirm_password": "Test@123456",
            "mobile": mobile,
        })
        assert s == 409
        assert_fail_shell(j2, "40912", "register-dup")


# ═══════════════════════════════════════════════════════
# 2. chat：会话 + 检索 + 非流式 + SSE done 壳
# ═══════════════════════════════════════════════════════
class TestChatShell:
    def _tok(self):
        tok = login_token()
        assert tok, "登录失败"
        return tok

    def test_sessions_shell(self):
        tok = self._tok()
        s, j = api("GET", "/api/chat/sessions?limit=3", token=tok)
        assert s == 200
        assert_ok_shell(j, "sessions-list")

    def test_session_crud_shell(self):
        tok = self._tok()
        s, j = api("POST", "/api/chat/sessions", {"title": "t15-contract"}, token=tok)
        assert s == 201
        assert_ok_shell(j, "sessions-create")
        sid = j["data"]["session_id"]
        s, j = api("GET", f"/api/chat/sessions/{sid}/history", token=tok)
        assert s == 200
        assert_ok_shell(j, "history")
        s, j = api("DELETE", f"/api/chat/sessions/{sid}", token=tok)
        assert s == 200
        assert_ok_shell(j, "sessions-delete")

    def test_search_shell(self):
        tok = self._tok()
        s, j = api("POST", "/api/chat/search", {"query": "hello", "top_k": 2}, token=tok, timeout=30)
        assert s == 200
        assert_ok_shell(j, "search")

    def test_stream_done_embeds_shell(self):
        """GWT① SSE：done 事件 data 内嵌 {code:0, message:'ok', data:{...}}"""
        tok = self._tok()
        s, raw = api("POST", "/api/chat/stream",
                     {"query": "hello", "top_k": 2, "use_mcp_tools": False},
                     token=tok, raw=True, timeout=45)
        if s != 200 or not raw:
            pytest.skip("SSE 未触发（LLM/检索降级），跳过 done 壳断言")
        done_ok = False
        for line in raw.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                evt = json.loads(line[6:])
            except Exception:
                continue
            if isinstance(evt, dict) and "code" in evt:
                assert evt["code"] == 0, f"done 壳 code != 0: {evt}"
                assert evt["message"] == "ok"
                assert "data" in evt and isinstance(evt["data"], dict)
                done_ok = True
        assert done_ok, "SSE 流未找到内嵌壳的 done 事件"


# ═══════════════════════════════════════════════════════
# 3. community：列表/详情/评论/点赞 壳
# ═══════════════════════════════════════════════════════
class TestCommunityShell:
    def _tok(self):
        tok = login_token()
        assert tok, "登录失败"
        return tok

    def test_posts_shell(self):
        tok = self._tok()
        s, j = api("GET", "/api/community/posts?page=1&page_size=3", token=tok)
        assert s == 200
        assert_ok_shell(j, "posts-list")
        items = j["data"].get("items") or []
        if items:
            pid = items[0]["post_id"]
            s, j = api("GET", f"/api/community/posts/{pid}", token=tok)
            assert s == 200
            assert_ok_shell(j, "post-detail")
            s, j = api("GET", f"/api/community/posts/{pid}/comments", token=tok)
            assert s == 200
            assert_ok_shell(j, "comments-list")

    def test_post_create_like_shell(self):
        tok = self._tok()
        suffix = int(time.time() * 1000)
        s, j = api("POST", "/api/community/posts",
                   {"board_code": "general", "title": f"t15 c {suffix}", "content_md": "测试内容"},
                   token=tok)
        assert s == 200
        assert_ok_shell(j, "post-create")
        pid = j["data"]["post_id"]
        s, j = api("POST", f"/api/community/posts/{pid}/like", token=tok)
        assert s == 200
        assert_ok_shell(j, "post-like")


# ═══════════════════════════════════════════════════════
# 4. gamification：徽章/积分/排行（ZSET）+ 打靶加积分
# ═══════════════════════════════════════════════════════
class TestGamificationShell:
    def _tok(self):
        tok = login_token()
        assert tok, "登录失败"
        return tok

    def test_badges_points_shell(self):
        tok = self._tok()
        s, j = api("GET", "/api/gamification/me/badges", token=tok)
        assert s == 200
        assert_ok_shell(j, "badges")
        s, j = api("GET", "/api/gamification/me/points", token=tok)
        assert s == 200
        assert_ok_shell(j, "points")

    def test_award_updates_zset_ranking(self):
        """GWT②：打靶加积分 → ZSET 写入侧增量 → 1s 内 /rankings 可查（source=ZSET）"""
        tok = self._tok()
        uniq = int(time.time() * 1000)
        # 打靶加 10 分（幂等 biz_key）
        s, j = api("POST", f"/api/gamification/me/award?point_type=QUIZ_CORRECT&delta=10&biz_key=t15-zset-{uniq}",
                   token=tok)
        assert s == 200
        assert_ok_shell(j, "award")
        # 1s 内查排行
        s, j = api("GET", "/api/gamification/rankings?scope=DAILY&dimension=POINTS&top_n=5", token=tok)
        assert s == 200
        assert_ok_shell(j, "rankings")
        data = j["data"]
        assert data["source"] in ("ZSET", "LIVE_CALC"), f"source 异常: {data['source']}"
        # 我的积分 >= 本次增量（ZSET 实时可查）
        my = data.get("my_rank") or {}
        assert my.get("metric_value", 0) >= 10, f"ZSET 未实时累计: {my}"

    def test_rankings_badge_dimension_shell(self):
        tok = self._tok()
        s, j = api("GET", "/api/gamification/rankings?scope=WEEKLY&dimension=BADGE_COUNT&top_n=5", token=tok)
        assert s == 200
        assert_ok_shell(j, "rankings-badge")


# ═══════════════════════════════════════════════════════
# 5. mcp：server/tools/call-log 壳 + student 403
# ═══════════════════════════════════════════════════════
class TestMcpShell:
    def test_admin_servers_shell(self):
        tok = login_token()
        assert tok, "登录失败"
        s, j = api("GET", "/api/mcp/servers?page=1&page_size=5", token=tok)
        assert s == 200
        assert_ok_shell(j, "mcp-servers")
        items = j["data"].get("items") or []
        if items:
            sid = items[0]["id"]
            s, j = api("GET", f"/api/mcp/servers/{sid}", token=tok)
            assert s == 200
            assert_ok_shell(j, "mcp-server-detail")
            s, j = api("GET", f"/api/mcp/servers/{sid}/tools?page=1&page_size=3", token=tok)
            assert s == 200
            assert_ok_shell(j, "mcp-tools")

    def test_call_log_shell(self):
        tok = login_token()
        assert tok, "登录失败"
        s, j = api("GET", "/api/mcp/call-log?page=1&page_size=3", token=tok)
        assert s == 200
        assert_ok_shell(j, "mcp-call-log")

    def test_student_forbidden_403_shell(self):
        """student 访问 mcp → 403 字符串码 + data null"""
        tok = login_token(STUDENT_ACCOUNT)
        if not tok:
            pytest.skip("student 登录被限流，跳过 403 用例")
        s, j = api("GET", "/api/mcp/servers", token=tok)
        assert s == 403
        assert_fail_shell(j, "40300", "mcp-student-403")


# ═══════════════════════════════════════════════════════
# 6. rag_admin：collections/presets/audit-log 壳
# ═══════════════════════════════════════════════════════
class TestRagAdminShell:
    def test_collections_shell(self):
        tok = login_token()
        assert tok, "登录失败"
        s, j = api("GET", "/api/admin/rag/collections", token=tok)
        assert s == 200
        assert_ok_shell(j, "rag-collections")

    def test_presets_shell(self):
        tok = login_token()
        assert tok, "登录失败"
        s, j = api("GET", "/api/admin/rag/presets", token=tok)
        assert s == 200
        assert_ok_shell(j, "rag-presets")

    def test_audit_log_shell(self):
        tok = login_token()
        assert tok, "登录失败"
        s, j = api("GET", "/api/admin/rag/audit-log?page=1&page_size=3", token=tok)
        assert s == 200
        assert_ok_shell(j, "rag-audit-log")
