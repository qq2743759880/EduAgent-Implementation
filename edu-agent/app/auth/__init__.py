"""
鉴权模块公共出口（供其他模块 `from app.auth import X` 统一引用）。

按 RBAC 规范暴露：
- UserRole       : 四级角色枚举
- CurrentUser    : Depends 参数类型别名（= UserInfo）
- get_current_user : 登录态校验依赖（DEBUG 虚拟管理员 / 生产 JWT）
- require_role   : 高阶依赖工厂，require_role([ADMIN, MANAGER]) 返回 Depends 函数
"""
from app.auth.schemas import UserRole
from app.auth.dependencies import CurrentUser, get_current_user, require_role
from app.auth.service import create_access_token, create_refresh_token, hash_password, verify_password

__all__ = [
    "UserRole",
    "CurrentUser",
    "get_current_user",
    "require_role",
    "create_access_token",
    "create_refresh_token",
    "hash_password",
    "verify_password",
]
