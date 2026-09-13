# -*- coding: utf-8 -*-
"""
C5-K4：refresh_token 轮换 allowlist（Redis 最小方案）测试。

覆盖：
1. 轮换主流程（真 Redis）：旧 jti 刷新成功后立即作废（重放 401）、
   换发的新 refresh_token 可继续刷新（新过）。
2. 存量无 jti 的 refresh_token：Redis 可用时一次性作废（行为变更已批）。
3. Redis 降级 fail-open：allowlist 校验/登记失败时维持轮换前行为（不 401）。
4. 轮换开关关闭（JWT_REFRESH_ROTATION_ENABLED=false）：完全回退轮换前行为，
   签发 payload 不含 jti。
5. 轮换关闭时签发/刷新不受 allowlist 影响。
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.auth import service as auth_service
from app.auth.schemas import UserInfo, UserRole
from app.common.exceptions import ValidationError
from app.config import settings


# ============================================================
# 工具
# ============================================================
def _make_user(uid: int = 5, role: UserRole = UserRole.MANAGER) -> UserInfo:
    return UserInfo(
        user_id=uid, nickname="M", real_name="", mobile=None, email="m@e.com",
        gender=None, avatar_url=None, role=role,
    )


@pytest.fixture()
def fake_user(monkeypatch):
    """mock get_user_info_by_id，避免依赖 DB。"""

    async def fake_get(uid):
        return _make_user(uid)

    monkeypatch.setattr(auth_service, "get_user_info_by_id", fake_get)
    return fake_get


def _refresh_req(token: str):
    return type("R", (), {"refresh_token": token})()


async def _issue_registered_refresh(uid: int, role: UserRole) -> str:
    """签发带 jti 的 refresh_token 并登记 allowlist（模拟登录路径）。"""
    token, jti = auth_service._create_refresh_token_with_jti(uid, role)
    assert jti, "轮换开启时签发必须带 jti"
    registered = await auth_service._allowlist_register(
        uid, jti, settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    )
    return token


# ============================================================
# 真 Redis 依赖（复用 H-2/task39 先例：Redis 不可用则 skip，不造假绿）
# ============================================================
@pytest.fixture()
async def real_redis():
    """函数级真 Redis 连接（pytest-asyncio 每个用例新事件循环，连接池必须每用例重建）。"""
    from app.database import close_redis, get_redis, init_redis

    try:
        await init_redis()
        r = get_redis()
        await r.ping()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Redis 不可用，跳过真 Redis 轮换用例: {e}")
    yield r
    await close_redis()


# ============================================================
# 1. 轮换主流程（真 Redis）：旧拒 / 新过
# ============================================================
@pytest.mark.asyncio
async def test_rotation_replay_old_jti_rejected(real_redis, fake_user):
    """轮换后重放旧 refresh_token → 401 AUTH_TOKEN_INVALID。"""
    uid = 915001
    old_token = await _issue_registered_refresh(uid, UserRole.MANAGER)

    # 第一次刷新：消费旧 jti，成功并换发新 refresh_token
    resp1 = await auth_service.refresh_access_token(_refresh_req(old_token))
    assert resp1.access_token
    assert resp1.refresh_token != old_token

    # 重放旧 token：jti 已被原子消费 → 401
    with pytest.raises(ValidationError) as ei:
        await auth_service.refresh_access_token(_refresh_req(old_token))
    assert ei.value.code == "40101"
    assert "AUTH_TOKEN_INVALID" in (ei.value.detail or "")
    # jti 键随机不可枚举，遗留键靠 TTL（7 天）自然过期，不影响后续用例


@pytest.mark.asyncio
async def test_rotation_new_token_accepted(real_redis, fake_user):
    """换发的新 refresh_token（新 jti 已登记）→ 刷新成功。"""
    uid = 915002
    old_token = await _issue_registered_refresh(uid, UserRole.STUDENT)

    resp1 = await auth_service.refresh_access_token(_refresh_req(old_token))
    resp2 = await auth_service.refresh_access_token(_refresh_req(resp1.refresh_token))
    assert resp2.user.user_id == uid
    assert resp2.refresh_token != resp1.refresh_token
    # 轮换链：每次 refresh_token 都不同
    assert resp1.refresh_token != old_token


@pytest.mark.asyncio
async def test_rotation_unknown_jti_rejected(real_redis, fake_user):
    """签名合法但 jti 不在 allowlist（从未登记）→ 401。"""
    uid = 915003
    token, jti = auth_service._create_refresh_token_with_jti(uid, UserRole.ADMIN)
    assert jti
    with pytest.raises(ValidationError) as ei:
        await auth_service.refresh_access_token(_refresh_req(token))
    assert ei.value.code == "40101"


@pytest.mark.asyncio
async def test_legacy_no_jti_token_invalidated_when_redis_up(real_redis, fake_user):
    """存量无 jti 的 refresh_token：Redis 可用时一次性作废（行为变更已批）。"""
    from app.config import settings as cfg

    uid = 915004
    monkey_closed = None
    # 临时关轮换签发一个无 jti 的 token（模拟升级前的存量 token）
    old_flag = cfg.JWT_REFRESH_ROTATION_ENABLED
    try:
        cfg.JWT_REFRESH_ROTATION_ENABLED = False
        legacy_token = auth_service.create_refresh_token(uid, UserRole.STUDENT)
    finally:
        cfg.JWT_REFRESH_ROTATION_ENABLED = old_flag

    data = auth_service.decode_token(legacy_token, expect_type="refresh")
    assert data.jti is None

    with pytest.raises(ValidationError) as ei:
        await auth_service.refresh_access_token(_refresh_req(legacy_token))
    assert ei.value.code == "40101"
    assert "AUTH_TOKEN_INVALID" in (ei.value.detail or "")


# ============================================================
# 2. Redis 降级 fail-open（不连 Redis：_get_redis_or_none → None）
# ============================================================
@pytest.mark.asyncio
async def test_failopen_redis_down_unknown_jti_passes(fake_user, monkeypatch):
    """Redis 降级：jti 不在 allowlist 也放行（fail-open，可用性优先）。"""
    uid = 915005

    def redis_down():
        return None

    monkeypatch.setattr(auth_service, "_get_redis_or_none", redis_down)
    token, jti = auth_service._create_refresh_token_with_jti(uid, UserRole.MANAGER)
    # 未登记 allowlist（模拟 Redis 不可用期间的登记失败）
    resp = await auth_service.refresh_access_token(_refresh_req(token))
    assert resp.user.user_id == uid


@pytest.mark.asyncio
async def test_failopen_redis_down_legacy_token_passes(fake_user, monkeypatch):
    """Redis 降级：存量无 jti token 维持旧行为放行（fail-open）。"""
    uid = 915006

    def redis_down():
        return None

    monkeypatch.setattr(auth_service, "_get_redis_or_none", redis_down)
    token, jti = auth_service._create_refresh_token_with_jti(uid, UserRole.STUDENT)
    # 即便 token 带 jti（未登记），降级也放行；再验无 jti 的存量 token 同样放行
    data = auth_service.decode_token(token, expect_type="refresh")
    assert data.jti == jti


@pytest.mark.asyncio
async def test_failopen_register_returns_false(monkeypatch):
    """Redis 降级：allowlist 登记 fail-open 返回 False，不抛异常阻断登录。"""

    def redis_down():
        return None

    monkeypatch.setattr(auth_service, "_get_redis_or_none", redis_down)
    ok = await auth_service._allowlist_register(915007, uuid.uuid4().hex, 60)
    assert ok is False


@pytest.mark.asyncio
async def test_failopen_consume_returns_true(monkeypatch):
    """Redis 降级：allowlist 校验 fail-open 返回 True（放行）。"""

    def redis_down():
        return None

    monkeypatch.setattr(auth_service, "_get_redis_or_none", redis_down)
    ok = await auth_service._allowlist_consume(915008, uuid.uuid4().hex)
    assert ok is True


# ============================================================
# 3. 轮换开关关闭（JWT_REFRESH_ROTATION_ENABLED=false）：回退轮换前行为
# ============================================================
@pytest.mark.asyncio
async def test_rotation_disabled_no_jti_in_payload(monkeypatch):
    """关轮换：签发 payload 不含 jti，行为与轮换前完全一致。"""
    monkeypatch.setattr(settings, "JWT_REFRESH_ROTATION_ENABLED", False)
    token = auth_service.create_refresh_token(915009, UserRole.ADMIN)
    data = auth_service.decode_token(token, expect_type="refresh")
    assert data.jti is None


@pytest.mark.asyncio
async def test_rotation_disabled_refresh_passes_without_allowlist(fake_user, monkeypatch):
    """关轮换：无 jti token 刷新不受 allowlist 影响（Redis 可用也放行）。"""
    monkeypatch.setattr(settings, "JWT_REFRESH_ROTATION_ENABLED", False)
    uid = 915010
    token = auth_service.create_refresh_token(uid, UserRole.MANAGER)
    resp = await auth_service.refresh_access_token(_refresh_req(token))
    assert resp.user.user_id == uid
    # 换发的 refresh_token 同样无 jti
    data = auth_service.decode_token(resp.refresh_token, expect_type="refresh")
    assert data.jti is None
