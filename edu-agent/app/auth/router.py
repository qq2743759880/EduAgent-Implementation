"""
鉴权模块 —— HTTP 路由。

4 个接口：
- POST /api/auth/register  : 注册（用户名/密码）
- POST /api/auth/login     : 登录（账号+密码 → 双 Token）
- POST /api/auth/refresh   : 刷新 Token（refresh_token → 新双 Token）
- GET  /api/auth/me        : 当前用户信息（需登录）

路由统一前缀 `/api/auth`，Swagger 归到 "鉴权" 分组。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.schemas import (
    LoginResponse,
    RefreshTokenRequest,
    UserInfo,
    UserLogin,
    UserRegister,
)
from app.auth.service import (
    login_user,
    refresh_access_token,
    register_user,
)
from app.common.exceptions import DatabaseError, ValidationError
from app.common.logging import logger

router = APIRouter(prefix="/api/auth", tags=["鉴权"])


# ============================================================
# 辅助：把业务层抛的 ValidationError/DatabaseError 转 HTTP 状态码
# ============================================================
def _translate_validation_error(e: ValidationError) -> HTTPException:
    """业务层错误码 → 对应 HTTP 状态码。"""
    # 账号相关错误 → 401 未认证
    auth_unauthorized_codes = {
        "AUTH_LOGIN_FAILED",
        "AUTH_TOKEN_EXPIRED",
        "AUTH_TOKEN_INVALID",
        "AUTH_TOKEN_MALFORMED",
        "AUTH_TOKEN_TYPE_MISMATCH",
        "AUTH_USER_DISABLED",
        "AUTH_USER_NOT_FOUND",
    }
    # 角色相关错误 → 403 无权限
    auth_forbidden_codes = {"AUTH_ROLE_INVALID"}
    # 注册冲突 → 409
    auth_conflict_codes = {
        "AUTH_MOBILE_EXISTS",
        "AUTH_EMAIL_EXISTS",
        "AUTH_ACCOUNT_EXISTS",
    }

    detail = {"code": e.code, "message": str(e)}
    if e.code in auth_unauthorized_codes:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if e.code in auth_forbidden_codes:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    if e.code in auth_conflict_codes:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    # 其他校验错误 → 400
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# ============================================================
# 1. 注册
# ============================================================
@router.post(
    "/register",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
    description="用手机号或邮箱注册，默认角色为 student。返回新注册的 user_id。",
)
async def register(
    req: UserRegister,
):
    try:
        new_user_id = await register_user(req)
    except ValidationError as e:
        raise _translate_validation_error(e) from e
    except DatabaseError as e:
        logger.exception(f"[auth.router.register] 数据库异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DB_ERROR", "message": str(e)},
        ) from e
    return {
        "code": 0,
        "message": "注册成功",
        "data": {"user_id": new_user_id},
    }


# ============================================================
# 2. 登录
# ============================================================
@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="用户登录",
    description="账号(手机号/邮箱) + 密码登录，返回 access_token + refresh_token + 用户信息。",
)
async def login(
    req: UserLogin,
):
    try:
        login_result = await login_user(req)
    except ValidationError as e:
        raise _translate_validation_error(e) from e
    except DatabaseError as e:
        logger.exception(f"[auth.router.login] 数据库异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DB_ERROR", "message": str(e)},
        ) from e
    return login_result


# ============================================================
# 3. 刷新 Token（滑动过期）
# ============================================================
@router.post(
    "/refresh",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="刷新访问令牌",
    description="用 refresh_token 换一对新的 access_token + refresh_token，实现 7 天滑动过期。",
)
async def refresh(
    req: RefreshTokenRequest,
):
    try:
        result = await refresh_access_token(req)
    except ValidationError as e:
        raise _translate_validation_error(e) from e
    except DatabaseError as e:
        logger.exception(f"[auth.router.refresh] 数据库异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DB_ERROR", "message": str(e)},
        ) from e
    return result


# ============================================================
# 4. 取当前用户（已登录才用）
# ============================================================
@router.get(
    "/me",
    response_model=UserInfo,
    status_code=status.HTTP_200_OK,
    summary="获取当前登录用户信息",
    description="需在 Header 携带 Authorization: Bearer <access_token>。",
)
async def get_me(
    user: CurrentUser = Depends(get_current_user),
):
    """
    Depends(get_current_user) 就会自动：
      - 校验 Authorization Header + JWT 签名 + 过期 + token_type=access
      - 去数据库取最新用户信息（角色可能被管理员改过）
      - 都通过后把 UserInfo 对象塞给 user 参数
    """
    return user
