"""
P7 管理端控制台 - 用户管理 schemas。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 列表项 + 列表
# ============================================================
class AdminUserItem(BaseModel):
    user_id: int
    username: Optional[str] = None
    real_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role_code: str
    status: int
    yn: int
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None


class AdminUserListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AdminUserItem]


# ============================================================
# 请求体
# ============================================================
class RoleChangeRequest(BaseModel):
    target_role: str = Field(..., pattern="^(admin|manager|teacher|student)$")
    reason: Optional[str] = Field(default=None, max_length=255)


class UserStatusRequest(BaseModel):
    status: int = Field(..., ge=0, le=1)
    yn: Optional[int] = Field(default=None, ge=0, le=1)
    reason: Optional[str] = Field(default=None, max_length=255)


# ============================================================
# 统计面板 6 指标
# ============================================================
class DashboardMetrics(BaseModel):
    total_user_count: int
    active_user_count_7d: int
    role_breakdown: dict[str, int]         # admin/manager/teacher/student
    disabled_user_count: int
    new_register_count_7d: int
    avg_login_days_per_user_30d: float
