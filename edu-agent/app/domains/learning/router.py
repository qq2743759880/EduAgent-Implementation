# -*- coding: utf-8 -*-
"""study/learning 域（task21 契约⑪ task21 段）路由。

端点（对齐前端 study.ts，供 /learning 播放页 / task48）：
- GET  /api/study/courses/{series_id}/access   访问鉴权（access_scope 矩阵，enrolled_only 需报名）
- GET  /api/study/courses/{series_id}/outline  学习大纲（模块/课次/进度 + 资源过滤）
- POST /api/study/sessions/{session_id}/complete 课次完成态
- GET  /api/study/sessions/{session_id}        课次详情（session_asset 过滤 + transcode）

响应壳沿用契约① ok()；失败 AppException → 全局 handler（403 用业务码 403xx）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.resp import ok
from app.domains.learning import service as svc

router = APIRouter(prefix="/api/study", tags=["study · 学习"])  # noqa: F401


@router.get("/courses/{series_id}/access", summary="班次访问鉴权")
async def study_access(
    series_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_study_access(user.user_id, series_id)
    return ok(data=data.model_dump(mode="json"))


@router.get("/courses/{series_id}/outline", summary="学习大纲")
async def study_outline(
    series_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_study_outline(user.user_id, series_id)
    return ok(data=data.model_dump(mode="json"))


@router.post("/sessions/{session_id}/complete", summary="课次完成态")
async def session_complete(
    session_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.complete_session(user.user_id, session_id)
    return ok(data=data.model_dump(mode="json"))


@router.get("/sessions/{session_id}", summary="课次详情（资源过滤 + transcode）")
async def session_detail(
    session_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_session_detail(user.user_id, session_id)
    return ok(data=data.model_dump(mode="json"))