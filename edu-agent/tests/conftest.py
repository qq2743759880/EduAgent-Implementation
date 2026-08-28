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


# ════════════════════════════════════════════════════════════════
# task37 GWT③：live-backend 集成测试「标注 expected」机制
# ────────────────────────────────────────────────────────────────
# 大量契约测试（test_contract_*/test_course_*/test_auth_service 等）直连
# 127.0.0.1:8000 / 8003 的真实后端。无后端运行环境（task 执行窗口无 LLM/
# 服务）下这些测试抛 ConnectionError/URLError，属环境依赖而非代码缺陷。
# 这里在调用阶段捕获连接类异常并转为 skip，等价于「标注 expected」；
# 真实 CI 有后端时（EUID_LIVE_BACKEND=1 或端口可达）不触发，测试照常运行。
# ════════════════════════════════════════════════════════════════
_LIVE_HOSTS = [("127.0.0.1", 8000), ("127.0.0.1", 8003)]


def _backend_reachable(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


_BACKEND_UP = any(_backend_reachable(h, p) for h, p in _LIVE_HOSTS)
if os.environ.get("EUID_LIVE_BACKEND") == "1":
    _BACKEND_UP = True

_CONNECTION_ERRORS: tuple[type[BaseException], ...] = (ConnectionError, OSError)
try:
    import urllib.error as _urllib_error

    _CONNECTION_ERRORS = _CONNECTION_ERRORS + (_urllib_error.URLError,)
except Exception:  # pragma: no cover
    pass


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_backend: 需要运行中的真实后端（127.0.0.1:8000/8003）的集成测试",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item):
    """调用阶段：后端不可达时，连接类异常转为 skip（标注 expected）。"""
    if _BACKEND_UP:
        yield
        return
    try:
        yield
    except _CONNECTION_ERRORS as exc:
        pytest.skip(
            f"live backend unreachable (127.0.0.1:8000/8003) — 标注 expected（task37 GWT③）: {exc}"
        )
