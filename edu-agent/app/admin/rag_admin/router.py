"""
P7 路径 B：管理端 RAG 控制台路由（全部 require_role admin-only）。
API：
  GET    /api/admin/rag/collections                         知识库列表（含 Milvus 行计数快照）
  POST   /api/admin/rag/collections/rebuild                 重建索引（返回 job_id）
  GET    /api/admin/rag/presets                             参数预设列表
  POST   /api/admin/rag/presets                             新建预设（若 is_default=1 会把旧 default 置 0）
  GET    /api/admin/rag/audit-log                           审计日志分页（user_id/role/created_after 过滤）
  POST   /api/admin/rag/search                              管理员高级检索（跨租户全库 / tenant_ids / content_types / preset）
所有非 admin 请求 → 403；底层 Milvus/Neo4j 缺时返回空 docs + degraded_reason，不抛 500。
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.admin.rag_admin.schemas import (
    AdminSearchRequest,
    AdminSearchResponse,
    AuditLogPage,
    CollectionMeta,
    CollectionRebuildRequest,
    CollectionRebuildResponse,
    ParamPreset,
    ParamPresetCreate,
)
from app.admin.rag_admin.service import (
    admin_search,
    create_preset,
    list_audit_log,
    list_collections,
    list_presets,
    rebuild_collection,
)
from app.auth import CurrentUser, UserRole, require_role
from app.common.exceptions import AppException, NotFoundError, ValidationError


router = APIRouter(prefix="/api/admin/rag", tags=["P7-管理端RAG控制台"])

AdminOnly = Annotated[CurrentUser, Depends(require_role([UserRole.ADMIN]))]


def _translate(e: Exception) -> None:
    if isinstance(e, NotFoundError):
        raise HTTPException(
            status_code=getattr(e, "http_status", 404),
            detail={"code": "RAG_PRESET_NOT_FOUND" if "参数预设" in getattr(e, "message", "") else "NOT_FOUND", "message": getattr(e, "message", str(e))},
        )
    if isinstance(e, ValidationError):
        detail = getattr(e, "detail", None) or ""
        msg = getattr(e, "message", str(e))
        if "RAG_PRESET_" in f"{msg} {detail}":
            raise HTTPException(status_code=400, detail={"code": detail or "RAG_PRESET_INVALID", "message": msg})
        raise
    if isinstance(e, AppException):
        raise
    logger.exception(f"[rag_admin.router] 未处理异常：{e}")
    raise HTTPException(status_code=500, detail={"code": "RAG_ADMIN_INTERNAL_ERROR", "message": "管理端 RAG 服务暂不可用，请稍后重试"})


@router.get("/collections", response_model=list[CollectionMeta])
async def collections_list(user: AdminOnly):
    try:
        return await list_collections()
    except Exception as e:
        _translate(e)


@router.post("/collections/rebuild", response_model=CollectionRebuildResponse, status_code=status.HTTP_202_ACCEPTED)
async def collections_rebuild(body: CollectionRebuildRequest, user: AdminOnly):
    try:
        return await rebuild_collection(body, operator_user_id=int(user.user_id))
    except Exception as e:
        _translate(e)


@router.get("/presets", response_model=list[ParamPreset])
async def presets_list(user: AdminOnly):
    try:
        return await list_presets()
    except Exception as e:
        _translate(e)


@router.post("/presets", response_model=ParamPreset, status_code=status.HTTP_201_CREATED)
async def presets_create(body: ParamPresetCreate, user: AdminOnly):
    try:
        return await create_preset(body, operator_user_id=int(user.user_id))
    except Exception as e:
        _translate(e)


@router.get("/audit-log", response_model=AuditLogPage)
async def audit_log_list(
    user: AdminOnly,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user_id: Annotated[int | None, Query(description="按用户过滤（None=全部）")] = None,
    role: Annotated[str | None, Query(description="按发起角色过滤 student/admin/teacher/manager")] = None,
    created_after: Annotated[datetime | None, Query(description="只返回这个时间之后的审计记录（UTC/本地都可，FastAPI 自动解析 ISO）")] = None,
):
    try:
        return await list_audit_log(
            page=page, page_size=page_size,
            user_id=user_id, role=role, created_after=created_after,
        )
    except Exception as e:
        _translate(e)


@router.post("/search", response_model=AdminSearchResponse)
async def admin_search_endpoint(body: AdminSearchRequest, user: AdminOnly):
    try:
        return await admin_search(body)
    except Exception as e:
        _translate(e)
