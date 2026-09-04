# -*- coding: utf-8 -*-
"""P1-1 可观测性单测：trace_id 全链路 + 生产 JSON 日志格式 + 访问日志字段。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.common.auth import AuthMiddleware, _is_public_path, get_trace_id, trace_id_var
from app.common.logging import _json_sink


# ============================================================
# 1. 公开路径判定
# ============================================================
def test_public_path_exact():
    assert _is_public_path("/health") is True
    assert _is_public_path("/health/detail") is True
    assert _is_public_path("/") is True
    assert _is_public_path("/docs") is True


def test_public_path_prefix():
    assert _is_public_path("/api/auth/login") is True
    assert _is_public_path("/api/auth/register") is True
    assert _is_public_path("/api/auth/refresh") is True


def test_non_public_path():
    assert _is_public_path("/api/chat/stream") is False
    assert _is_public_path("/api/admin/users") is False
    assert _is_public_path("/api/curriculum/series") is False


# ============================================================
# 2. trace_id contextvar
# ============================================================
def test_trace_id_var_default_empty():
    # 未设置时返回空（避免跨测试污染）
    trace_id_var.set("")
    assert get_trace_id() == ""


def test_trace_id_set_and_get():
    trace_id_var.set("test-tid-1")
    assert get_trace_id() == "test-tid-1"
    trace_id_var.set("")  # 清理


# ============================================================
# 3. 生产 JSON 日志格式（_json_sink 输出到 stdout 捕获）
# ============================================================
def test_json_sink_outputs_valid_json(monkeypatch, capsys):
    """_json_sink 输出单行合法 JSON，含 extra 字段。"""
    import datetime

    loguru_level = type("L", (), {"name": "INFO"})()

    class _Rec:
        def __init__(self):
            self.record = {
                "time": datetime.datetime(2026, 1, 1, 12, 0, 0, 123456),
                "level": loguru_level,
                "name": "test_mod",
                "function": "test_func",
                "line": 42,
                "message": "访问日志",
                "extra": {"trace_id": "tid-xyz", "status": 200, "duration_ms": 15.3},
                "exception": None,
            }

    _json_sink(_Rec())
    out = capsys.readouterr().out
    parsed = json.loads(out.strip())
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_mod:test_func:42"
    assert parsed["message"] == "访问日志"
    assert parsed["trace_id"] == "tid-xyz"
    assert parsed["status"] == 200
    assert parsed["duration_ms"] == 15.3


# ============================================================
# 4. AuthMiddleware 完整链路（ASGI 测试）
# ============================================================
@pytest.mark.asyncio
async def test_middleware_sets_trace_id_and_access_log(monkeypatch, capsys):
    """中间件：生成 trace_id、写响应头、记录结构化访问日志。"""

    from fastapi import FastAPI

    # 用真实 middleware 包装一个最小 app
    app = FastAPI()

    @app.get("/api/test-route")
    async def route():
        # 路由内应能取到 trace_id（contextvar 贯穿）
        assert get_trace_id() != ""
        return {"ok": True}

    app.add_middleware(AuthMiddleware)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/test-route")
    assert resp.status_code == 200
    # 响应头带 trace_id
    assert resp.headers.get("X-Trace-Id")
    # trace_id 是 8 字符短 UUID
    assert len(resp.headers["X-Trace-Id"]) == 8
