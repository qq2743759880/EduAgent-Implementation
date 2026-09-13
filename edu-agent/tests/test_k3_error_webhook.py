# -*- coding: utf-8 -*-
"""C5-K3：500 错误上报通道（ERROR_WEBHOOK_URL）契约测试（离线 + 本地 HTTP 捕获服务）。

用例矩阵：
  ① 非 DEBUG + 已设置 URL：global_exception_handler 触发后本地 webhook 收到精简载荷
     {trace_id, time, exception_type, stack≤2000}；错误响应契约零变更（50000 脱敏形状）
  ② 未设置 URL（默认空）→ 不发
  ③ DEBUG=True（本仓 dev .env 默认形态）→ 不发
  ④ 依赖型异常（50301）同样上报且响应形状不变（契约回归点）

守则对齐：禁 DB 直写；禁 Playwright；外呼目标是本进程内临时 HTTP 捕获服务。
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from starlette.requests import Request

import app.main as app_main
from app.core.db_resilience import DependencyUnavailableError
from app.config import settings


# ── 本地 HTTP 捕获服务（进程内，无外部依赖） ──
class _CaptureServer:
    def __init__(self):
        self.received: list[dict] = []
        self._event = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                outer.received.append(json.loads(body.decode("utf-8")))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):  # 静默
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def _make_request(trace_id: str = "t-k3-001") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/boom",
        "raw_path": b"/boom",
        "query_string": b"",
        "root_path": "",
        "server": ("127.0.0.1", 8000),
        "headers": [(b"x-trace-id", trace_id.encode())],
        "state": {"trace_id": trace_id},
    }
    return Request(scope)


async def _invoke(exc: Exception):
    """调用全局兜底处理器并 drain 在飞上报任务，返回响应。"""
    resp = await app_main.global_exception_handler(_make_request(), exc)
    if app_main._ERROR_WEBHOOK_TASKS:
        await asyncio.gather(*list(app_main._ERROR_WEBHOOK_TASKS))
    return resp


def test_webhook_receives_payload_and_contract_unchanged(monkeypatch):
    """① 非 DEBUG + 设置 URL → 收到载荷；响应 {code:50000,message,data:null} 零变更。"""
    with _CaptureServer() as srv:
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "ERROR_WEBHOOK_URL", srv.url)
        try:
            raise RuntimeError("boom-secret-detail")
        except RuntimeError as exc:
            resp = asyncio.run(_invoke(exc))
        body = json.loads(resp.body.decode("utf-8"))
        # 响应契约零变更：脱敏形状不变，不含异常细节
        assert resp.status_code == 500
        assert body == {"code": "50000", "message": "服务内部错误，请稍后重试", "data": None}
        assert "boom-secret-detail" not in resp.body.decode("utf-8")
        # webhook 收到精简载荷
        assert len(srv.received) == 1
        payload = srv.received[0]
        assert set(payload.keys()) == {"trace_id", "time", "exception_type", "stack"}
        assert payload["trace_id"] == "t-k3-001"
        assert payload["exception_type"] == "RuntimeError"
        assert payload["stack"].startswith("Traceback")
        assert len(payload["stack"]) <= 2000
        assert payload["time"]


def test_no_webhook_when_url_unset(monkeypatch):
    """② 未设置 URL（默认空）→ 不发。"""
    with _CaptureServer() as srv:
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "ERROR_WEBHOOK_URL", "")
        asyncio.run(_invoke(RuntimeError("x")))
        assert srv.received == []


def test_no_webhook_in_debug(monkeypatch):
    """③ DEBUG=True → 不发（本地开发零外呼）。"""
    with _CaptureServer() as srv:
        monkeypatch.setattr(settings, "DEBUG", True)
        monkeypatch.setattr(settings, "ERROR_WEBHOOK_URL", srv.url)
        asyncio.run(_invoke(RuntimeError("x")))
        assert srv.received == []


def test_dependency_exception_reported_and_50301_shape_unchanged(monkeypatch):
    """④ 依赖型异常 → 50301 响应形状不变，且同样旁路上报（500 级兜底）。"""
    with _CaptureServer() as srv:
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "ERROR_WEBHOOK_URL", srv.url)
        resp = asyncio.run(_invoke(DependencyUnavailableError("milvus down")))
        body = json.loads(resp.body.decode("utf-8"))
        assert body["code"] == "50301"
        assert body["data"] is None
        assert len(srv.received) == 1
        assert srv.received[0]["exception_type"] == "DependencyUnavailableError"
