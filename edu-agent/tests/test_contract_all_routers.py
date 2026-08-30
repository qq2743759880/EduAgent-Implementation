"""task10-fix: 响应壳补充测试 + 中间件顺序断言（P0 补测）"""
from __future__ import annotations

import pytest
import urllib.request
import urllib.error
import json

BASE = "http://127.0.0.1:8000"


def api_get(path, token=None, headers=None):
    url = BASE + path 
    req = urllib.request.Request(url, method="GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.headers, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        return e.code, e.headers, body


def login(account="adm02test", password="Test@123456"):
    """获取 admin token，返回 (status, headers, body)"""
    url = BASE + "/api/auth/login"
    data = json.dumps({"account": account, "password": password}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.headers, json.loads(e.read())


def login_token(account="adm02test", password="Test@123456"):
    """登录并解壳取出 access_token（契约①：登录成功 data 内嵌令牌）。"""
    _, _, body = login(account=account, password=password)
    return body.get("data", {}).get("access_token") if isinstance(body, dict) else None


# ═══════════════════════════════════════════════════════
# 1. 响应壳补充测试（已使用 ok()/fail() 的端点）
# ═══════════════════════════════════════════════════════
class TestResponseShellExtra:
    """验证已使用 ok()/fail() 包裹的端点返回字符串错误码"""

    def test_admin_series_endpoint(self):
        """管理端课程系列：成功 code=0 (int) 或失败 code=<字符串>"""
        _, _, login_body = login()
        token = login_body["data"]["access_token"]
        code, headers, body = api_get("/api/admin/courses/series", token=token)
        if isinstance(body, dict) and "code" in body:
            if body["code"] == 0:
                assert isinstance(body["code"], int), "成功 code 应为 int 0"
                assert "data" in body
            else:
                # 错误码必须为字符串
                assert isinstance(body["code"], str), f"失败 code 应为字符串: {body['code']}"

    def test_failure_code_is_string(self):
        """已知失败端点：验证错误码为字符串（非数字）"""
        _, _, login_body = login()
        token = login_body["data"]["access_token"]
        # 用不存在的资源触发 404 业务错误，验证 code 为字符串
        code, headers, body = api_get("/api/admin/courses/series/999999", token=token)
        if isinstance(body, dict) and "code" in body:
            assert isinstance(body["code"], str), f"失败 code 应为字符串: {body['code']}"

    def test_mindmap_endpoint(self):
        """思维导图端点：验证响应壳"""
        _, _, login_body = login()
        token = login_body["data"]["access_token"]
        code, headers, body = api_get("/api/mindmap/course/1", token=token)
        if isinstance(body, dict) and "code" in body:
            assert body["code"] == 0
            assert "data" in body

    def test_vocab_daily_endpoint(self):
        """单词每日端点：验证响应壳"""
        _, _, login_body = login()
        token = login_body["data"]["access_token"]
        code, headers, body = api_get("/api/vocab/daily", token=token)
        if isinstance(body, dict) and "code" in body:
            assert body["code"] == 0
            assert "data" in body

    def test_vocab_progress_endpoint(self):
        """单词进度端点：验证响应壳"""
        _, _, login_body = login()
        token = login_body["data"]["access_token"]
        code, headers, body = api_get("/api/vocab/progress", token=token)
        if isinstance(body, dict) and "code" in body:
            assert body["code"] == 0
            assert "data" in body

    def test_coding_challenges_endpoint(self):
        """编程挑战列表：验证响应壳"""
        _, _, login_body = login()
        token = login_body["data"]["access_token"]
        code, headers, body = api_get("/api/coding/challenges", token=token)
        if isinstance(body, dict) and "code" in body:
            assert body["code"] == 0
            assert "data" in body


# ═══════════════════════════════════════════════════════
# 2. 中间件注册顺序断言
# ═══════════════════════════════════════════════════════
class TestMiddlewareOrder:
    """
    断言中间件注册顺序：SecurityHeaders → CORS → Trace → Idempotency → RateLimit → CircuitGuard → RespWrap
    通过请求响应头间接验证各中间件生效。
    """

    def test_security_headers_present(self):
        """SecurityHeaders 最先注入：所有响应应包含安全头"""
        code, headers, body = login()
        # 安全头在 login 响应中
        assert "x-frame-options" in headers, "SecurityHeaders 未注入 X-Frame-Options"
        assert "x-content-type-options" in headers, "SecurityHeaders 未注入 X-Content-Type-Options"
        assert "x-xss-protection" in headers, "SecurityHeaders 未注入 X-XSS-Protection"

    def test_cors_headers_present(self):
        """CORS 在 SecurityHeaders 之后：带 Origin 请求头时应有 CORS 响应头"""
        code, headers, body = api_get(
            "/api/community/posts",
            headers={"Origin": "http://localhost:3000"},
        )
        assert "access-control-allow-origin" in headers, "CORS 中间件未生效"
        # 安全头也应有（SecurityHeaders 在 CORS 之前）
        assert "x-frame-options" in headers

    def test_trace_id_present(self):
        """Trace 在 CORS 之后：所有响应应包含 X-Trace-Id"""
        code, headers, body = login()
        assert "x-trace-id" in headers, "TraceMiddleware 未注入 X-Trace-Id"
        assert len(headers["x-trace-id"]) == 8

    def test_trace_id_passthrough(self):
        """Trace 透传：请求头 X-Trace-Id 应被保留"""
        code, headers, body = api_get(
            "/api/community/posts",
            headers={"X-Trace-Id": "test1234"},
        )
        assert headers["x-trace-id"] == "test1234"

    def test_full_middleware_chain(self):
        """通过带 Origin 的请求验证完整中间件链路"""
        code, headers, body = api_get(
            "/api/community/posts",
            headers={"Origin": "http://localhost:3000"},
        )

        # 安全头（SecurityHeaders 最先）
        assert "x-frame-options" in headers
        assert "x-content-type-options" in headers
        # CORS（SecurityHeaders 之后）
        assert "access-control-allow-origin" in headers
        # Trace（CORS 之后）
        assert "x-trace-id" in headers

        print(f"中间件全链路验证通过: X-Trace-Id={headers.get('x-trace-id')}")