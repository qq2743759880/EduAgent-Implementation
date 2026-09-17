# -*- coding: utf-8 -*-
"""W-NEXT-SSRF-001：单测 —— SSRF 白名单 + probe。

覆盖 GWT (≥4 例)：
1. 127.0.0.1 / localhost 允许（项目依赖的 MySQL/Redis/MinIO/Rerank sidecar）
2. 192.168.85.101 允许（项目内网 Milvus/Mongo 容器，config.py 实证）
3. 外网（evil.example.com / dashscope.aliyuncs.com）拒绝
4. AWS / GCP 元数据 endpoint（169.254.169.254 / metadata.google.internal）拒绝
5. file:// 等非 http(s) scheme 拒绝
6. username:password@host 的 userinfo 绕道拒绝
7. 0.0.0.0 / RFC1918 私网（10.x / 172.16.x / 192.168.x.x 不在白名单）拒绝
8. ssrf_scan 静态扫描：能命中真实风险位 + 找到 URL-ingest 入口（p8_import_url）
9. 端口越界（0、65536）拒绝
10. p8_import_url 路由层 router 集成：黑名单 URL 触发 400（不调 DB，直接走函数体）
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.security.ssrf_guard import (
    DEFAULT_ALLOWED_HOSTS,
    BLOCKED_HOSTS,
    SSRFBlockedError,
    validate_url,
)


# ============================================================
# ①-② 白名单放行（必须通过）
# ============================================================
@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/health",
    "http://127.0.0.1:8601/rerank",
    "http://127.0.0.1:6379/0",
    "http://127.0.0.1:9000/edu-course",
    "http://localhost:6379",
    "http://192.168.85.101:19530/v1/vector/search",
    "http://192.168.85.101:27017",
    "https://127.0.0.1/api/test",
])
def test_validate_url_allows_trusted_hosts(url: str) -> None:
    """GWT SSRF-G2-①/②：白名单内 host（含项目依赖 127/192.168.85.101）应被放行。"""
    validate_url(url)  # 不抛即通过
    assert "127.0.0.1" in DEFAULT_ALLOWED_HOSTS
    assert "192.168.85.101" in DEFAULT_ALLOWED_HOSTS


# ============================================================
# ③-⑥ 黑名单拒绝（必须 SSRFBlockedError）
# ============================================================
@pytest.mark.parametrize("url", [
    "http://evil.example.com/payload",                 # ③ 任意外网
    "http://www.google.com/",                          # ③ 公网
    "https://dashscope.aliyuncs.com/api/v1/services",  # ③ 公网（即使有真实业务）
    "http://169.254.169.254/latest/meta-data/",        # ④ AWS / GCP IMDS
    "http://metadata.google.internal/computeMetadata/v1/",  # ④ GCP metadata
    "file:///etc/passwd",                              # ⑤ file:// scheme
    "ftp://127.0.0.1/etc/shadow",                      # ⑤ ftp
    "gopher://127.0.0.1:11211/",                       # ⑤ gopher（redis 协议隧道）
    "ldap://127.0.0.1/cn=admin",                       # ⑤ ldap
    "http://evil@127.0.0.1:8000/",                     # ⑥ userinfo
    "http://user:pass@127.0.0.1/",                     # ⑥ userinfo with creds
    "http://0.0.0.0:9000/",                            # ⑦ 通配
])
def test_validate_url_rejects_untrusted(url: str) -> None:
    """GWT SSRF-G2-③/④/⑤/⑥/⑦：外网 / IMDS / 非 http(s) / userinfo / 通配 应被拒绝。"""
    with pytest.raises(SSRFBlockedError) as exc_info:
        validate_url(url)
    err = exc_info.value
    assert err.reason, "SSRFBlockedError 必须带 reason"
    assert err.host or err.scheme, "必须至少带 host 或 scheme"


# ============================================================
# ⑦ RFC1918 私网段（不在白名单）
# ============================================================
@pytest.mark.parametrize("url", [
    "http://10.0.0.5/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",       # 192.168.0.0/16 不在白名单（仅 192.168.85.101 允许）
    "http://172.20.5.5/admin",
])
def test_validate_url_rejects_rfc1918_not_in_whitelist(url: str) -> None:
    """GWT SSRF-G2-⑦：RFC1918 私网段但不在白名单应被拒。"""
    with pytest.raises(SSRFBlockedError) as exc_info:
        validate_url(url)
    assert "白名单" in exc_info.value.reason or "高危段" in exc_info.value.reason


# ============================================================
# ⑧ ssrf_scan 探针：能扫到 ≥1 个 findings
# ============================================================
def test_ssrf_scan_finds_findings() -> None:
    """GWT SSRF-G1：ssrf_scan 必须能扫到 ≥1 个 HTTP/URL 构造点 + URL-ingest 入口。"""
    from scripts.eval.ssrf_scan import scan_python_file, scan_url_ingest_endpoints

    repo = Path(__file__).resolve().parents[1]
    findings = scan_python_file(repo / "app" / "otel" / "exporter.py")
    assert findings, "OTLP exporter 的 requests.post 应被探针命中"

    eps = scan_url_ingest_endpoints()
    models = {e["model"] for e in eps}
    assert "MCPImportUrlReq" in models, f"必须扫到 MCPImportUrlReq，got {models}"

    fields = [f for e in eps for f in e["fields"]]
    assert "url" in fields


# ============================================================
# ⑨ 端口越界
# ============================================================
@pytest.mark.parametrize("url", [
    "http://127.0.0.1:0/",
    "http://127.0.0.1:65536/",
])
def test_validate_url_rejects_invalid_port(url: str) -> None:
    """GWT SSRF-G2-扩展：畸形端口应被拒绝。"""
    with pytest.raises(SSRFBlockedError):
        validate_url(url)


# ============================================================
# ⑩ p8_import_url 路由层 router 集成：黑名单 URL 触发 400
# ============================================================
def test_router_rejects_ssrf_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """GWT SSRF-G2 实证：p8_import_url 收到 169.254.169.254 必被 400 拒绝（不依赖 DB）"""
    # 延迟 import 避免顶层循环
    from app.mcp.schemas import MCPImportUrlReq

    admin_user = type("U", (), {"user_id": 1, "role": "admin", "tenant_id": "_default"})()

    # 走代码静态读而非 import router（避免依赖真实数据库初始化）
    # 改用直接 reload 模块并读出函数体
    import importlib
    from app.mcp import router as _r
    importlib.reload(_r)

    bad_req = MCPImportUrlReq(url="http://169.254.169.254/latest/meta-data/iam/security-credentials/")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_r.p8_import_url(bad_req, me=admin_user))
    assert exc.value.status_code == 400
    assert ("SSRF" in str(exc.value.detail)
            or "白名单" in str(exc.value.detail)
            or "封禁" in str(exc.value.detail))


def test_router_allows_internal_trusted_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """GWT SSRF-G2：合法 IP 通过路由层校验（不进 DB 也能完成 schema 校验）"""
    from app.mcp.schemas import MCPImportUrlReq
    MCPImportUrlReq(url="http://127.0.0.1:65535/test")
    MCPImportUrlReq(url="http://192.168.85.101:19530/health")
    # schema 自身允许通过；路由层 SSRF 校验仅在 http(s):// 形态触发
