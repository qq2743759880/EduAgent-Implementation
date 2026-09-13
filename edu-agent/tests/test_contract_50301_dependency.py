# -*- coding: utf-8 -*-
"""T19-3（contracts/reshape-b.json amendments，2026-09-12 用户签字）：
50301 DEPENDENCY_UNAVAILABLE + 错误响应脱敏 契约测试（离线 TestClient + monkeypatch，不触 DB/真 Milvus）。

用例矩阵：
  ① 依赖不可达端点（GET /api/knowledge/partitions，Milvus 超时 / 连接失败）
     → code=50301 + message 面向用户（无文件路径/类名/host/内部细节）+ HTTP 503/500 语义不变
  ② 原始异常完整进 logger（含堆栈）——loguru 等价 caplog：
     本项目日志为 loguru 单例（不经 stdlib logging），pytest caplog 无法捕获，
     故用 loguru sink 捕获断言（等价语义：原始异常文本+堆栈必须落日志、不落响应）。
  ③ 普通业务错误不受影响：404 → 40400；全局兜底非依赖异常 → 50000；
     DEBUG=True 下全局兜底 data 恒为 null（不再回传 str(exc)，脱敏核心回归点）。
  ④ 依赖分类器 _is_dependency_exception 单元用例：MCP stdio spawn RuntimeError 签名 → 依赖类；
     普通逻辑异常（ValueError/RuntimeError 非依赖文案）→ 非依赖类（保守不误判）。

守则对齐：禁 DB 直写（全程无任何 DB 写操作）；禁 Playwright；异常全部 monkeypatch 注入。
回滚承诺：本文件随 T19-3 单 commit 落地，revert 即回滚。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from loguru import logger as loguru_logger

from app.auth import dependencies as auth_deps
from app.auth import service as auth_service
from app.auth.dependencies import get_current_user
from app.auth.schemas import UserInfo, UserRole
from app.common.error_codes import DEPENDENCY_UNAVAILABLE, SERVICE_UNAVAILABLE
from app.common.exceptions import DependencyUnavailableError
from app.config import settings
from app.knowledge.routers import upload as knowledge_upload
from app.main import _is_dependency_exception, app

# 带"内部细节毒物"的异常文案：类名 + 包名 + Windows 文件路径 + host:port
_POISON = (
    "pymilvus.exceptions.MilvusException: <_MultiThreadedRendezvous RPC terminated> "
    "connect 192.168.85.101:19530 failed, "
    r'File "C:\Users\Administrator\edu-agent\.venv\Lib\site-packages\pymilvus\grpc_handler.py"'
)


# ══════════════════════════════════════════════════════════════
# fixtures
# ══════════════════════════════════════════════════════════════
@pytest.fixture()
def admin_headers(monkeypatch):
    """离线管理端认证：真 JWT（conftest 测试密钥）+ 内存用户桩（不触 DB）。

    AdminAuthMiddleware 对 /api/knowledge/partitions 强制真实 Bearer 并剥离
    X-Force-Role（judge R1 fail-closed 设计），故走真 token + monkeypatch 用户查询。
    """
    token, _ = auth_service.create_access_token(user_id=1, role=UserRole.ADMIN)
    real_name = "T19-3 契约测试管理员"

    async def _fake_get_user(user_id: int) -> UserInfo:
        return UserInfo(user_id=1, nickname="T19-3", real_name=real_name,
                        mobile=None, email=None, gender=None, avatar_url=None,
                        role=UserRole.ADMIN)

    monkeypatch.setattr(auth_service, "get_user_info_by_id", _fake_get_user)
    # dependencies.py 顶层绑定了同名函数对象，路由依赖用的是自己的命名空间
    monkeypatch.setattr(auth_deps, "get_user_info_by_id", _fake_get_user)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(monkeypatch):
    """DEBUG=True 的离线 TestClient：验证「即使 DEBUG，响应也不回传原始异常」。

    raise_server_exceptions=False：全局兜底 handler（@app.exception_handler(Exception)）
    由 ServerErrorMiddleware 调用生成 500 响应；默认 True 会把原始异常重抛给测试端
    （ExceptionGroup），断言不到响应壳——这里要验证的恰是「handler 生成的响应体」。
    """
    monkeypatch.setattr(settings, "DEBUG", True)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def loguru_capture():
    """loguru sink 捕获器（等价 caplog：本项目 logger=loguru 单例，不经 stdlib logging）。"""
    records: list = []

    def _sink(message):
        rec = message.record
        exc = rec.get("exception")
        records.append({
            "text": str(rec["message"]) + (f" || {exc}" if exc else ""),
            "level": rec["level"].name,
            "has_exception": exc is not None,
        })

    hook_id = loguru_logger.add(_sink, level="ERROR")
    try:
        yield records
    finally:
        loguru_logger.remove(hook_id)


# ══════════════════════════════════════════════════════════════
# ① 依赖不可达端点 → 50301 + message 用户化 + HTTP 语义不变
# ══════════════════════════════════════════════════════════════
class TestDependencyEndpointContract:
    def test_partitions_timeout_returns_50301_http503(self, client, monkeypatch, admin_headers, loguru_capture):
        """①a Milvus 查询分区超时：code=50301、message 用户化、HTTP 503 维持。"""
        def _unreachable():
            raise asyncio.TimeoutError()  # py3.11：asyncio.TimeoutError 即 TimeoutError

        monkeypatch.setattr(knowledge_upload, "list_all_partitions", _unreachable)
        resp = client.get("/api/knowledge/partitions", headers=admin_headers)

        assert resp.status_code == 503, f"HTTP 503 语义必须维持：{resp.status_code}"
        body = resp.json()
        assert body["code"] == DEPENDENCY_UNAVAILABLE == "50301"
        assert body["message"] == "依赖服务暂不可用，请稍后重试"
        assert body["data"] is None

    def test_partitions_conn_error_sanitized_http500(self, client, monkeypatch, admin_headers, loguru_capture):
        """①b Milvus 连接失败（原 f\"查询失败: {e}\" 直泄 str(e)）：code=50301，
        message 不含类名/包名/文件路径/host，HTTP 500 维持，data 恒 null（DEBUG 亦然）。"""
        def _unreachable():
            raise ConnectionError(_POISON)

        monkeypatch.setattr(knowledge_upload, "list_all_partitions", _unreachable)
        resp = client.get("/api/knowledge/partitions", headers=admin_headers)

        assert resp.status_code == 500, "HTTP 500 语义必须维持"
        body = resp.json()
        assert body["code"] == "50301"
        assert body["message"] == "依赖服务暂不可用，请稍后重试"
        assert body["data"] is None
        raw = resp.text
        assert "MilvusException" not in raw, f"类名泄漏：{raw[:300]}"
        assert "pymilvus" not in raw
        assert "192.168.85.101" not in raw
        assert "grpc_handler.py" not in raw
        assert "\\\\" not in raw and "Users" not in raw

    def test_delete_partition_conn_error_sanitized(self, client, monkeypatch, admin_headers):
        """①c 删除分区连接失败（原 f\"删除失败: {e}\" 直泄）：code=50301 + HTTP 500 维持。"""
        def _unreachable(tenant_id: str):
            raise ConnectionError(_POISON)

        monkeypatch.setattr(knowledge_upload, "drop_partition", _unreachable)
        resp = client.delete("/api/knowledge/partitions/some_tenant", headers=admin_headers)
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "50301"
        assert body["message"] == "依赖服务暂不可用，请稍后重试"
        assert body["data"] is None
        assert "MilvusException" not in resp.text

    def test_delete_partition_404_kept(self, client, monkeypatch, admin_headers):
        """①d drop_partition 返回 False 的 404 分支不受 50301 改造影响。"""
        monkeypatch.setattr(knowledge_upload, "drop_partition", lambda t: False)
        resp = client.delete("/api/knowledge/partitions/some_tenant", headers=admin_headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == "40400"


# ══════════════════════════════════════════════════════════════
# ② 原始异常进 logger（loguru 等价 caplog）
# ══════════════════════════════════════════════════════════════
class TestOriginalExceptionLogged:
    def test_original_exception_in_logger_with_stack(self, client, monkeypatch, admin_headers, loguru_capture):
        """② 依赖异常的原始细节（类名/host/路径）必须完整进日志（含堆栈），
        与「不进响应」形成对照（用例 ①b）。"""
        def _unreachable():
            raise ConnectionError(_POISON)

        monkeypatch.setattr(knowledge_upload, "list_all_partitions", _unreachable)
        client.get("/api/knowledge/partitions", headers=admin_headers)

        joined = "\n".join(r["text"] for r in loguru_capture)
        assert "MilvusException" in joined, "原始异常（类名/host/路径）必须进日志"
        assert "192.168.85.101" in joined
        assert "grpc_handler.py" in joined
        # 含堆栈：loguru record 的 exception 字段非空（logger.exception 语义）
        assert any(r["has_exception"] and r["level"] == "ERROR" for r in loguru_capture), \
            "必须以 ERROR 级别含异常堆栈入日志"

    def test_global_handler_logs_unhandled(self, client, monkeypatch, loguru_capture):
        """②b 全局兜底同样把原始异常（含堆栈）写入日志。"""
        def _boom():
            raise ValueError("内部秘密报错 C:\\secret\\path.py")

        monkeypatch.setitem(app.dependency_overrides, get_current_user, _boom)
        try:
            resp = client.get("/api/auth/me")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 500
        joined = "\n".join(r["text"] for r in loguru_capture)
        assert "内部秘密报错" in joined and "C:\\secret\\path.py" in joined
        assert any(r["has_exception"] for r in loguru_capture)


# ══════════════════════════════════════════════════════════════
# ③ 普通业务错误不受影响 + DEBUG 下全局兜底 data 恒 null
# ══════════════════════════════════════════════════════════════
class TestNormalBusinessErrorsUnaffected:
    def test_not_found_still_40400(self, client):
        """③a 普通业务错误（40400）不受脱敏改造影响。"""
        resp = client.get("/api/__definitely_not_a_route__")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "40400"
        assert body["data"] is None

    def test_global_handler_non_dependency_50000_no_leak_in_debug(self, client, monkeypatch):
        """③b DEBUG=True 下全局兜底：非依赖异常 → 50000 + message 用户化 + data 恒 null
        （原实现 DEBUG 会把 str(exc) 塞进 data——脱敏核心回归点）。"""
        def _boom():
            raise ValueError("内部秘密报错 C:\\secret\\path.py")

        monkeypatch.setitem(app.dependency_overrides, get_current_user, _boom)
        try:
            resp = client.get("/api/auth/me")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "50000"
        assert body["message"] == "服务内部错误，请稍后重试"
        assert body["data"] is None, "DEBUG 下 data 也必须恒为 null"
        assert "内部秘密报错" not in resp.text
        assert "secret" not in resp.text

    def test_status_to_code_mapping_unchanged(self):
        """③c 纯增量原则：STATUS_TO_CODE 503→50300 通用映射保持不变（50301 只在依赖点显式接线）。"""
        from app.common.error_codes import STATUS_TO_CODE
        assert STATUS_TO_CODE[503] == SERVICE_UNAVAILABLE == "50300"
        assert STATUS_TO_CODE[500] == "50000"


# ══════════════════════════════════════════════════════════════
# ④ 依赖分类器单元用例（MCP spawn 同类接线的判定核心）
# ══════════════════════════════════════════════════════════════
class TestDependencyClassifier:
    def test_mcp_spawn_runtime_error_is_dependency(self):
        """④a MCP stdio spawn 失败签名（app/mcp/executor.py 固定 raise 文案）→ 依赖类。"""
        assert _is_dependency_exception(
            RuntimeError("create_subprocess_exec 失败：SelectorEventLoop；cmd=['python'] cwd=..."))
        assert _is_dependency_exception(RuntimeError("stdio 未收到任何响应帧：clue"))
        assert _is_dependency_exception(RuntimeError("stdio: JSON decode fail: x"))

    def test_builtin_conn_timeout_are_dependency(self):
        """④b 内建连接/超时族 → 依赖类（py3.11 asyncio.TimeoutError=TimeoutError）。"""
        assert _is_dependency_exception(ConnectionError("x"))
        assert _is_dependency_exception(ConnectionRefusedError("x"))
        assert _is_dependency_exception(asyncio.TimeoutError())

    def test_driver_exceptions_are_dependency(self):
        """④c 第三方驱动层（按模块根/类名，不硬 import）→ 依赖类。"""
        MilvusException = type("MilvusException", (Exception,),
                               {"__module__": "pymilvus.exceptions"})
        ServerSel = type("ServerSelectionTimeoutError", (Exception,),
                         {"__module__": "pymongo.errors"})
        RedisConn = type("ConnectionError", (Exception,), {"__module__": "redis.exceptions"})
        assert _is_dependency_exception(MilvusException("connect failed"))
        assert _is_dependency_exception(ServerSel("timeout"))
        assert _is_dependency_exception(RedisConn("x"))

    def test_db_resilience_signal_is_dependency(self):
        """④d 熔断依赖信号（app.core.db_resilience.DependencyUnavailableError）→ 依赖类。"""
        from app.core.db_resilience import DependencyUnavailableError as _Dep
        assert _is_dependency_exception(_Dep("circuit open"))

    def test_logic_errors_not_misclassified(self):
        """④e 保守不误判：普通逻辑异常仍走 50000。"""
        assert not _is_dependency_exception(ValueError("bad input"))
        assert not _is_dependency_exception(RuntimeError("某业务逻辑 bug"))
        assert not _is_dependency_exception(KeyError("k"))
        assert not _is_dependency_exception(TypeError("x"))


# ══════════════════════════════════════════════════════════════
# 契约异常类本身
# ══════════════════════════════════════════════════════════════
class TestDependencyUnavailableErrorClass:
    def test_default_shape(self):
        """50301 异常类：默认 message 用户化、detail 恒 None（data 恒 null 的根）、HTTP 可指定。"""
        e503 = DependencyUnavailableError()
        assert e503.code == "50301"
        assert e503.message == "依赖服务暂不可用，请稍后重试"
        assert e503.detail is None
        assert e503.http_status == 503

        e500 = DependencyUnavailableError(http_status=500)
        assert e500.http_status == 500 and e500.code == "50301"
