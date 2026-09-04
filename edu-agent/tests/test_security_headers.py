# -*- coding: utf-8 -*-
"""测试安全响应头中间件（Phase 1 安全加固）。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.common.security_headers import SecurityHeadersMiddleware


class TestSecurityHeaders:
    """SecurityHeadersMiddleware 单元测试。"""

    @pytest.mark.asyncio
    async def test_csp_header_present(self):
        """CSP 头必须存在。"""
        middleware = SecurityHeadersMiddleware(MagicMock())

        async def mock_call_next(req):
            resp = MagicMock()
            resp.headers = {}
            return resp

        mock_request = MagicMock()
        mock_request.url.hostname = "localhost"
        response = await middleware.dispatch(mock_request, mock_call_next)
        assert "Content-Security-Policy" in response.headers
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]

    @pytest.mark.asyncio
    async def test_x_content_type_options(self):
        """X-Content-Type-Options 必须为 nosniff。"""
        middleware = SecurityHeadersMiddleware(MagicMock())

        async def mock_call_next(req):
            resp = MagicMock()
            resp.headers = {}
            return resp

        mock_request = MagicMock()
        mock_request.url.hostname = "localhost"
        response = await middleware.dispatch(mock_request, mock_call_next)
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options_deny(self):
        """X-Frame-Options 必须为 DENY（防点击劫持）。"""
        middleware = SecurityHeadersMiddleware(MagicMock())

        async def mock_call_next(req):
            resp = MagicMock()
            resp.headers = {}
            return resp

        mock_request = MagicMock()
        mock_request.url.hostname = "localhost"
        response = await middleware.dispatch(mock_request, mock_call_next)
        assert response.headers["X-Frame-Options"] == "DENY"

    @pytest.mark.asyncio
    async def test_x_xss_protection(self):
        """X-XSS-Protection 必须启用。"""
        middleware = SecurityHeadersMiddleware(MagicMock())

        async def mock_call_next(req):
            resp = MagicMock()
            resp.headers = {}
            return resp

        mock_request = MagicMock()
        mock_request.url.hostname = "localhost"
        response = await middleware.dispatch(mock_request, mock_call_next)
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    @pytest.mark.asyncio
    async def test_hsts_not_set_on_localhost(self):
        """本地开发不设置 HSTS（localhost 没有 HTTPS）。"""
        middleware = SecurityHeadersMiddleware(MagicMock())

        async def mock_call_next(req):
            resp = MagicMock()
            resp.headers = {}
            return resp

        mock_request = MagicMock()
        mock_request.url.hostname = "localhost"
        response = await middleware.dispatch(mock_request, mock_call_next)
        assert "Strict-Transport-Security" not in response.headers

    @pytest.mark.asyncio
    async def test_hsts_set_on_production_host(self):
        """生产域名应设置 HSTS。"""
        middleware = SecurityHeadersMiddleware(MagicMock())

        async def mock_call_next(req):
            resp = MagicMock()
            resp.headers = {}
            return resp

        mock_request = MagicMock()
        mock_request.url.hostname = "edu.example.com"
        response = await middleware.dispatch(mock_request, mock_call_next)
        assert "Strict-Transport-Security" in response.headers
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]

    @pytest.mark.asyncio
    async def test_referrer_policy(self):
        """Referrer-Policy 应设置为 strict-origin-when-cross-origin。"""
        middleware = SecurityHeadersMiddleware(MagicMock())

        async def mock_call_next(req):
            resp = MagicMock()
            resp.headers = {}
            return resp

        mock_request = MagicMock()
        mock_request.url.hostname = "localhost"
        response = await middleware.dispatch(mock_request, mock_call_next)
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_permissions_policy_restricts_sensitive_apis(self):
        """Permissions-Policy 应限制摄像头/麦克风等敏感 API。"""
        middleware = SecurityHeadersMiddleware(MagicMock())

        async def mock_call_next(req):
            resp = MagicMock()
            resp.headers = {}
            return resp

        mock_request = MagicMock()
        mock_request.url.hostname = "localhost"
        response = await middleware.dispatch(mock_request, mock_call_next)
        policy = response.headers["Permissions-Policy"]
        assert "camera=()" in policy
        assert "microphone=()" in policy
        assert "geolocation=()" in policy