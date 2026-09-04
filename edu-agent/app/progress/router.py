# -*- coding: utf-8 -*-
"""P3 学习进度追踪 —— router（全部是 C 端登录态可用的 API）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.resp import ok
from app.progress.schemas import (
    CourseProgressOut, DashboardOut, ExamSubmitIn, HomeworkSubmitIn,
    SubmitOut, VideoTickBatchIn, VideoTickBatchOut,
)
from app.progress import service

router = APIRouter(prefix="/api/progress", tags=["P3 学习进度"])


# ========== 1. 视频播放打点 ==========

@router.post("/video/tick-batch", summary="批量视频播放打点")
async def video_tick_batch(
    payload: VideoTickBatchIn,
    current_user: CurrentUser = Depends(get_current_user),
):
    """客户端每 30 秒批量上报一次播放事件。"""
    return ok(await service.record_video_ticks(current_user.user_id, payload))


# ========== 2. 作业 / 考试提交 ==========

@router.post("/homework/submit", summary="提交课次作业")
async def homework_submit(
    req: HomeworkSubmitIn,
    current_user: CurrentUser = Depends(get_current_user),
):
    """提交课次作业（需 homework_id 外键）。"""
    return ok(await service.submit_homework(current_user.user_id, req))


@router.post("/exam/submit", summary="提交考试答卷")
async def exam_submit(
    req: ExamSubmitIn,
    current_user: CurrentUser = Depends(get_current_user),
):
    """提交考试答卷（需 exam_id 外键）。"""
    return ok(await service.submit_exam(current_user.user_id, req))


# ========== 3. 统计看板 ==========

@router.get("/dashboard", summary="个人学习看板")
async def dashboard(
    days: int = Query(7, ge=1, le=365, description="最近多少天明细"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """累计天数/时长、最近连续天数 + 最近 N 天明细。"""
    return ok(await service.get_dashboard(current_user.user_id, days=days))


# ========== 4. 课程进度 ==========

@router.get("/courses", summary="我的课程进度")
async def course_progress(
    series_id: int | None = Query(None, ge=1, description="指定系列 ID；为空则返回全部系列前 5 个"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """按系列→模块→课次三层结构返回完成率。"""
    return ok(await service.get_course_progress(current_user.user_id, series_id=series_id))