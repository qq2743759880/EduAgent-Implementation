"""
P7 管理端控制台 - 课程管理 router。
全量 require_role([ADMIN]) 约束。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth import CurrentUser, UserRole, require_role
from app.admin.course_admin import service
from app.admin.course_admin.schemas import (
    BindVideoToSessionRequest,
    CohortAdminCreate,
    CohortAdminUpdate,
    MaterialRedirectResponse,
    ModuleAdminCreate,
    ModuleAdminUpdate,
    SeriesAdminCreate,
    SeriesAdminUpdate,
    SessionAdminCreate,
    SessionAdminUpdate,
    VideoAsset,
    VideoUploadFinalizeRequest,
    VideoUploadInitRequest,
    VideoUploadInitResponse,
)
from app.curriculum.schemas import (
    Cohort,
    Module,
    SeriesDetailResponse,
    SeriesListResponse,
    SeriesTreeResponse,
    Session,
)

router = APIRouter(
    prefix="/api/admin/courses",
    tags=["admin-course"],
    dependencies=[Depends(require_role([UserRole.ADMIN]))],
)


# ============================================================
# 1. 系列
# ============================================================
@router.get("/series", response_model=SeriesListResponse)
async def admin_list_series(
    subject_code: Optional[str] = None,
    level_code: Optional[str] = None,
    keyword: Optional[str] = None,
    yn: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return await service.list_series_admin(
        subject_code=subject_code,
        level_code=level_code,
        keyword=keyword,
        page=page,
        page_size=page_size,
        yn=yn,
    )


@router.get("/series/{series_id}", response_model=SeriesDetailResponse)
async def admin_get_series(series_id: int):
    return await service.get_series_admin(series_id)


@router.get("/series/{series_id}/tree", response_model=SeriesTreeResponse)
async def admin_get_series_tree(series_id: int):
    return await service.get_series_tree_admin(series_id)


@router.post("/series", response_model=dict)
async def admin_create_series(
    payload: SeriesAdminCreate,
    user: CurrentUser = Depends(require_role([UserRole.ADMIN])),
):
    pk = await service.create_series(payload, created_by=user.user_id)
    return {"id": pk, "series_code": payload.series_code}


@router.patch("/series/{series_id}", response_model=dict)
async def admin_update_series(series_id: int, payload: SeriesAdminUpdate):
    await service.update_series(series_id, payload)
    return {"updated": True, "id": series_id}


@router.post("/series/{series_id}/yn", response_model=dict)
async def admin_toggle_series_yn(series_id: int, yn: int = Query(..., ge=0, le=1)):
    await service.toggle_series_yn(series_id, yn)
    return {"updated": True, "id": series_id, "yn": yn}


# ============================================================
# 2. 班次
# ============================================================
@router.get("/cohorts", response_model=list[Cohort])
async def admin_list_cohorts(series_id: Optional[int] = None):
    return await service.list_cohorts_admin(series_id)


@router.post("/cohorts", response_model=dict)
async def admin_create_cohort(payload: CohortAdminCreate):
    pk = await service.create_cohort(payload)
    return {"id": pk, "cohort_code": payload.cohort_code}


@router.patch("/cohorts/{cohort_id}", response_model=dict)
async def admin_update_cohort(cohort_id: int, payload: CohortAdminUpdate):
    await service.update_cohort(cohort_id, payload)
    return {"updated": True, "id": cohort_id}


@router.delete("/cohorts/{cohort_id}", response_model=dict)
async def admin_delete_cohort(cohort_id: int):
    await service.delete_cohort(cohort_id)
    return {"deleted": True, "id": cohort_id}


# ============================================================
# 3. 模块
# ============================================================
@router.get("/modules", response_model=list[Module])
async def admin_list_modules(series_id: Optional[int] = None):
    return await service.list_modules_admin(series_id)


@router.post("/modules", response_model=dict)
async def admin_create_module(payload: ModuleAdminCreate):
    pk = await service.create_module(payload)
    return {"id": pk, "module_code": payload.module_code}


@router.patch("/modules/{module_id}", response_model=dict)
async def admin_update_module(module_id: int, payload: ModuleAdminUpdate):
    await service.update_module(module_id, payload)
    return {"updated": True, "id": module_id}


@router.delete("/modules/{module_id}", response_model=dict)
async def admin_delete_module(module_id: int):
    await service.delete_module(module_id)
    return {"deleted": True, "id": module_id}


# ============================================================
# 4. 课次
# ============================================================
@router.get("/sessions", response_model=list[Session])
async def admin_list_sessions(module_id: Optional[int] = None):
    return await service.list_sessions_admin(module_id)


@router.post("/sessions", response_model=dict)
async def admin_create_session(payload: SessionAdminCreate):
    pk = await service.create_session(payload)
    return {"id": pk, "session_title": payload.session_title}


@router.patch("/sessions/{session_id}", response_model=dict)
async def admin_update_session(session_id: int, payload: SessionAdminUpdate):
    await service.update_session(session_id, payload)
    return {"updated": True, "id": session_id}


@router.delete("/sessions/{session_id}", response_model=dict)
async def admin_delete_session(session_id: int):
    await service.delete_session(session_id)
    return {"deleted": True, "id": session_id}


# ============================================================
# 5. 视频资产（占位式上传）
# ============================================================
@router.post("/videos/upload/init", response_model=VideoUploadInitResponse)
async def admin_init_video_upload(
    req: VideoUploadInitRequest,
    user: CurrentUser = Depends(require_role([UserRole.ADMIN])),
):
    return await service.init_video_upload(req, created_by=user.user_id)


@router.post("/videos/upload/finalize", response_model=VideoAsset)
async def admin_finalize_video_upload(req: VideoUploadFinalizeRequest):
    return await service.finalize_video_upload(req)


@router.post("/videos/bind-session", response_model=VideoAsset)
async def admin_bind_video_to_session(req: BindVideoToSessionRequest):
    return await service.bind_video_to_session(req)


@router.get("/videos", response_model=dict)
async def admin_list_video_assets(
    session_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    total, items = await service.list_video_assets(session_id, status, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ============================================================
# 6. 课件上传（307 跳转 P1 知识库管道）
# ============================================================
@router.get("/materials/redirect-upload", response_model=MaterialRedirectResponse)
async def admin_redirect_material_upload():
    return await service.redirect_material_to_p1_upload()
