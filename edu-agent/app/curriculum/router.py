"""
分级课程 API 路由（P0-P 阶段只实现浏览/搜索/详情，匿名即可访问）。

后续 P7 管理端在同路由下加 POST/PUT/DELETE + require_role([MANAGER, ADMIN]) 即可。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.curriculum.schemas import (
    LevelCode, SeriesDetailResponse, SeriesListResponse,
    SeriesTreeResponse, SubjectCode,
)
from app.curriculum import service as svc


router = APIRouter(
    prefix="/api/curriculum",
    tags=["curriculum · 分级课程"],
)


# ============================================================
# 1. 系列列表（浏览/搜索主入口）
#    - 匿名可访问（不挂 Depends）
#    - 支持三条件过滤：学科 / 分级 / 关键词（名字+简介+等级名模糊）
# ============================================================
@router.get("/series", response_model=SeriesListResponse, summary="系列列表（支持学科/分级/关键词）")
async def series_list(
    subject_code: Optional[SubjectCode] = Query(None, description="学科：english/programming/math/physics/chemistry"),
    level_code: Optional[LevelCode] = Query(None, description="难度：L1入门 / L2基础 / L3进阶 / L4高级 / L5专家"),
    keyword: Optional[str] = Query(None, description="模糊搜索：匹配系列名称 / 简介 / 等级名称", min_length=1, max_length=64),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，1~100"),
):
    return await svc.list_series(
        subject_code=subject_code,
        level_code=level_code,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


# ============================================================
# 2. 系列基础详情（只有系列主表字段）
# ============================================================
@router.get("/series/{series_id}", response_model=SeriesDetailResponse, summary="系列详情（主表字段+班次+模块）")
async def series_detail(series_id: int):
    series = await svc.get_series(series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="系列不存在")
    cohorts = await svc.list_cohorts(series_id)
    modules = await svc.list_modules(series_id, include_sessions=False)
    return SeriesDetailResponse(series=series, cohorts=cohorts, modules=modules)


# ============================================================
# 3. 系列 → 班次列表（只返回班次，不含系列主字段）
# ============================================================
@router.get("/series/{series_id}/cohorts", summary="系列下全部班次")
async def series_cohorts(series_id: int):
    if not await svc.get_series(series_id):
        raise HTTPException(status_code=404, detail="系列不存在")
    return await svc.list_cohorts(series_id)


# ============================================================
# 4. 系列 → 模块列表（可返回课次）
# ============================================================
@router.get("/series/{series_id}/modules", summary="系列下全部模块（可选含课次）")
async def series_modules(series_id: int, include_sessions: bool = Query(False, description="是否返回模块下每节课")):
    if not await svc.get_series(series_id):
        raise HTTPException(status_code=404, detail="系列不存在")
    return await svc.list_modules(series_id, include_sessions=include_sessions)


# ============================================================
# 5. 完整树（前端详情页直接一次性拿，省 3 次请求）
# ============================================================
@router.get("/series/{series_id}/tree", response_model=SeriesTreeResponse, summary="完整嵌套树：系列+班次+模块→课次")
async def series_tree(series_id: int):
    tree = await svc.get_series_tree(series_id)
    if tree is None:
        raise HTTPException(status_code=404, detail="系列不存在")
    return tree
