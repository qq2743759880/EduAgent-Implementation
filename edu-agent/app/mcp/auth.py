# -*- coding: utf-8 -*-
"""task95 R3(3)：MCP 认证 —— API key + OAuth2 Authorization Code（含 refresh）。

修复 self-critique 维度 2 结构性缺陷：MCP 缺 OAuth 认证 / API key 注入。

对标 Claude Code mcp.md：MCP server 支持 OAuth 认证、API key、受管配置（allow/deny）。
  URL: https://docs.claude.com/en/docs/claude-code/mcp

设计约束：
  - 纯逻辑 / 数据结构，HTTP 发送可注入（post_fn），便于无网单测。
  - 认证失败降级：缺失凭据时不抛异常，仅不注入认证头（由 server 侧返回 401 处理）。
"""
from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlencode


@dataclass
class AuthConfig:
    """MCP server 认证配置。auth_type ∈ {none, api_key, oauth}。"""

    auth_type: str = "none"
    # api_key
    api_key: str = ""
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "  # 注入到 header value 的前缀（Bearer / Token / 空）
    # oauth（Authorization Code flow + refresh token）
    auth_url: str = ""
    token_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: list[str] = field(default_factory=list)
    redirect_uri: str = ""
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0  # epoch 秒；0 表示永不过期型
    extra_headers: dict[str, str] = field(default_factory=dict)


def build_auth_headers(cfg: AuthConfig) -> dict[str, str]:
    """根据配置生成注入到 MCP 请求的认证头（不抛异常，缺失则降级无认证）。"""
    headers: dict[str, str] = {}
    for k, v in (cfg.extra_headers or {}).items():
        headers[k] = v
    if cfg.auth_type == "api_key":
        if cfg.api_key:
            value = f"{cfg.api_key_prefix}{cfg.api_key}" if cfg.api_key_prefix else cfg.api_key
            headers[cfg.api_key_header] = value
    elif cfg.auth_type == "oauth":
        if cfg.access_token:
            # OAuth 默认 Authorization: Bearer <token>
            headers[cfg.api_key_header or "Authorization"] = f"Bearer {cfg.access_token}"
    return headers


def is_token_expired(cfg: AuthConfig, *, clock: Callable[[], float] = time.time,
                     leeway_s: float = 30.0) -> bool:
    """access_token 是否即将过期（默认留 30s 余量）。无 token 视为已过期。"""
    if not cfg.access_token:
        return True
    if cfg.expires_at <= 0:
        return False  # 永不过期型（部分 server）
    return clock() >= (cfg.expires_at - leeway_s)


class OAuthClient:
    """OAuth2 Authorization Code flow + refresh token 获取 access_token。

    HTTP 发送可注入（post_fn(url, data, headers) -> dict），便于无网单测。
    data 为 x-www-form-urlencoded 风格 dict；返回 JSON dict。
    """

    def __init__(self, cfg: AuthConfig, post_fn: Optional[Callable[[str, dict, dict], Any]] = None):
        self.cfg = cfg
        self._post = post_fn

    async def _post_json(self, url: str, data: dict, headers: dict) -> dict:
        if self._post is None:
            raise RuntimeError("OAuthClient 未配置 HTTP 发送器（post_fn）")
        res = self._post(url, data, headers)
        if inspect.isawaitable(res):
            res = await res
        if not isinstance(res, dict):
            raise RuntimeError(f"OAuth token 响应非 dict: {type(res)}")
        return res

    async def ensure_token(self) -> AuthConfig:
        """确保有效 access_token：未过期直接返回；否则用 refresh_token 刷新。

        无 refresh_token 则视为需走授权码流程（返回当前配置，由上层引导用户授权跳转）。
        """
        if not is_token_expired(self.cfg):
            return self.cfg
        if self.cfg.refresh_token:
            return await self.refresh()
        return self.cfg

    async def refresh(self) -> AuthConfig:
        if not self.cfg.refresh_token or not self.cfg.token_url:
            raise RuntimeError("缺少 refresh_token / token_url，无法刷新")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.cfg.refresh_token,
            "client_id": self.cfg.client_id,
            "client_secret": self.cfg.client_secret,
        }
        if self.cfg.scopes:
            data["scope"] = " ".join(self.cfg.scopes)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = await self._post_json(self.cfg.token_url, data, headers)
        self.cfg.access_token = str(resp.get("access_token", ""))
        if resp.get("refresh_token"):
            self.cfg.refresh_token = str(resp["refresh_token"])
        expires_in = float(resp.get("expires_in", 0) or 0)
        if expires_in:
            self.cfg.expires_at = time.time() + expires_in
        return self.cfg

    def authorization_url(self, *, state: str = "") -> str:
        """构造 Authorization Code 授权跳转 URL（基础版，PKCE 可选）。"""
        q = {
            "response_type": "code",
            "client_id": self.cfg.client_id,
            "redirect_uri": self.cfg.redirect_uri,
        }
        if self.cfg.scopes:
            q["scope"] = " ".join(self.cfg.scopes)
        if state:
            q["state"] = state
        sep = "&" if "?" in self.cfg.auth_url else "?"
        return f"{self.cfg.auth_url}{sep}{urlencode(q)}"
