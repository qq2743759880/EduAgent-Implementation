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

from fastapi import APIRouter, Depends, HTTPException, status

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
from app.core.resp import ok
from app.common.exceptions import DatabaseError, ValidationError
from app.common.logging import logger

router = APIRouter(prefix="/api/auth", tags=["鉴权"])


# ============================================================
# 辅助：把业务层抛的 ValidationError/DatabaseError 转 HTTP 状态码
# ============================================================
def _translate_validation_error(e: ValidationError) -> HTTPException:
    """
    业务层错误码 → 对应 HTTP 状态码。

    单一事实源：ValidationError 构造时已按 _AUTH_CODE_TO_HTTP 映射出 http_status
    （AUTH_LOGIN_FAILED→401、AUTH_USER_DISABLED→403、AUTH_ACCOUNT_EXISTS→409、其余→400）。
    旧实现把 e.code（数字业务码，如 40112）与字符串子码集合比较，永远不命中，
    导致所有鉴权错误一律落到 HTTP 400 —— 禁用提示与前端 LoginForm 文档（403）不一致。
    """
    headers = {"WWW-Authenticate": "Bearer"} if e.http_status == status.HTTP_401_UNAUTHORIZED else None
    return HTTPException(
        status_code=e.http_status,
        detail={"code": e.code, "message": str(e)},
        headers=headers,
    )


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
    response_model=dict,
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
    return ok(login_result)


# ============================================================
# 3. 刷新 Token（滑动过期）
# ============================================================
@router.post(
    "/refresh",
    response_model=dict,
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
    return ok(result)


# ============================================================
# 4. 取当前用户（已登录才用）
# ============================================================
@router.get(
    "/me",
    response_model=dict,
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
    return ok(user)
