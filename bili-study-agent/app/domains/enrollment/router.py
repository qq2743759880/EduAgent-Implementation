# -*- coding: utf-8 -*-
"""enrollment 域（task20 契约⑪ 前段，只读）路由。

端点（对齐前端 enrollments.ts /me/cohorts + task20 4 端点）：
- GET  /api/enrollments/me/cohorts?status=&series_id=    我的班次列表（进度聚合，EnrolledCohort[]）
- GET  /api/enrollments/me/cohorts/{cohort_id}           报名详情（状态 + 进度）
- GET  /api/enrollments/me/cohorts/{cohort_id}/progress  进度快照（模块/课次明细）
- GET  /api/enrollments/me/cohorts/{cohort_id}/status    报名状态查询

响应壳沿用契约① ok()；失败 AppException → 全局 handler。满班并发由下单路径（task17）承载。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.resp import ok
from app.domains.enrollment import service as svc

router = APIRouter(prefix="/api/enrollments", tags=["enrollment · 报名"])  # noqa: F401

_ENROLL_STATUSES = ("active", "completed", "cancelled", "refunded")


@router.get("/me/cohorts", summary="我的班次（状态过滤 + 进度聚合）")
async def list_my_cohorts(
    status: Optional[str] = Query(None, description=f"报名状态过滤：{'/'.join(_ENROLL_STATUSES)}"),
    series_id: Optional[int] = Query(None, ge=1),
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.list_my_enrollments(user.user_id, enroll_status=status, series_id=series_id)
    return ok(data=[d.model_dump(mode="json") for d in data])


@router.get("/me/cohorts/{cohort_id}", summary="报名详情（状态 + 进度）")
async def get_enrollment_detail(
    cohort_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_enrollment_detail(user.user_id, cohort_id)
    return ok(data=data.model_dump(mode="json"))


@router.get("/me/cohorts/{cohort_id}/progress", summary="进度快照（模块/课次明细）")
async def get_progress_snapshot(
    cohort_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_progress_snapshot(user.user_id, cohort_id)
    return ok(data=data.model_dump(mode="json"))


@router.get("/me/cohorts/{cohort_id}/status", summary="报名状态查询")
async def get_enrollment_status(
    cohort_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_enrollment_status(user.user_id, cohort_id)
    return ok(data=data)