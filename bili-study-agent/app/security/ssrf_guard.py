# -*- coding: utf-8 -*-
"""W-NEXT-SSRF-001：URL/host 白名单 + SSRF 校验工具。

设计依据：
- Mimosa 强约束："① host 写死 127.0.0.1"（本仓库任意外部 URL 入参均需 host 白名单）
- 全量评估模块（knowledge_uploads / mcp_import_url / web_search / otel_webhook 等）前置门
- 与 task113 加固批一致：默认 deny，需白名单通过才放行
- 配置驱动：通过 settings.SSRF_ALLOWED_HOSTS / settings.SSRF_BLOCKED_HOSTS 覆盖默认值

SSRF 拒绝清单（即使 host 在白名单，命中以下也直接拒绝）：
- 169.254.0.0/16 —— AWS/GCP/Azure/阿里云元数据 endpoint（IMDS / metadata.google.internal）
- 127.0.0.0/8 之外的 localhost 等价但要求 127 字面（仅白名单精确匹配）
- 0.0.0.0 / 0.0.0.0/0 —— 通配（任何地址）
- :: / ::1 在 token-形 IPv6 任意通配

放行规则：
- scheme ∈ {http, https} + netloc host ∈ 白名单（即精确 host 字面，等于 settings 默认列表）
- 拒绝 file://、ftp://、gopher://、ldap:// 等非 http(s)
- 拒绝 userinfo@ 嵌入凭据（防御 SSRF 经典绕道）
"""
from __future__ import annotations

import ipaddress
from typing import Iterable
from urllib.parse import urlparse

# ============================================================
# 默认白名单（同步 settings 配置覆盖路径在 app.config.settings.SSRF_ALLOWED_HOSTS）
# 与 config.py 实证对齐：MILVUS/MONGO 在 192.168.85.101；本机项目服务在 127.0.0.1
# ============================================================
DEFAULT_ALLOWED_HOSTS: frozenset[str] = frozenset({
    "127.0.0.1",                # 本机回环（含本机 MySQL/Redis/MinIO/Rerank sidecar）
    "localhost",                # 等价 127（仅本地开发）
    "192.168.85.101",           # 项目内网：Milvus(19530)/Mongo(27017)
    "10.0.0.1",                 # 常见内网网关（部分场景 VPN 环境）
})

# 永远拒绝的 host（SSRF 杀招）：即使在白名单也必须二次拒绝
BLOCKED_HOSTS: frozenset[str] = frozenset({
    "0.0.0.0",
    "169.254.169.254",          # AWS / GCP / Azure / 阿里云元数据 endpoint（IMDS）
    "metadata.google.internal", # GCP 元数据域名
    "metadata",                 # 部分云默认短名
})

# 允许的 scheme
ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})


def _load_allowed_hosts_from_settings() -> frozenset[str]:
    """从 settings 读 SSRF_ALLOWED_HOSTS（runtime 覆盖默认白名单）；
    未配置则回退默认白名单。"""
    try:
        from app.config import settings

        custom = getattr(settings, "SSRF_ALLOWED_HOSTS", None)
        if isinstance(custom, (list, tuple, set)) and custom:
            return frozenset(str(x).strip().lower() for x in custom if str(x).strip()) | DEFAULT_ALLOWED_HOSTS
    except Exception:
        pass
    return DEFAULT_ALLOWED_HOSTS


def is_ip_in_blocked_range(host: str) -> bool:
    """检查 host 是否落在 SSRF 高危 IP 段（含 169.254.0.0/16、0.0.0.0/8、本地链路 IPv6 等）。
    对应攻击面：IMDS 元数据枚举、内网穿透、IPv6 通配。"""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.is_loopback and str(ip) != "127.0.0.1" and str(ip) != "127.1":
        # 127.x.x.x 其他回环域名通过 IP 解也会被允许（与白名单交集即满足）
        pass
    if ip.is_link_local:
        return True                # 169.254.0.0/16, 169.254.x.x 含 IMDS
    if ip.is_multicast:
        return True
    if ip.is_unspecified:
        return True                # 0.0.0.0
    if ip.is_private and not _is_in_allowed_internal(host):
        return True                # RFC1918 内网但不在白名单（防未授权内网穿透）
    return False


def _is_in_allowed_internal(host: str) -> bool:
    """白名单中字面的内网 IP 才允许；其余 RFC1918 段拒。"""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return str(ip) in DEFAULT_ALLOWED_HOSTS


class SSRFBlockedError(ValueError):
    """SSRF 校验失败——URL 不在允许列表 / 命中黑名单 / scheme 不合法。"""

    def __init__(self, reason: str, host: str = "", scheme: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.host = host
        self.scheme = scheme


def validate_url(url: str, *, allowed_hosts: Iterable[str] | None = None) -> None:
    """校验 URL 是否允许；不允许抛 SSRFBlockedError。

    通过条件：
      1) scheme ∈ ALLOWED_SCHEMES（仅 http/https）
      2) netloc 不含 userinfo（拒绝 username@host 防绕道）
      3) host ∈ 白名单（默认 + runtime 覆盖）
      4) host 不在 BLOCKED_HOSTS（IMDS 等），且 IP 不在内网穿透黑段
      5) port 在 1..65535（避免攻击者塞边界）

    注意：本函数 side-effect 零；调用方负责按需记录审计/拒绝。
    """
    if not isinstance(url, str) or not url:
        raise SSRFBlockedError("URL 为空", host="", scheme="")
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SSRFBlockedError(
            f"scheme 不在白名单（仅 http/https）：{scheme!r}",
            host=parsed.hostname or "", scheme=scheme,
        )
    if parsed.username or parsed.password:
        raise SSRFBlockedError(
            "URL 包含 userinfo（username:password@host），拒绝",
            host=parsed.hostname or "", scheme=scheme,
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise SSRFBlockedError("URL 缺少 host", host="", scheme=scheme)
    if host in BLOCKED_HOSTS:
        raise SSRFBlockedError(
            f"host 在 SSRF 永久封禁名单：{host!r}",
            host=host, scheme=scheme,
        )
    # IP 段校验：捕获 IMDS（169.254.x.x）/未指定（0.0.0.0）/RFC1918（仅白名单放行）
    if is_ip_in_blocked_range(host):
        # 即便是字面 IP，先看白名单（127.0.0.1 也在白名单）
        if host not in DEFAULT_ALLOWED_HOSTS and host not in _load_allowed_hosts_from_settings():
            raise SSRFBlockedError(
                f"host 落在 SSRF 高危段（IMDS/私网/通配）：{host!r}",
                host=host, scheme=scheme,
            )
    # 白名单校验
    allowed = set(_load_allowed_hosts_from_settings())
    if allowed_hosts:
        allowed |= {str(h).strip().lower() for h in allowed_hosts if h}
    # 域名（FQDN）与 IP 字面均需在白名单里（绝对白名单模型，不允许任何 host 后缀匹配）
    if host not in allowed:
        raise SSRFBlockedError(
            f"host 不在白名单：{host!r}（允许：{sorted(allowed)[:8]} 等）",
            host=host, scheme=scheme,
        )
    # port 边界（防御畸形端口注入）。urlparse 自身在 port 越界时抛 ValueError，
    # 这里先在 netloc 字面里独立判定，捕获 urlparse 的 ValueError 转 SSRFBlockedError。
    try:
        port = parsed.port
    except ValueError as exc:
        raise SSRFBlockedError(
            f"port 越界或不合法：{exc}",
            host=host, scheme=scheme,
        ) from exc
    if port is not None and not (1 <= port <= 65535):
        raise SSRFBlockedError(
            f"port 越界：{port}",
            host=host, scheme=scheme,
        )
