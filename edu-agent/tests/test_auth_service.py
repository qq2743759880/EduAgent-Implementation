# -*- coding: utf-8 -*-
"""auth.service 核心单测：JWT 签发/校验/过期/伪造 + 密码哈希 + 登录业务（mock DB 层）。"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.auth import service as auth_service
from app.auth.schemas import UserInfo, UserLogin, UserRegister, UserRole
from app.common.exceptions import ValidationError


# ============================================================
# 一、密码哈希
# ============================================================
def test_hash_and_verify_password_roundtrip():
    h = auth_service.hash_password("Abc@12345")
    assert h != "Abc@12345"
    assert h.startswith("$2b$")
    assert auth_service.verify_password("Abc@12345", h) is True


def test_verify_password_wrong_password():
    h = auth_service.hash_password("Abc@12345")
    assert auth_service.verify_password("wrong", h) is False


def test_verify_password_invalid_hash_returns_false():
    assert auth_service.verify_password("x", "not-a-bcrypt-hash") is False


# ============================================================
# 二、JWT 签发 / 校验
# ============================================================
def test_create_and_decode_access_token():
    token, expires_in = auth_service.create_access_token(42, UserRole.STUDENT)
    assert expires_in == auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    data = auth_service.decode_token(token, expect_type="access")
    assert data.user_id == 42
    assert data.role == UserRole.STUDENT
    assert data.token_type == "access"


def test_create_and_decode_refresh_token():
    token = auth_service.create_refresh_token(7, UserRole.ADMIN)
    data = auth_service.decode_token(token, expect_type="refresh")
    assert data.user_id == 7
    assert data.role == UserRole.ADMIN
    assert data.token_type == "refresh"


def test_decode_wrong_type_rejected():
    access, _ = auth_service.create_access_token(1, UserRole.STUDENT)
    with pytest.raises(ValidationError) as ei:
        auth_service.decode_token(access, expect_type="refresh")
    assert ei.value.code == "40104"
    assert "AUTH_TOKEN_TYPE_MISMATCH" in (ei.value.detail or "")


def test_decode_forged_token_rejected():
    """伪造签名（篡改 payload 不改签）必须失败。"""
    import jwt as pyjwt

    token = pyjwt.encode(
        {"sub": "999", "role": "admin", "token_type": "access"},
        "wrong-secret-wrong-secret-wrong-secret-wrong-secret-0000",
        algorithm="HS256",
    )
    with pytest.raises(ValidationError) as ei:
        auth_service.decode_token(token)
    assert ei.value.code == "40101"
    assert "AUTH_TOKEN_INVALID" in (ei.value.detail or "")


def test_decode_expired_token_rejected(monkeypatch):
    """手动构造一个已过期的 token → AUTH_TOKEN_EXPIRED。"""
    import jwt as pyjwt

    from app.config import settings

    expired = pyjwt.encode(
        {
            "sub": "1",
            "role": "student",
            "token_type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(ValidationError) as ei:
        auth_service.decode_token(expired)
    assert ei.value.code == "40102"
    assert "AUTH_TOKEN_EXPIRED" in (ei.value.detail or "")


def test_decode_malformed_token_rejected():
    """payload 缺字段（无 sub/role/exp）→ 拒绝。"""
    import jwt as pyjwt

    from app.config import settings

    bad = pyjwt.encode(
        {"foo": "bar"},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(ValidationError) as ei:
        auth_service.decode_token(bad)
    assert ei.value.code == "40103"
    assert "AUTH_TOKEN_MALFORMED" in (ei.value.detail or "")


def test_decode_invalid_role_rejected():
    import jwt as pyjwt

    from app.config import settings

    bad = pyjwt.encode(
        {"sub": "1", "role": "superadmin", "token_type": "access", "exp": 9999999999},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(ValidationError) as ei:
        auth_service.decode_token(bad)
    assert ei.value.code == "40105"
    assert "AUTH_ROLE_INVALID" in (ei.value.detail or "")


# ============================================================
# 三、注册（mock fetch_one + transaction）
# ============================================================
@pytest.mark.asyncio
async def test_register_success(monkeypatch):
    """正常注册：查重返回 None → 事务插入 → 返回新 id。"""
    async def fake_fetch_one(sql, args):
        return None  # 无冲突

    calls = []

    class FakeCur:
        lastrowid = 88

        async def execute(self, sql, args=None):
            calls.append((sql, args))

    class FakeConn:
        def __init__(self):
            self.lastrowid = 88

        async def commit(self):
            calls.append(("commit", None))

        async def execute(self, sql, args=None):
            calls.append((sql, args))

    class FakeCtx:
        def __init__(self, conn, cur):
            self._conn, self._cur = conn, cur

        async def __aenter__(self):
            return (self._conn, self._cur)  # (conn, cur)

        async def __aexit__(self, *exc):
            return False

    class FakeTx:
        def __init__(self, conn, cur):
            self._conn, self._cur = conn, cur

        def __call__(self):
            return FakeCtx(self._conn, self._cur)

    monkeypatch.setattr(auth_service, "fetch_one", fake_fetch_one)
    conn = FakeConn()
    monkeypatch.setattr(auth_service, "transaction", FakeTx(conn, FakeCur()))

    req = UserRegister(
        account="alice_test", nickname="Alice", password="Abc@12345", email="alice_test@example.com",
    )
    uid = await auth_service.register_user(req)
    assert uid == 88
    # 验证确实执行了两次 INSERT（sys_user + sys_user_auth）+ commit
    insert_sqls = [c[0] for c in calls if c[0] and "INSERT" in c[0]]
    assert len(insert_sqls) == 2
    assert any("sys_user_auth" in s for s in insert_sqls)


@pytest.mark.asyncio
async def test_register_duplicate_account(monkeypatch):
    """account 已存在 → AUTH_ACCOUNT_EXISTS。"""
    async def fake_fetch_one(sql, args):
        return {"account": "alice", "mobile": None, "email": None}

    monkeypatch.setattr(auth_service, "fetch_one", fake_fetch_one)
    req = UserRegister(account="alice", nickname="Alice", password="Abc@12345", email="a2@e.com")
    with pytest.raises(ValidationError) as ei:
        await auth_service.register_user(req)
    assert ei.value.code == "40912"
    assert "AUTH_ACCOUNT_EXISTS" in (ei.value.detail or "")


@pytest.mark.asyncio
async def test_register_no_account_field():
    """account 为空且未提供 mobile/email → schema 层拒绝（防 AUTH_ACCOUNT_MISSING 死路径）。"""
    from pydantic import ValidationError as PyValidationError

    # mobile 和 email 同时为 None → pydantic 拒绝
    with pytest.raises(PyValidationError):
        UserRegister(account="", nickname="Alice", password="Abc@12345", mobile=None, email=None)
    # account 少于 4 字符 → pydantic 拒绝
    with pytest.raises(PyValidationError):
        UserRegister(account="ab", nickname="Alice", password="Abc@12345", email="a@e.com")


# ============================================================
# 四、登录（mock _find_user_by_account）
# ============================================================
def _mk_user_row(**overrides) -> dict:
    row = {
        "user_id": 1,
        "account": "alice",
        "username": "alice",
        "nickname": "Alice",
        "real_name": None,
        "mobile": None,
        "email": "alice@example.com",
        "gender": None,
        "avatar_url": None,
        "yn": 1,
        "status": 1,
        "password_hash": auth_service.hash_password("Abc@12345"),
        "role_code": "student",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_login_success(monkeypatch):
    async def fake_find(account):
        return _mk_user_row()

    monkeypatch.setattr(auth_service, "_find_user_by_account", fake_find)
    resp = await auth_service.login_user(UserLogin(account="alice", password="Abc@12345"))
    assert resp.token_type == "Bearer"
    assert resp.expires_in > 0
    assert resp.user.user_id == 1
    assert resp.user.role == UserRole.STUDENT
    assert resp.access_token and resp.refresh_token


@pytest.mark.asyncio
async def test_login_wrong_password(monkeypatch):
    async def fake_find(account):
        return _mk_user_row()

    monkeypatch.setattr(auth_service, "_find_user_by_account", fake_find)
    with pytest.raises(ValidationError) as ei:
        await auth_service.login_user(UserLogin(account="alice", password="WrongPass1"))
    # 统一「账号或密码错误」，防账号枚举
    assert ei.value.code == "40111"


@pytest.mark.asyncio
async def test_login_unknown_account(monkeypatch):
    async def fake_find(account):
        return None

    monkeypatch.setattr(auth_service, "_find_user_by_account", fake_find)
    with pytest.raises(ValidationError) as ei:
        await auth_service.login_user(UserLogin(account="nobody", password="Abc@12345"))
    assert ei.value.code == "40111"


@pytest.mark.asyncio
async def test_login_disabled_user(monkeypatch):
    """status=0（管理员禁用）→ AUTH_USER_DISABLED。"""
    async def fake_find(account):
        return _mk_user_row(status=0)

    monkeypatch.setattr(auth_service, "_find_user_by_account", fake_find)
    with pytest.raises(ValidationError) as ei:
        await auth_service.login_user(UserLogin(account="alice", password="Abc@12345"))
    assert ei.value.code == "40312"
    assert "AUTH_USER_DISABLED" in (ei.value.detail or "")


@pytest.mark.asyncio
async def test_login_soft_deleted_user(monkeypatch):
    """yn=0（注销）→ AUTH_USER_DISABLED。"""
    async def fake_find(account):
        return _mk_user_row(yn=0)

    monkeypatch.setattr(auth_service, "_find_user_by_account", fake_find)
    with pytest.raises(ValidationError) as ei:
        await auth_service.login_user(UserLogin(account="alice", password="Abc@12345"))
    assert ei.value.code == "40312"
    assert "AUTH_USER_DISABLED" in (ei.value.detail or "")


# ============================================================
# 五、refresh / 用户信息
# ============================================================
@pytest.mark.asyncio
async def test_refresh_access_token(monkeypatch):
    token = auth_service.create_refresh_token(5, UserRole.MANAGER)
    # mock get_user_info_by_id 返回固定用户
    async def fake_get(uid):
        return UserInfo(
            user_id=5, nickname="M", real_name="", mobile=None, email="m@e.com",
            gender=None, avatar_url=None, role=UserRole.MANAGER,
        )

    monkeypatch.setattr(auth_service, "get_user_info_by_id", fake_get)
    resp = await auth_service.refresh_access_token(
        type("R", (), {"refresh_token": token})()
    )
    assert resp.user.user_id == 5
    assert resp.user.role == UserRole.MANAGER
    assert resp.access_token != token


@pytest.mark.asyncio
async def test_refresh_with_access_token_rejected():
    access, _ = auth_service.create_access_token(5, UserRole.STUDENT)
    with pytest.raises(ValidationError) as ei:
        await auth_service.refresh_access_token(type("R", (), {"refresh_token": access})())
    assert ei.value.code == "40104"
    assert "AUTH_TOKEN_TYPE_MISMATCH" in (ei.value.detail or "")


@pytest.mark.asyncio
async def test_refresh_user_deleted(monkeypatch):
    token = auth_service.create_refresh_token(5, UserRole.STUDENT)

    async def fake_get(uid):
        return None

    monkeypatch.setattr(auth_service, "get_user_info_by_id", fake_get)
    with pytest.raises(ValidationError) as ei:
        await auth_service.refresh_access_token(type("R", (), {"refresh_token": token})())
    assert ei.value.code == "40413"
    assert "AUTH_USER_NOT_FOUND" in (ei.value.detail or "")


@pytest.mark.asyncio
async def test_get_user_info_by_id(monkeypatch):
    async def fake_fetch_one(sql, args):
        return {
            "user_id": 9, "account": "bob", "username": "bob", "nickname": "Bob",
            "real_name": None, "mobile": None, "email": "bob@e.com", "gender": None,
            "avatar_url": None, "role_code": "teacher",
        }

    monkeypatch.setattr(auth_service, "fetch_one", fake_fetch_one)
    info = await auth_service.get_user_info_by_id(9)
    assert info is not None
    assert info.nickname == "Bob"
    assert info.role == UserRole.TEACHER


@pytest.mark.asyncio
async def test_get_user_info_by_id_missing(monkeypatch):
    async def fake_fetch_one(sql, args):
        return None

    monkeypatch.setattr(auth_service, "fetch_one", fake_fetch_one)
    assert await auth_service.get_user_info_by_id(999) is None
