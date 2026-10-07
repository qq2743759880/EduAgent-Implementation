"""
鉴权模块 —— FastAPI 依赖注入（路由级权限控制）。

其他模块的路由想做权限保护时，只要这样写：

    from fastapi import Depends
    from app.auth import get_current_user, require_role, UserRole, CurrentUser

    @router.get("/my/profile")
    async def my_profile(user: CurrentUser = Depends(get_current_user)):
        # 只要进来了，user 就是已登录的 UserInfo 对象
        return {"nickname": user.nickname}

    @router.get("/admin/users")
    async def admin_list_users(
        user: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
    ):
        # 只有 admin / manager 角色能进来，其他人直接 403
        ...
"""
from __future__ import annotations

from typing import Annotated, Iterable

from fastapi import Depends, HTTPException, Request, status

from app.auth.schemas import UserInfo, UserRole
from app.auth.service import decode_token, get_user_info_by_id
from app.config import settings


# 方便路由参数类型简写：CurrentUser = UserInfo
CurrentUser = UserInfo


# ============================================================
# 1. 从 HTTP Header 里提取 Bearer Token
# ============================================================
def _extract_bearer_token(request: Request) -> str:
    """
    从 Authorization: "Bearer xxx" 中提取 Token 字符串。
    取不到或格式错 → 直接抛 HTTPException(401)。
    """
    auth_header: str | None = request.headers.get("Authorization")
    if auth_header is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Authorization 请求头",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization 格式应为: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1]


# ============================================================
# 2. get_current_user —— 只要登录了就能用
# ============================================================
async def get_current_user(
    request: Request,
) -> UserInfo:
    """
    FastAPI 依赖：验证登录并返回当前用户信息。

    规则（按优先级）：
    1. 只要请求带了 Authorization Header → 强制走真实 JWT 校验（不管 DEBUG）
       （保证测试 register→login→refresh→me 真实链路畅通）
    2. 没带 Header 且 DEBUG=True → 虚拟超级管理员（方便调试无 Token 场景）
    3. 没带 Header 且 DEBUG=False → 401
    """
    auth_header: str | None = request.headers.get("Authorization")

    # --- DEBUG 模式下，测试打靶专用：X-Force-Role / X-Force-User-Id 直接返回虚拟用户
    # （必须和 Authorization 都不传或传了也可以，force 优先级最高。仅 DEBUG=true 生效。）---
    if settings.DEBUG:
        force_role_raw = request.headers.get("X-Force-Role")
        if force_role_raw:
            try:
                force_role = UserRole(force_role_raw)
            except Exception:
                force_role = None
            if force_role is not None:
                force_user_id_raw = request.headers.get("X-Force-User-Id")
                try:
                    force_user_id = int(force_user_id_raw) if force_user_id_raw else (1 if force_role == UserRole.ADMIN else 2)
                except Exception:
                    force_user_id = 1 if force_role == UserRole.ADMIN else 2
                return UserInfo(
                    user_id=force_user_id,
                    nickname=f"DEBUG_{force_role.value}",
                    real_name=f"调试用户({force_role.value})",
                    mobile=None,
                    email=f"debug_{force_role.value}@edu.agent",
                    gender=None,
                    avatar_url=None,
                    role=force_role,
                )

    # ---- 规则 1：带了 Authorization → 强制真实校验（无论 DEBUG / 生产） ----
    if auth_header:
        token = _extract_bearer_token(request)
        token_data = decode_token(token, expect_type="access")
        user = await get_user_info_by_id(token_data.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在或已被删除",
            )
        return user

    # ---- 规则 2：没带 + DEBUG → 虚拟管理员（健康检查 / 空接口调试用） ----
    if settings.DEBUG:
        return UserInfo(
            user_id=1,
            nickname="DEBUG_超级管理员",
            real_name="调试用户",
            mobile=None,
            email="debug@edu.agent",
            gender=None,
            avatar_url=None,
            role=UserRole.ADMIN,
        )

    # ---- 规则 3：生产模式没带 → 401 ----
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="缺少 Authorization 请求头",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ============================================================
# 3. require_role —— 登录 + 角色校验（P7 管理端主用）
# ============================================================
def require_role(
    allowed_roles: Iterable[UserRole],
):
    """
    角色权限依赖工厂。返回一个 Depends 函数，只允许指定角色通过。

    例：
        Depends(require_role([UserRole.ADMIN, UserRole.MANAGER]))
    """
    allowed = set(allowed_roles)

    async def _check_role(
        user: Annotated[UserInfo, Depends(get_current_user)],
    ) -> UserInfo:
        if user.role not in allowed:
            allowed_names = [r.value for r in sorted(allowed, key=lambda r: r.value)]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"角色无权限。当前角色={user.role.value}，允许角色={allowed_names}",
            )
        return user

    return _check_role
