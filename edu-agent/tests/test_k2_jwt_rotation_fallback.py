# -*- coding: utf-8 -*-
"""C5-K2：JWT_SECRET 轮换 fallback（JWT_SECRET_PREVIOUS）契约测试（离线，不触 DB）。

用例矩阵：
  ① 旧密钥签发的 token，配置 previous 后仍可验签解析（轮换窗口期语义）
  ② 未配置 previous 时旧密钥 token 被拒（AUTH_TOKEN_INVALID，行为与现状一致）
  ③ 签发永远用当前密钥：轮换后新签 token 用 previous 密钥无法伪造/旧密钥签不出新语义
  ④ 过期语义不受 fallback 干扰：旧密钥签+已过期 → AUTH_TOKEN_EXPIRED；
     当前密钥签+已过期 → AUTH_TOKEN_EXPIRED（不走 fallback 分支）
  ⑤ previous == JWT_SECRET（自指配置）视同未配置，不改变验签路径

守则对齐：禁 DB 直写；禁 Playwright；密钥全部 monkeypatch 注入。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt as pyjwt
import pytest

from app.auth import service as auth_service
from app.auth.schemas import UserRole
from app.common.exceptions import ValidationError
from app.config import settings

_OLD_SECRET = "rotation-old-secret-" + "0" * 40
_NEW_SECRET = "rotation-new-secret-" + "1" * 40


def _sign(payload: dict, secret: str) -> str:
    return pyjwt.encode(payload, secret, algorithm="HS256")


def test_old_key_token_verifiable_with_previous(monkeypatch):
    """① 旧密钥签的 token 在配置 previous 后仍可验。"""
    old_token = _sign(
        {"sub": "7", "role": "admin", "token_type": "access", "exp": 9999999999},
        _OLD_SECRET,
    )
    monkeypatch.setattr(settings, "JWT_SECRET", _NEW_SECRET)
    monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", _OLD_SECRET)
    data = auth_service.decode_token(old_token, expect_type="access")
    assert data.user_id == 7
    assert data.role == UserRole.ADMIN


def test_old_key_token_rejected_without_previous(monkeypatch):
    """② 未配置 previous（默认空）→ 旧密钥 token 拒绝，语义同现状。"""
    old_token = _sign(
        {"sub": "7", "role": "admin", "token_type": "access", "exp": 9999999999},
        _OLD_SECRET,
    )
    monkeypatch.setattr(settings, "JWT_SECRET", _NEW_SECRET)
    monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", "")
    with pytest.raises(ValidationError) as ei:
        auth_service.decode_token(old_token)
    assert ei.value.code == "40101"
    assert "AUTH_TOKEN_INVALID" in (ei.value.detail or "")


def test_signing_always_uses_current_secret(monkeypatch):
    """③ 签发恒用当前密钥：轮换后新签 token 不含旧密钥参与。"""
    monkeypatch.setattr(settings, "JWT_SECRET", _NEW_SECRET)
    monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", _OLD_SECRET)
    token, _ = auth_service.create_access_token(42, UserRole.STUDENT)
    # 用当前密钥手动验签应通过；仅用旧密钥验签应失败
    payload = pyjwt.decode(token, _NEW_SECRET, algorithms=["HS256"])
    assert payload["sub"] == "42"
    with pytest.raises(pyjwt.InvalidTokenError):
        pyjwt.decode(token, _OLD_SECRET, algorithms=["HS256"])


def test_old_key_expired_token_reports_expired(monkeypatch):
    """④-a 旧密钥签+已过期（配置 previous）→ 过期语义优先。"""
    expired = _sign(
        {
            "sub": "1",
            "role": "student",
            "token_type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        _OLD_SECRET,
    )
    monkeypatch.setattr(settings, "JWT_SECRET", _NEW_SECRET)
    monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", _OLD_SECRET)
    with pytest.raises(ValidationError) as ei:
        auth_service.decode_token(expired)
    assert ei.value.code == "40102"
    assert "AUTH_TOKEN_EXPIRED" in (ei.value.detail or "")


def test_current_key_expired_token_reports_expired(monkeypatch):
    """④-b 当前密钥签+已过期 → 不走 fallback 直接判过期（回归）。"""
    expired = _sign(
        {
            "sub": "1",
            "role": "student",
            "token_type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        _NEW_SECRET,
    )
    monkeypatch.setattr(settings, "JWT_SECRET", _NEW_SECRET)
    monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", _OLD_SECRET)
    with pytest.raises(ValidationError) as ei:
        auth_service.decode_token(expired)
    assert ei.value.code == "40102"


def test_previous_same_as_current_treated_as_unset(monkeypatch):
    """⑤ previous == 当前密钥（自指）→ 视同未配置，伪造 token 拒绝。"""
    forged = _sign(
        {"sub": "999", "role": "admin", "token_type": "access", "exp": 9999999999},
        _OLD_SECRET,
    )
    monkeypatch.setattr(settings, "JWT_SECRET", _NEW_SECRET)
    monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", _NEW_SECRET)
    with pytest.raises(ValidationError) as ei:
        auth_service.decode_token(forged)
    assert ei.value.code == "40101"
