# -*- coding: utf-8 -*-
"""测试请求限流逻辑（Phase 1 基础设施加固）。"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.common.rate_limit import (
    _get_client_ip,
    _get_limit_for_path,
    _get_rate_limit_key,
    _RATE_LIMIT_RULES,
    _RATE_LIMIT_SKIP_PREFIXES,
)


class TestRateLimitRules:
    """限流规则配置测试。"""

    def test_auth_login_rate_limit(self):
        """登录接口限流：60秒窗口最多10次。"""
        window, limit = _get_limit_for_path("/api/auth/login")
        assert window == 60
        assert limit == 10

    def test_auth_register_rate_limit(self):
        """注册接口限流：60秒窗口最多5次（防批量注册）。"""
        window, limit = _get_limit_for_path("/api/auth/register")
        assert window == 60
        assert limit == 5

    def test_chat_rate_limit(self):
        """AI问答限流：60秒窗口最多20次（LLM调用贵）。"""
        window, limit = _get_limit_for_path("/api/chat/answer")
        assert window == 60
        assert limit == 20

    def test_admin_rate_limit(self):
        """管理端限流：60秒窗口最多200次（内部使用）。"""
        window, limit = _get_limit_for_path("/api/admin/users")
        assert window == 60
        assert limit == 200

    def test_default_rate_limit(self):
        """通用API默认限流：60秒窗口最多100次。"""
        window, limit = _get_limit_for_path("/api/curriculum/series")
        assert window == 60
        assert limit == 100

    def test_skip_paths(self):
        """健康检查等路径应跳过限流。"""
        skip_paths = ["/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/favicon.ico"]
        for path in skip_paths:
            assert any(path.startswith(p) for p in _RATE_LIMIT_SKIP_PREFIXES)


class TestClientIP:
    """客户端 IP 获取测试。"""

    def test_x_forwarded_for(self):
        """X-Forwarded-For 头优先。"""
        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        assert _get_client_ip(mock_request) == "10.0.0.1"

    def test_x_real_ip(self):
        """X-Real-IP 头作为备选。"""
        mock_request = MagicMock()
        mock_request.headers = {"X-Real-IP": "10.0.0.2"}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        assert _get_client_ip(mock_request) == "10.0.0.2"

    def test_direct_client_ip(self):
        """无代理头时取直接 IP。"""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.100"
        assert _get_client_ip(mock_request) == "192.168.1.100"

    def test_forwarded_for_takes_priority(self):
        """X-Forwarded-For 优先级高于 X-Real-IP。"""
        mock_request = MagicMock()
        mock_request.headers = {
            "X-Forwarded-For": "10.0.0.1",
            "X-Real-IP": "10.0.0.2",
        }
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        assert _get_client_ip(mock_request) == "10.0.0.1"


class TestRateLimitKey:
    """限流 Redis key 生成测试。"""

    def test_key_format(self):
        """key 格式应为 rate_limit:{ip}:{path}:{window_start}。"""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"
        mock_request.url.path = "/api/chat/answer"

        key = _get_rate_limit_key(mock_request)
        assert key.startswith("rate_limit:192.168.1.1:/api/chat/answer:")
        # 最后一段是窗口起始时间戳（整数）
        ts = key.rsplit(":", 1)[-1]
        try:
            int(ts)
        except ValueError:
            pytest.fail(f"Key 最后一段不是时间戳: {key}")


class TestRateLimitMiddleware:
    """RateLimitMiddleware 单元测试（Mock Redis）。"""

    @pytest.fixture
    def mock_redis(self):
        """创建 Mock Redis。"""
        r = AsyncMock()
        r.incr = AsyncMock(return_value=1)  # 默认返回 1（未超限）
        r.expire = AsyncMock()
        return r

    @pytest.fixture
    def mock_request(self):
        """创建 Mock Request。"""
        req = MagicMock()
        req.url.path = "/api/curriculum/series"
        req.headers = {}
        req.client = MagicMock()
        req.client.host = "192.168.1.1"
        return req

    @pytest.mark.asyncio
    async def test_under_limit_passes(self, mock_redis, mock_request):
        """未超限时请求正常通过。"""
        mock_redis.incr.return_value = 50  # 50/100，未超限

        with patch("app.database.get_redis", return_value=mock_redis):
            from app.common.rate_limit import RateLimitMiddleware
            middleware = RateLimitMiddleware(MagicMock())

            async def mock_call_next(req):
                resp = MagicMock()
                resp.headers = {}
                return resp

            response = await middleware.dispatch(mock_request, mock_call_next)
            assert response.headers.get("X-RateLimit-Limit") is not None
            assert response.headers.get("X-RateLimit-Remaining") is not None

    @pytest.mark.asyncio
    async def test_over_limit_returns_429(self, mock_redis, mock_request):
        """超限时返回 429。"""
        mock_redis.incr.return_value = 101  # 超过 100 限制

        with patch("app.database.get_redis", return_value=mock_redis):
            from app.common.rate_limit import RateLimitMiddleware
            middleware = RateLimitMiddleware(MagicMock())

            async def mock_call_next(req):
                return MagicMock()

            response = await middleware.dispatch(mock_request, mock_call_next)
            assert response.status_code == 429
            assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_redis_unavailable_degrades(self, mock_request):
        """Redis 不可用时降级放行。"""
        with patch("app.database.get_redis", side_effect=RuntimeError("Redis not ready")):
            from app.common.rate_limit import RateLimitMiddleware
            middleware = RateLimitMiddleware(MagicMock())

            async def mock_call_next(req):
                resp = MagicMock()
                resp.headers = {}
                return resp

            response = await middleware.dispatch(mock_request, mock_call_next)
            # 应该正常返回（降级放行），不抛异常
            assert response is not None

    @pytest.mark.asyncio
    async def test_skip_path_not_rate_limited(self, mock_request):
        """健康检查路径跳过限流。"""
        mock_request.url.path = "/health"

        from app.common.rate_limit import RateLimitMiddleware
        middleware = RateLimitMiddleware(MagicMock())

        async def mock_call_next(req):
            resp = MagicMock()
            resp.headers = {}
            return resp

        response = await middleware.dispatch(mock_request, mock_call_next)
        # 跳过限流的请求不应有 X-RateLimit 头
        assert "X-RateLimit-Limit" not in response.headers