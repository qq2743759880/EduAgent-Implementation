"""
管理端课程 CRUD 路由（task12 契约冻结③）。

前缀：/api/admin/courses
依赖：require_role([ADMIN, MANAGER])
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth import CurrentUser, get_current_user, require_role
from app.auth.schemas import UserRole
from app.common.exceptions import PermissionDeniedError
from app.core.resp import ok
from app.domains.course_admin import service as svc
from app.domains.course_admin.schemas import (
    CohortCreateAdmin,
    CohortUpdateAdmin,
    ModuleCreateAdmin,
    ModuleUpdateAdmin,
    SeriesCreateAdmin,
    SeriesUpdateAdmin,
    SessionCreateAdmin,
    SessionUpdateAdmin,
)

router = APIRouter(
    prefix="/api/admin/courses",
    tags=["course_admin · 管理端课程（task12）"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.MANAGER]))],
)


# ═══════════════════════════════════════════
# 系列 Series CRUD（5 端点）
# ═══════════════════════════════════════════

@router.get("/series", summary="管理端·系列列表（筛选+分页）")
async def admin_list_series(
    keyword: Optional[str] = Query(None, min_length=1, max_length=64),
    institution_id: Optional[int] = Query(None),
    delivery_mode: Optional[str] = Query(
        None, pattern=r"^(online_live|online_recorded|offline_face_to_face)$"
    ),
    sale_status: Optional[str] = Query(
        None, pattern=r"^(draft|on_sale|off_sale)$"
    ),
    include_deleted: bool = Query(False, description="true=包含已下架（软删）系列，回收站用"),
    sort: str = Query("default", pattern=r"^(default|newest|name_asc|name_desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    me: CurrentUser = Depends(get_current_user),
):
    data = await svc.list_series_admin(
        keyword=keyword, institution_id=institution_id,
        delivery_mode=delivery_mode, sale_status=sale_status,
        sort=sort, page=page, page_size=page_size,
        include_deleted=include_deleted,
    )
    return ok(data=data)


@router.get("/series/{series_id}", summary="管理端·系列详情")
async def admin_get_series(series_id: int, me: CurrentUser = Depends(get_current_user)):
    detail = await svc.get_series_admin(series_id)
    return ok(data=detail.model_dump(mode="json"))


@router.post("/series", summary="管理端·创建系列")
async def admin_create_series(payload: SeriesCreateAdmin, me: CurrentUser = Depends(get_current_user)):
    result = await svc.create_series(payload)
    return ok(data=result.model_dump(mode="json"))


@router.patch("/series/{series_id}", summary="管理端·更新系列")
async def admin_update_series(series_id: int, payload: SeriesUpdateAdmin,
                               me: CurrentUser = Depends(get_current_user)):
    result = await svc.update_series(series_id, payload)
    return ok(data=result.model_dump(mode="json"))


@router.delete("/series/{series_id}", summary="管理端·删除系列（软删下架 / ?hard=true 真删）")
async def admin_delete_series(
    series_id: int,
    hard: bool = Query(False, description="true=物理真删（仅 ADMIN，且零引用）"),
    me: CurrentUser = Depends(get_current_user),
):
    if hard and me.role != UserRole.ADMIN:
        raise PermissionDeniedError("真删操作仅 SUPER ADMIN 可执行")
    await svc.delete_series(series_id, hard=hard)
    return ok(data=None, message="系列已彻底删除" if hard else "系列已下架")


# ═══════════════════════════════════════════
# 班次 Cohort CRUD（5 端点）
# ═══════════════════════════════════════════

@router.get("/series/{series_id}/cohorts", summary="管理端·班次列表（按系列）")
async def admin_list_cohorts(series_id: int, me: CurrentUser = Depends(get_current_user)):
    items = await svc.list_cohorts_by_series(series_id)
    return ok(data=[i.model_dump(mode="json") for i in items])


@router.get("/cohorts/{cohort_id}", summary="管理端·班次详情")
async def admin_get_cohort(cohort_id: int, me: CurrentUser = Depends(get_current_user)):
    detail = await svc.get_cohort_admin(cohort_id)
    return ok(data=detail.model_dump(mode="json"))


@router.post("/cohorts", summary="管理端·创建班次")
async def admin_create_cohort(payload: CohortCreateAdmin, me: CurrentUser = Depends(get_current_user)):
    result = await svc.create_cohort(payload)
    return ok(data=result.model_dump(mode="json"))


@router.patch("/cohorts/{cohort_id}", summary="管理端·更新班次")
async def admin_update_cohort(cohort_id: int, payload: CohortUpdateAdmin,
                               me: CurrentUser = Depends(get_current_user)):
    result = await svc.update_cohort(cohort_id, payload)
    return ok(data=result.model_dump(mode="json"))


@router.delete("/cohorts/{cohort_id}", summary="管理端·软删班次（yn=0）")
async def admin_delete_cohort(cohort_id: int, me: CurrentUser = Depends(get_current_user)):
    await svc.delete_cohort(cohort_id)
    return ok(data=None, message="班次已删除")


# ═══════════════════════════════════════════
# 模块 Module CRUD（5 端点）
# ═══════════════════════════════════════════

@router.get("/cohorts/{cohort_id}/modules", summary="管理端·模块列表（按班次）")
async def admin_list_modules(cohort_id: int, me: CurrentUser = Depends(get_current_user)):
    items = await svc.list_modules_by_cohort(cohort_id)
    return ok(data=[i.model_dump(mode="json") for i in items])


@router.get("/modules/{module_id}", summary="管理端·模块详情")
async def admin_get_module(module_id: int, me: CurrentUser = Depends(get_current_user)):
    detail = await svc.get_module_admin(module_id)
    return ok(data=detail.model_dump(mode="json"))


@router.post("/modules", summary="管理端·创建模块")
async def admin_create_module(payload: ModuleCreateAdmin, me: CurrentUser = Depends(get_current_user)):
    result = await svc.create_module(payload)
    return ok(data=result.model_dump(mode="json"))


@router.patch("/modules/{module_id}", summary="管理端·更新模块")
async def admin_update_module(module_id: int, payload: ModuleUpdateAdmin,
                               me: CurrentUser = Depends(get_current_user)):
    result = await svc.update_module(module_id, payload)
    return ok(data=result.model_dump(mode="json"))


@router.delete("/modules/{module_id}", summary="管理端·软删模块（yn=0）")
async def admin_delete_module(module_id: int, me: CurrentUser = Depends(get_current_user)):
    await svc.delete_module(module_id)
    return ok(data=None, message="模块已删除")


# ═══════════════════════════════════════════
# 课次 Session CRUD（5 端点）
# ═══════════════════════════════════════════

@router.get("/cohorts/{cohort_id}/sessions", summary="管理端·课次列表（按班次，task12-fix 批判②）")
async def admin_list_sessions_by_cohort(cohort_id: int, me: CurrentUser = Depends(get_current_user)):
    items = await svc.list_sessions_by_cohort(cohort_id)
    return ok(data=[i.model_dump(mode="json") for i in items])


@router.get("/modules/{module_id}/sessions", summary="管理端·课次列表（按模块）")
async def admin_list_sessions(module_id: int, me: CurrentUser = Depends(get_current_user)):
    items = await svc.list_sessions_by_module(module_id)
    return ok(data=[i.model_dump(mode="json") for i in items])


@router.get("/sessions/{session_id}", summary="管理端·课次详情")
async def admin_get_session(session_id: int, me: CurrentUser = Depends(get_current_user)):
    detail = await svc.get_session_admin(session_id)
    return ok(data=detail.model_dump(mode="json"))


@router.post("/sessions", summary="管理端·创建课次")
async def admin_create_session(payload: SessionCreateAdmin, me: CurrentUser = Depends(get_current_user)):
    result = await svc.create_session(payload)
    return ok(data=result.model_dump(mode="json"))


@router.patch("/sessions/{session_id}", summary="管理端·更新课次")
async def admin_update_session(session_id: int, payload: SessionUpdateAdmin,
                                me: CurrentUser = Depends(get_current_user)):
    result = await svc.update_session(session_id, payload)
    return ok(data=result.model_dump(mode="json"))


@router.delete("/sessions/{session_id}", summary="管理端·软删课次（yn=0）")
async def admin_delete_session(session_id: int, me: CurrentUser = Depends(get_current_user)):
    await svc.delete_session(session_id)
    return ok(data=None, message="课次已删除")


# ═══════════════════════════════════════════
# 视频 + 分片上传（占位，task13 完整实现）
# ═══════════════════════════════════════════

@router.post("/videos/init-chunked", summary="管理端·分片上传 init（占位）")
async def admin_init_chunked_upload(
    session_id: int, file_name: str, file_size: int, chunk_count: int,
    me: CurrentUser = Depends(get_current_user),
):
    result = await svc.init_chunked_upload(session_id, file_name, file_size, chunk_count)
    return ok(data=result)


@router.post("/videos/finalize-chunked", summary="管理端·分片上传 finalize（占位）")
async def admin_finalize_chunked_upload(
    upload_id: str, me: CurrentUser = Depends(get_current_user),
):
    result = await svc.finalize_chunked_upload(upload_id)
    return ok(data=result)


@router.post("/videos/bind-session", summary="管理端·绑定视频到课次（占位）")
async def admin_bind_video(
    session_id: int, video_id: int, sort_no: int = 0,
    me: CurrentUser = Depends(get_current_user),
):
    result = await svc.bind_video_to_session(session_id, video_id, sort_no)
    return ok(data=result)


@router.get("/videos/{video_id}/transcode-status", summary="管理端·转码状态轮询（占位）")
async def admin_get_transcode_status(
    video_id: int, me: CurrentUser = Depends(get_current_user),
):
    result = await svc.get_transcode_status(video_id)
    return ok(data=result)