# -*- coding: utf-8 -*-
"""AUTO20 T6：限流前缀收窄（段边界 + 最长前缀优先）+ 429 CORS 头测试。

根因（编排者实证）：旧 startswith 前缀匹配下 "/api/trade/order" 规则
（10 次/60s）误伤 GET /api/trade/orders（订单列表）——学生页连拉列表
第 11 次起 429，且 429 短路响应不带 access-control-allow-origin 头，
浏览器报成 CORS 错误 → me 页 console-errors 假红。

修复：匹配语义收窄为段边界 + 最长前缀优先；阈值/窗口一律未动。
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from app.middleware.rate_limit import (
    _get_limit_for_path,
    _path_in_prefix_scope,
    RateLimitMiddleware,
    _RATE_LIMIT_RULES,
)


# ─────────────────────────────────────────────────────────────
# ① 段边界匹配原语
# ─────────────────────────────────────────────────────────────
class TestPathInPrefixScope:
    def test_exact_path_hits(self):
        assert _path_in_prefix_scope("/api/trade/order", "/api/trade/order")

    def test_subpath_hits(self):
        assert _path_in_prefix_scope("/api/trade/order/NO123", "/api/trade/order")
        assert _path_in_prefix_scope("/api/trade/order/NO123/cancel", "/api/trade/order")

    def test_sibling_segment_not_hit(self):
        """核心回归：/api/trade/orders 不得命中 /api/trade/order 规则。"""
        assert not _path_in_prefix_scope("/api/trade/orders", "/api/trade/order")

    def test_sibling_prefix_not_hit(self):
        assert not _path_in_prefix_scope("/api/trade/orders/extra", "/api/trade/order")
        assert not _path_in_prefix_scope("/api/chatx", "/api/chat")


# ─────────────────────────────────────────────────────────────
# ② 规则解析：误伤收窄 + 既有阈值全保留
# ─────────────────────────────────────────────────────────────
class TestGetLimitForPath:
    def test_orders_list_uses_default_not_order_rule(self):
        """T6 核心：订单列表走 default(100/min)，不走 order 规则(10/min)。"""
        window, limit = _get_limit_for_path("/api/trade/orders")
        assert (window, limit) == _RATE_LIMIT_RULES["default"]

    def test_order_post_still_hits_order_rule(self):
        """下单端点行为不变：仍命中 order 规则。"""
        window, limit = _get_limit_for_path("/api/trade/order")
        assert window == 60
        assert limit == int(os.environ.get("EDUAGENT_TRADE_ORDER_LIMIT", "10"))

    def test_order_subpaths_still_hit_order_rule(self):
        """订单详情/取消子路径仍命中 order 规则。"""
        for p in ("/api/trade/order/NO123", "/api/trade/order/NO123/cancel"):
            window, limit = _get_limit_for_path(p)
            assert (window, limit) == _RATE_LIMIT_RULES["/api/trade/order"], p

    def test_nested_receive_longest_prefix_wins(self):
        """/api/trade/coupon/receive 最长前缀优先，不被更短交易前缀截胡。"""
        window, limit = _get_limit_for_path("/api/trade/coupon/receive")
        assert window == 60
        assert limit == 30

    def test_auth_rules_unchanged(self):
        assert _get_limit_for_path("/api/auth/login") == (60, 10)
        assert _get_limit_for_path("/api/auth/register") == (60, 5)
        assert _get_limit_for_path("/api/auth/refresh") == (60, 30)

    def test_chat_rule_unchanged(self):
        assert _get_limit_for_path("/api/chat")[0] == 60
        assert _get_limit_for_path("/api/chat/stream") == _get_limit_for_path("/api/chat")

    def test_admin_rule_unchanged(self):
        assert _get_limit_for_path("/api/admin/users") == (60, 200)

    def test_payment_rule_unchanged(self):
        assert _get_limit_for_path("/api/trade/payment/P123") == _RATE_LIMIT_RULES["/api/trade/payment"]

    def test_unknown_path_default(self):
        assert _get_limit_for_path("/api/curriculum/series") == _RATE_LIMIT_RULES["default"]

    def test_every_registered_prefix_resolves_to_itself(self):
        """既有规则全部保留：每条注册前缀都能解析回自身规则（防收窄误删）。"""
        for prefix, rule in _RATE_LIMIT_RULES.items():
            if prefix == "default":
                continue
            assert _get_limit_for_path(prefix) == rule, prefix


# ─────────────────────────────────────────────────────────────
# ③ 中间件级行为：orders 不被 order 规则击穿 + 429 带 CORS 头
# ─────────────────────────────────────────────────────────────
def _make_request(path: str, origin: str | None = None) -> Request:
    headers = [(b"authorization", b"Bearer x")] if False else []
    if origin:
        headers = [(b"origin", origin.encode())]
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers,
        "query_string": b"",
        "client": ("203.0.113.7", 12345),
        "scheme": "http",
        "server": ("127.0.0.1", 9988),
    }
    return Request(scope)


async def _call_next_ok(req):
    resp = MagicMock()
    resp.headers = {}
    return resp


class _CountingRedis:
    """按 key 计数的 fake Redis（incr/expire 最小实现）。"""

    def __init__(self, cap_for_path: int):
        self.counts: dict[str, int] = {}
        self.cap = cap_for_path

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, ttl: int) -> bool:
        return True


class TestMiddlewareMatching:
    @pytest.mark.asyncio
    async def test_orders_12x_not_429_under_order_rule(self):
        """T6 E2E 镜像：12 连发 GET /api/trade/orders 全放行（旧代码第 11 次起 429）。"""
        fake = _CountingRedis(cap_for_path=100)
        mw = RateLimitMiddleware(None)
        with patch("app.database.get_redis", return_value=fake):
            for _ in range(12):
                resp = await mw.dispatch(_make_request("/api/trade/orders"), _call_next_ok)
                assert getattr(resp, "status_code", 200) != 429

    @pytest.mark.asyncio
    async def test_order_still_429_after_10(self):
        """POST /api/trade/order 规则不变：第 11 次起仍 429（阈值未动）。"""
        fake = _CountingRedis(cap_for_path=10)
        mw = RateLimitMiddleware(None)
        codes = []
        with patch("app.database.get_redis", return_value=fake):
            for _ in range(12):
                resp = await mw.dispatch(_make_request("/api/trade/order"), _call_next_ok)
                codes.append(getattr(resp, "status_code", 200))
        assert codes[:10] == [200] * 10 or all(c != 429 for c in codes[:10])
        assert all(c == 429 for c in codes[10:])

    @pytest.mark.asyncio
    async def test_429_has_cors_headers_for_allowed_origin(self, monkeypatch):
        """T6 顺带修：429 短路响应带 access-control-allow-origin（allowlist 命中）。"""
        monkeypatch.setenv("CORS_ORIGINS", "http://127.0.0.1:3322,http://localhost:3322")
        from app.config import settings

        monkeypatch.setattr(settings, "CORS_ORIGINS", "http://127.0.0.1:3322,http://localhost:3322")
        monkeypatch.setattr(settings, "DEBUG", False)

        fake = _CountingRedis(cap_for_path=10)
        mw = RateLimitMiddleware(None)
        with patch("app.database.get_redis", return_value=fake):
            for _ in range(11):
                resp = await mw.dispatch(
                    _make_request("/api/trade/order", origin="http://127.0.0.1:3322"),
                    _call_next_ok,
                )
        from starlette.responses import JSONResponse as _JR

        assert isinstance(resp, _JR) and resp.status_code == 429
        assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:3322"
        assert resp.headers.get("access-control-allow-credentials") == "true"
        assert resp.headers.get("retry-after") == "60"

    @pytest.mark.asyncio
    async def test_429_no_cors_header_for_unknown_origin(self, monkeypatch):
        """非 allowlist Origin 不补 ACAO（不放宽 CORS 面）。"""
        from app.config import settings

        monkeypatch.setattr(settings, "CORS_ORIGINS", "http://127.0.0.1:3322")
        monkeypatch.setattr(settings, "DEBUG", False)

        fake = _CountingRedis(cap_for_path=10)
        mw = RateLimitMiddleware(None)
        with patch("app.database.get_redis", return_value=fake):
            for _ in range(11):
                resp = await mw.dispatch(
                    _make_request("/api/trade/order", origin="http://evil.example"),
                    _call_next_ok,
                )
        assert resp.status_code == 429
        assert "access-control-allow-origin" not in resp.headers

    @pytest.mark.asyncio
    async def test_200_response_still_has_ratelimit_headers(self):
        """放行响应 X-RateLimit-* 头注入行为不变。"""
        fake = _CountingRedis(cap_for_path=100)
        mw = RateLimitMiddleware(None)
        with patch("app.database.get_redis", return_value=fake):
            resp = await mw.dispatch(_make_request("/api/trade/orders"), _call_next_ok)
        assert resp.headers.get("X-RateLimit-Limit") == "100"
