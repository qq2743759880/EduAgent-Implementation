# -*- coding: utf-8 -*-
"""H1b（P1-8 热修）：DEBUG 虚拟管理员启动硬门禁 测试。

背景：DEBUG=true 时无 Authorization 头的请求会被注入虚拟管理员 user_id=1
（app/auth/dependencies.py 规则②），生产误开 DEBUG = 匿名可读用户数据。
原状仅告警（_security_guard），本批升级为 fail-fast 拒绝启动：

- DEBUG=true + ENV_NAME 显式非 local（prod/production/staging/dev/qa…）→ 拒绝启动
- DEBUG=true + ENV_NAME=local（默认）→ 放行（本机开发体验不变）
- DEBUG=false + ENV_NAME=prod → 放行（生产不受影响）

构造 Settings 时统一 _env_file=None（不读真实 .env，全量显式传参，确定性）；
prod 用例须带强 JWT_SECRET/API_TOKEN 以越过既有 _security_guard（本用例聚焦
_debug_env_gate，避免混入密钥护栏的报错）。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

_STRONG_JWT = "h1b-test-jwt-secret-" + "c" * 48
_STRONG_TOKEN = "h1b-test-api-token-" + "d" * 24
# Settings 的两个无默认值必填字段（_env_file=None 不读 .env 时必须显式给值）
_REQUIRED = {"MYSQL_PASSWORD": "x", "LLM_API_KEY": "x"}


def _settings(**kw) -> dict:
    """构造入参：必填字段 + 用例覆盖。"""
    base = dict(_REQUIRED)
    base.update(kw)
    return base


def test_debug_true_prod_rejected():
    """GWT①：DEBUG=true + ENV_NAME=prod → 抛 ValidationError 拒绝启动。"""
    with pytest.raises(ValidationError) as ei:
        Settings(
            **_settings(
                DEBUG=True,
                ENV_NAME="prod",
                JWT_SECRET=_STRONG_JWT,
                API_TOKEN=_STRONG_TOKEN,
            ),
            _env_file=None,
        )
    msg = str(ei.value)
    assert "ENV_NAME" in msg and "启动拒绝" in msg, f"门禁信息缺失: {msg}"


def test_debug_true_local_allowed():
    """GWT②：DEBUG=true + ENV_NAME=local（默认）→ 正常构造（本机开发放行）。"""
    s = Settings(
        **_settings(
            DEBUG=True,
            ENV_NAME="local",
            JWT_SECRET=_STRONG_JWT,
            API_TOKEN=_STRONG_TOKEN,
        ),
        _env_file=None,
    )
    assert s.DEBUG is True and s.ENV_NAME == "local"


def test_debug_false_prod_allowed():
    """GWT③：DEBUG=false + ENV_NAME=prod → 正常构造（生产启动不受影响）。"""
    s = Settings(
        **_settings(
            DEBUG=False,
            ENV_NAME="prod",
            JWT_SECRET=_STRONG_JWT,
            API_TOKEN=_STRONG_TOKEN,
        ),
        _env_file=None,
    )
    assert s.DEBUG is False and s.ENV_NAME == "prod"


def test_debug_true_default_env_name_allowed():
    """补充：ENV_NAME 缺省（=local）+ DEBUG=true → 放行。

    等价于「Windows 本机现有 .env(DEBUG=true，无 ENV_NAME) 必须照常能启动」——
    即真实 settings 单例的加载路径（conftest import app.config 时已验证一次）。
    """
    s = Settings(
        **_settings(
            DEBUG=True,
            JWT_SECRET=_STRONG_JWT,
            API_TOKEN=_STRONG_TOKEN,
        ),
        _env_file=None,
    )
    assert s.ENV_NAME == "local"


def test_real_settings_singleton_boots():
    """实机验证：当前仓库 .env（DEBUG=true，无 ENV_NAME）加载出的全局单例可正常工作。"""
    from app.config import settings as real_settings

    assert real_settings.ENV_NAME == "local"
