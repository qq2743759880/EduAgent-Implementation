"""
P7 管理端控制台 - 用户管理 router。
全量 require_role([ADMIN])。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth import CurrentUser, UserRole, require_role
from app.admin.user_admin import service
from app.admin.user_admin.schemas import (
    AdminUserListResponse,
    DashboardMetrics,
    RoleChangeRequest,
    UserStatusRequest,
)

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-user"],
    dependencies=[Depends(require_role([UserRole.ADMIN]))],
)


@router.get("", response_model=AdminUserListResponse)
async def admin_list_users(
    role_code: Optional[str] = None,
    keyword: Optional[str] = None,
    status: Optional[int] = None,
    yn: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return await service.list_users(
        role_code=role_code,
        keyword=keyword,
        status=status,
        yn=yn,
        page=page,
        page_size=page_size,
    )


@router.post("/{user_id}/role", response_model=dict)
async def admin_change_role(
    user_id: int,
    payload: RoleChangeRequest,
    operator: CurrentUser = Depends(require_role([UserRole.ADMIN])),
):
    await service.change_user_role(user_id, payload, operator_id=operator.user_id)
    return {"updated": True, "user_id": user_id, "target_role": payload.target_role}


@router.post("/{user_id}/status", response_model=dict)
async def admin_change_status(user_id: int, payload: UserStatusRequest):
    await service.update_user_status(user_id, payload)
    return {"updated": True, "user_id": user_id, "status": payload.status, "yn": payload.yn}


@router.get("/dashboard/metrics", response_model=DashboardMetrics)
async def admin_dashboard_metrics():
    return await service.get_dashboard_metrics()
