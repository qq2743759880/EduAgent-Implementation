# -*- coding: utf-8 -*-
"""pytest 全局 fixture：隔离测试环境与开发/生产配置。

关键点：
- 测试用强随机 JWT_SECRET（避免依赖 .env 的弱密钥 dev-secret-key-...，也避免 InsecureKeyLengthWarning）
- API_TOKEN 同样固定
- autouse：每个测试自动生效，保证 service 里读 settings.JWT_SECRET 是测试密钥
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.config import settings

_TEST_JWT_SECRET = "test-jwt-secret-" + "a" * 48   # 64 字符强密钥
_TEST_API_TOKEN = "test-api-token-" + "b" * 24


@pytest.fixture(autouse=True)
def _isolate_secrets(monkeypatch: pytest.MonkeyPatch):
    """每个测试前：覆盖 settings 的 JWT_SECRET/API_TOKEN 为测试专用值。"""
    monkeypatch.setattr(settings, "JWT_SECRET", _TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "API_TOKEN", _TEST_API_TOKEN)
    # service.py 顶部把 ACCESS_TOKEN_EXPIRE_MINUTES 等烘焙成模块常量，
    # 若测试需要改有效期，直接 monkeypatch service 层；此处不动默认值。
    yield


@pytest.fixture(autouse=True)
def _isolate_redis_outage_window():
    """H1a：每个测试前后清零 Redis 故障快断窗（进程级全局状态，防止测试间串扰）。

    某些用例（限流中间件故障注入等）会 mark_redis_down；不隔离会波及后续
    走 redis_run 门/cache 的用例（门在窗内毫秒级快断，改变其注入路径）。
    """
    from app.core import redis_outage

    redis_outage.reset_for_test()
    yield
    redis_outage.reset_for_test()


# ════════════════════════════════════════════════════════════════
# task37 GWT③：live-backend 集成测试「标注 expected」机制
# ────────────────────────────────────────────────────────────────
# 大量契约测试（test_contract_*/test_course_*/test_auth_service 等）直连
# 127.0.0.1:8000 / 8003 的真实后端。无后端运行环境（task 执行窗口无 LLM/
# 服务）下这些测试抛 ConnectionError/URLError，属环境依赖而非代码缺陷。
# 这里在测试体「连接发起处」拦截对 live backend 主机的连接并转为 pytest.skip，等价于
# 「标注 expected」；真实 CI 有后端时（EUID_LIVE_BACKEND=1 或端口可达）不触发，测试照常运行。
# 实现说明：hookwrapper 无法把捕获的连接异常可靠地转为 skip（yield 返回 outcome 对象而非抛异常），
# 故改为在 autouse fixture 中 monkeypatch urllib/socket 的连接入口——skip 在测试自身栈帧抛出，
# pytest 即可正常记为 skipped（task37 GWT③ 全量复核）。
# ════════════════════════════════════════════════════════════════
_LIVE_HOSTS = [("127.0.0.1", 8000), ("127.0.0.1", 8001), ("127.0.0.1", 8003)]


def _backend_reachable(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


_BACKEND_UP = any(_backend_reachable(h, p) for h, p in _LIVE_HOSTS)
if os.environ.get("EUID_LIVE_BACKEND") == "1":
    _BACKEND_UP = True


def _is_live_target(host, port) -> bool:
    try:
        return (str(host), int(port)) in _LIVE_HOSTS
    except (TypeError, ValueError):
        return False


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_backend: 需要运行中的真实后端（127.0.0.1:8000/8003）的集成测试",
    )


@pytest.fixture(autouse=True)
def _live_backend_expected(monkeypatch: pytest.MonkeyPatch):
    """后端不可达时，把对 127.0.0.1:8000/8003 的连接发起直接转为 pytest.skip（标注 expected）。

    仅拦截明确指向 live backend 主机的连接（urllib.urlopen / socket.create_connection /
    socket.connect）；其它目标（文档 URL、MySQL/Milvus 等）按原逻辑走真实连接，
    其失败属环境预期但不在此拦截，避免误伤。
    """
    if _BACKEND_UP:
        yield
        return

    import urllib.request as _urllib

    def _hostport_from_target(target):
        try:
            if isinstance(target, str):
                from urllib.parse import urlparse

                p = urlparse(target)
                return p.hostname or "", p.port or (443 if p.scheme == "https" else 80)
            host = getattr(target, "host", None)
            if host is None:
                return "", None
            port = getattr(target, "port", None)
            if port is None:
                port = 443 if getattr(target, "type", "http") == "https" else 80
            return host, port
        except Exception:
            return "", None

    _orig_urlopen = _urllib.urlopen

    def _urlopen(*args, **kwargs):
        target = kwargs.get("url") or (args[0] if args else None)
        host, port = _hostport_from_target(target)
        if _is_live_target(host, port or 80):
            raise pytest.skip(
                f"live backend unreachable (127.0.0.1:{port}) — 标注 expected（task37 GWT③）"
            )
        return _orig_urlopen(*args, **kwargs)

    monkeypatch.setattr(_urllib, "urlopen", _urlopen)

    import socket as _socket

    _orig_create = _socket.create_connection

    def _create_connection(*args, **kwargs):
        addr = args[0] if args else kwargs.get("address")
        if isinstance(addr, (tuple, list)) and len(addr) >= 2:
            host, port = addr[0], addr[1]
            if _is_live_target(host, port or 80):
                raise pytest.skip(
                    f"live backend unreachable (127.0.0.1:{port}) — 标注 expected（task37 GWT③）"
                )
        return _orig_create(*args, **kwargs)

    monkeypatch.setattr(_socket, "create_connection", _create_connection)

    _orig_connect = _socket.socket.connect

    def _connect(self, address, *a, **k):
        if isinstance(address, (tuple, list)) and len(address) >= 2:
            host, port = address[0], address[1]
            if _is_live_target(host, port or 80):
                raise pytest.skip(
                    f"live backend unreachable (127.0.0.1:{port}) — 标注 expected（task37 GWT③）"
                )
        return _orig_connect(self, address, *a, **k)

    monkeypatch.setattr(_socket.socket, "connect", _connect)

    # http.client 层兜底：部分契约测试用自定义 OpenerDirector（_OPENER.open）而非 urlopen，
    # 连接最终走 http.client.HTTPConnection/HTTPSConnection.connect，需在此层拦截。
    import http.client as _http_client

    def _make_http_connect(orig):
        def _connect(self):
            port = self.port or (443 if getattr(self, "scheme", "http") == "https" else 80)
            if _is_live_target(self.host, port):
                raise pytest.skip(
                    f"live backend unreachable (127.0.0.1:{port}) — 标注 expected（task37 GWT③）"
                )
            return orig(self)

        return _connect

    monkeypatch.setattr(_http_client.HTTPConnection, "connect", _make_http_connect(_http_client.HTTPConnection.connect))
    if hasattr(_http_client, "HTTPSConnection"):
        monkeypatch.setattr(_http_client.HTTPSConnection, "connect", _make_http_connect(_http_client.HTTPSConnection.connect))

    yield
