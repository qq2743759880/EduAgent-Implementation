"""
鉴权模块 —— 核心业务逻辑。

对外暴露的能力：
- hash_password / verify_password：bcrypt 密码哈希（不可逆、抗彩虹表）
- create_access_token / create_refresh_token：签发双 JWT（access 24h、refresh 7d）
- decode_token：验签 + 解析 payload（过期/签名错 → 抛异常）
- register_user：注册（sys_user + sys_user_auth 同事务 INSERT）
- login_user：登录（查账号 → bcrypt 比对密码 → 签发双 Token）
- refresh_access_token：用 refresh_token 换一对新 Token
- get_user_info_by_id：取用户详情 + 角色（/me 接口用）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.common.exceptions import DatabaseError, ValidationError
from app.common.logging import logger
from app.config import settings
from app.database import fetch_one, transaction
from app.auth.schemas import (
    LoginResponse,
    RefreshTokenRequest,
    TokenData,
    UserInfo,
    UserLogin,
    UserRegister,
    UserRole,
)

# ============================================================
# Token 过期时间 & 哈希轮次（从配置文件读取，方便不同环境覆盖）
# ============================================================
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
PASSWORD_HASH_ROUNDS = settings.PASSWORD_HASH_ROUNDS


# ============================================================
# 一、密码哈希层（bcrypt，带盐、自带抗彩虹表）
# ============================================================
def hash_password(raw_password: str) -> str:
    """把明文密码哈希成 bcrypt 字符串（返回值带盐和轮次信息）。"""
    hashed_bytes = bcrypt.hashpw(
        raw_password.encode("utf-8"),
        bcrypt.gensalt(rounds=PASSWORD_HASH_ROUNDS),
    )
    return hashed_bytes.decode("utf-8")


def verify_password(raw_password: str, hashed: str) -> bool:
    """比对明文密码和已存哈希值。True = 密码正确。"""
    try:
        return bcrypt.checkpw(
            raw_password.encode("utf-8"),
            hashed.encode("utf-8"),
        )
    except ValueError:
        return False


# ============================================================
# 二、JWT 层（签发 + 解析）
# ============================================================
def _sign_jwt(payload: dict, expire_minutes: int) -> str:
    """内部工具：给任意 payload 签发 JWT（统一算法/密钥，从 settings 读）。"""
    to_encode = payload.copy()
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    to_encode.update({"exp": expire_at})
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(user_id: int, role: UserRole) -> tuple[str, int]:
    """签发 access_token。返回 (jwt 字符串, 剩余有效秒数)。"""
    minutes = ACCESS_TOKEN_EXPIRE_MINUTES
    token = _sign_jwt(
        payload={
            "sub": str(user_id),
            "role": role.value,
            "token_type": "access",
        },
        expire_minutes=minutes,
    )
    return token, minutes * 60


def create_refresh_token(user_id: int, role: UserRole) -> str:
    """签发 refresh_token（7 天有效，滑动过期）。"""
    minutes = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60
    return _sign_jwt(
        payload={
            "sub": str(user_id),
            "role": role.value,
            "token_type": "refresh",
        },
        expire_minutes=minutes,
    )


def decode_token(token: str, *, expect_type: str | None = None) -> TokenData:
    """
    验签 + 解析 JWT。

    参数：
    - expect_type：传 "access" 或 "refresh" 时，额外校验 token_type 匹配

    C5-K2 轮换 fallback：配置 JWT_SECRET_PREVIOUS 后，验签先试当前密钥
    （JWT_SECRET），签名不符再试旧密钥——密钥轮换窗口期内旧 token 仍可验，
    签发（_sign_jwt）永远只用当前密钥。过期语义不受 fallback 影响：
    当前密钥验出 ExpiredSignatureError 直接判过期（说明确为当前密钥签发）。
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as e:
        raise ValidationError("登录已过期，请重新登录", code="AUTH_TOKEN_EXPIRED") from e
    except jwt.InvalidTokenError as first_err:
        prev_secret = (settings.JWT_SECRET_PREVIOUS or "").strip()
        if prev_secret and prev_secret != settings.JWT_SECRET:
            try:
                payload = jwt.decode(
                    token,
                    prev_secret,
                    algorithms=[settings.JWT_ALGORITHM],
                )
            except jwt.ExpiredSignatureError as e:
                # 旧密钥签发但已过期：过期语义优先于密钥来源
                raise ValidationError("登录已过期，请重新登录", code="AUTH_TOKEN_EXPIRED") from e
            except jwt.InvalidTokenError:
                raise ValidationError("登录凭证无效", code="AUTH_TOKEN_INVALID") from first_err
        else:
            raise ValidationError("登录凭证无效", code="AUTH_TOKEN_INVALID") from first_err

    user_id_str: str | None = payload.get("sub")
    role_str: str | None = payload.get("role")
    token_type: str | None = payload.get("token_type")
    exp_ts: int | None = payload.get("exp")
    if not user_id_str or not role_str or exp_ts is None:
        raise ValidationError("登录凭证缺失必要字段", code="AUTH_TOKEN_MALFORMED")

    if expect_type is not None and token_type != expect_type:
        raise ValidationError(
            f"Token 类型不匹配：期望 {expect_type}",
            code="AUTH_TOKEN_TYPE_MISMATCH",
        )

    try:
        role_enum = UserRole(role_str)
    except ValueError as e:
        raise ValidationError("角色非法", code="AUTH_ROLE_INVALID") from e

    return TokenData(
        user_id=int(user_id_str),
        role=role_enum,
        exp=datetime.fromtimestamp(exp_ts, tz=timezone.utc),
        token_type=token_type or "access",
    )


# ============================================================
# 三、业务逻辑：注册 / 登录 / 刷新 / 个人信息
# ============================================================
async def register_user(req: UserRegister) -> int:
    """
    用户注册。返回新用户 user_id。

    流程：
    1. 推导登录账号（account → mobile → email 兜底）
    2. 查重（account/手机号/邮箱任一已存在 → 409）
    3. 密码 bcrypt 哈希
    4. 同事务 INSERT sys_user → INSERT sys_user_auth
    """
    # --- 1. 推导登录账号：account > mobile > email ---
    account_val: str = (
        req.account
        or req.mobile
        or (req.email if req.email else "")
    ).strip()
    if not account_val:
        raise ValidationError(
            "注册失败：缺少登录账号（account / mobile / email 至少填一个）",
            code="AUTH_ACCOUNT_MISSING",
        )
    username_val: str = (req.account or req.nickname).strip()

    # --- 2. 查重：account / mobile / email 任一冲突都拒绝 ---
    duplicate_sql = """
        SELECT id, account, mobile, email FROM sys_user
        WHERE yn = 1 AND (account = %s OR mobile = %s OR email = %s)
        LIMIT 1
    """
    dup = await fetch_one(duplicate_sql, (account_val, req.mobile, req.email))
    if dup is not None:
        if dup.get("account") == account_val:
            raise ValidationError("该登录账号已被注册", code="AUTH_ACCOUNT_EXISTS")
        if req.mobile and dup.get("mobile") == req.mobile:
            raise ValidationError("该手机号已注册", code="AUTH_MOBILE_EXISTS")
        if req.email and dup.get("email") == req.email:
            raise ValidationError("该邮箱已注册", code="AUTH_EMAIL_EXISTS")
        raise ValidationError("账号已存在", code="AUTH_ACCOUNT_EXISTS")

    # --- 3. 密码哈希 ---
    pwd_hash = hash_password(req.password)
    default_role = UserRole.STUDENT.value

    # --- 4. 同事务写两张表（sys_user + sys_user_auth 一对一）---
    insert_user_sql = """
        INSERT INTO sys_user
        (account, username, nickname, real_name, mobile, email, gender, yn, created_at, updated_at)
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, 1, NOW(), NOW())
    """
    insert_auth_sql = """
        INSERT INTO sys_user_auth
        (user_id, password_hash, role_code, created_at, updated_at)
        VALUES
        (%s, %s, %s, NOW(), NOW())
    """
    try:
        async with transaction() as (conn, cur):
            await cur.execute(
                insert_user_sql,
                (
                    account_val, username_val,
                    req.nickname, req.real_name,
                    req.mobile, req.email, req.gender,
                ),
            )
            user_id = int(cur.lastrowid)
            await cur.execute(
                insert_auth_sql,
                (user_id, pwd_hash, default_role),
            )
            await conn.commit()
        logger.info(f"[auth.register] 新用户注册成功 user_id={user_id} account={account_val}")
        return user_id
    except DatabaseError:
        raise
    except Exception as e:
        logger.exception(f"[auth.register] 写入失败: {e}")
        raise DatabaseError(f"注册失败: {e}") from e


async def _find_user_by_account(account: str) -> dict | None:
    """
    登录辅助：用「账号」三选一（account 登录账号 / 手机号 / 邮箱）
    JOIN 查用户 + 密码哈希 + 角色。

    注意：不去 yn=1 过滤 —— 是否可用由 login 显式检查 status/yn 双字段，
    否则仅 status=0 禁用时查询直接查不到用户，会误报「账号或密码错误」，
    使 AUTH_USER_DISABLED 分支成为死代码。
    """
    sql = """
        SELECT
            u.id           AS user_id,
            u.account      AS account,
            u.username     AS username,
            u.nickname     AS nickname,
            u.real_name    AS real_name,
            u.mobile       AS mobile,
            u.email        AS email,
            u.gender       AS gender,
            u.avatar_url   AS avatar_url,
            u.yn           AS yn,
            u.status       AS status,
            a.password_hash AS password_hash,
            a.role_code    AS role_code
        FROM sys_user u
        INNER JOIN sys_user_auth a ON a.user_id = u.id
        WHERE (u.account = %s OR u.mobile = %s OR u.email = %s)
        LIMIT 1
    """
    return await fetch_one(sql, (account, account, account))


async def login_user(req: UserLogin) -> LoginResponse:
    """
    用户登录。返回 LoginResponse（双 Token + 用户信息）。

    密码错和账号不存在统一返回「账号或密码错误」—— 防止攻击者枚举已注册账号。
    禁用检查：yn=0（注销/删除）或 status=0（管理员禁用）任一命中 → AUTH_USER_DISABLED。
    """
    row = await _find_user_by_account(req.account)
    if row is None:
        raise ValidationError("账号或密码错误", code="AUTH_LOGIN_FAILED")
    # 注意：不能用 `row["status"] or 1` —— status=0 是 falsy，会被误替换成 1，禁用判定失效
    status_val = row.get("status")
    if int(row["yn"]) != 1 or (status_val is not None and int(status_val) != 1):
        raise ValidationError("该账号已被禁用，请联系管理员", code="AUTH_USER_DISABLED")

    pwd_hash: str = row["password_hash"] or ""
    if not verify_password(req.password, pwd_hash):
        raise ValidationError("账号或密码错误", code="AUTH_LOGIN_FAILED")

    role = UserRole(row["role_code"])
    access_str, expires_in = create_access_token(int(row["user_id"]), role)
    refresh_str = create_refresh_token(int(row["user_id"]), role)

    user = UserInfo(
        user_id=int(row["user_id"]),
        account=row.get("account") or None,
        username=row.get("username") or row.get("account") or None,
        nickname=row["nickname"],
        real_name=row["real_name"],
        mobile=row["mobile"],
        email=row["email"],
        gender=row["gender"],
        avatar_url=row["avatar_url"],
        role=role,
    )
    logger.info(f"[auth.login] 用户登录成功 user_id={user.user_id} role={role.value}")
    return LoginResponse(
        access_token=access_str,
        refresh_token=refresh_str,
        token_type="Bearer",
        expires_in=expires_in,
        user=user,
    )


async def refresh_access_token(req: RefreshTokenRequest) -> LoginResponse:
    """
    用 refresh_token 换新 access_token（同时换 refresh_token，实现「滑动过期」）。
    """
    token_data = decode_token(req.refresh_token, expect_type="refresh")
    user_info = await get_user_info_by_id(token_data.user_id)
    if user_info is None:
        raise ValidationError("用户不存在", code="AUTH_USER_NOT_FOUND")

    access_str, expires_in = create_access_token(user_info.user_id, user_info.role)
    refresh_str = create_refresh_token(user_info.user_id, user_info.role)

    logger.info(f"[auth.refresh] Token 刷新成功 user_id={user_info.user_id}")
    return LoginResponse(
        access_token=access_str,
        refresh_token=refresh_str,
        token_type="Bearer",
        expires_in=expires_in,
        user=user_info,
    )


async def get_user_info_by_id(user_id: int) -> UserInfo | None:
    """
    按 user_id 取用户详情 + 角色（/me 接口、依赖注入内部都用它）。
    找不到返回 None。
    """
    sql = """
        SELECT
            u.id           AS user_id,
            u.account      AS account,
            u.username     AS username,
            u.nickname     AS nickname,
            u.real_name    AS real_name,
            u.mobile       AS mobile,
            u.email        AS email,
            u.gender       AS gender,
            u.avatar_url   AS avatar_url,
            a.role_code    AS role_code
        FROM sys_user u
        INNER JOIN sys_user_auth a ON a.user_id = u.id
        WHERE u.yn = 1 AND u.id = %s
        LIMIT 1
    """
    row = await fetch_one(sql, (user_id,))
    if row is None:
        return None
    return UserInfo(
        user_id=int(row["user_id"]),
        account=row.get("account") or None,
        username=row.get("username") or row.get("account") or None,
        nickname=row["nickname"],
        real_name=row["real_name"],
        mobile=row["mobile"],
        email=row["email"],
        gender=row["gender"],
        avatar_url=row["avatar_url"],
        role=UserRole(row["role_code"]),
    )
