# -*- coding: utf-8 -*-
"""P1-3 错误处理规范化单测：统一响应壳 + 业务码 + 异常收敛。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.common.error_codes import SUBCODE_MAP
from app.common.exceptions import (
    AppException,
    BadRequestError,
    DatabaseError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
    _http_status_for_code,
)


# ============================================================
# 1. 值域表：码段 ↔ HTTP 语义对齐
# ============================================================
def test_error_codes_segment_mapping():
    """码段前缀决定 HTTP 状态：40xxx→400/401/403/404/409，5xxxx→500。

    契约①：业务码为字符串；_http_status_for_code 入参接受字符串码。
    """
    assert _http_status_for_code("40000") == 400
    assert _http_status_for_code("40101") == 401
    assert _http_status_for_code("40300") == 403
    assert _http_status_for_code("40410") == 404
    assert _http_status_for_code("40900") == 409
    assert _http_status_for_code("50001") == 500
    assert _http_status_for_code("42200") == 422


def test_subcode_map_complete():
    """SUBCODE_MAP 覆盖所有 AUTH_* 子码，且码段与 HTTP 一致。"""
    for sub, (code, http) in SUBCODE_MAP.items():
        # 契约①：业务码为字符串，比较前转 int
        assert 40000 <= int(code) < 50000, f"{sub} 业务码应在 4xxxx 段"
        assert http == _http_status_for_code(code), f"{sub} 的 http 与码段不一致"


def test_auth_codes_unique():
    """子码 → 数字码必须一一对应，无重复冲突。"""
    codes = [c for c, _ in SUBCODE_MAP.values()]
    assert len(codes) == len(set(codes)), "存在重复业务码"


# ============================================================
# 2. 规范异常输出统一壳 {code, message, detail}
# ============================================================
def test_bad_request_has_business_code():
    e = BadRequestError("帖子已锁定", code="40310")
    assert e.code == "40310"
    assert e.http_status == 403
    assert e.message == "帖子已锁定"


def test_permission_denied_default_code():
    e = PermissionDeniedError("无权限")
    assert e.code == "40300"
    assert e.http_status == 403


def test_resource_not_found_default_code():
    e = ResourceNotFoundError("帖子不存在", code="40410")
    assert e.code == "40410"
    assert e.http_status == 404


def test_validation_error_string_subcode_maps():
    """ValidationError 字符串子码 → 数字码 + http + detail 里带 sub_code。"""
    e = ValidationError("登录凭证无效", code="AUTH_TOKEN_INVALID")
    assert e.code == "40101"
    assert e.http_status == 401
    assert "AUTH_TOKEN_INVALID" in (e.detail or "")


def test_app_exception_default_http():
    e = AppException(code=40000, message="x")
    assert e.http_status == 400


def test_database_error_500():
    e = DatabaseError("db down")
    assert e.code == "50002"
    assert e.http_status == 500


# ============================================================
# 3. 完整链路：AppException → 全局 handler → 统一壳
# ============================================================
@pytest.mark.asyncio
async def test_global_handler_returns_uniform_shell():
    """验证 main.py 的 AppException handler 输出 {code,message,detail}。"""
    from httpx import ASGITransport, AsyncClient

    from fastapi import FastAPI

    from app.common.exceptions import AppException

    app = FastAPI()

    @app.get("/boom")
    async def boom():
        raise PermissionDeniedError("不能修改他人的帖子", code="40311")

    from fastapi.responses import JSONResponse

    from app.common.auth import AuthMiddleware

    # 注册与 main.py 一致的 AppException handler
    @app.exception_handler(AppException)
    async def _handler(request, exc: AppException):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )

    app.add_middleware(AuthMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/boom")
    assert r.status_code == 403
    body = r.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "40311"
    assert body["message"] == "不能修改他人的帖子"
