# -*- coding: utf-8 -*-
"""P3 学习进度追踪 —— router（全部是 C 端登录态可用的 API）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.progress.schemas import (
    CourseProgressOut, DashboardOut, ExamSubmitIn, HomeworkSubmitIn,
    SubmitOut, VideoTickBatchIn, VideoTickBatchOut,
)
from app.progress import service

router = APIRouter(prefix="/api/progress", tags=["P3 学习进度"])


# ========== 1. 视频播放打点 ==========

@router.post("/video/tick-batch", response_model=VideoTickBatchOut, summary="批量视频播放打点")
async def video_tick_batch(
    payload: VideoTickBatchIn,
    current_user: CurrentUser = Depends(get_current_user),
) -> VideoTickBatchOut:
    """客户端每 30 秒批量上报一次播放事件。"""
    return await service.record_video_ticks(current_user.user_id, payload)


# ========== 2. 作业 / 考试提交 ==========

@router.post("/homework/submit", response_model=SubmitOut, summary="提交课次作业")
async def homework_submit(
    req: HomeworkSubmitIn,
    current_user: CurrentUser = Depends(get_current_user),
) -> SubmitOut:
    """每课次一次作业（homework_id = session_id），提交后客观题自动批改。"""
    return await service.submit_homework(current_user.user_id, req)


@router.post("/exam/submit", response_model=SubmitOut, summary="提交考试答卷")
async def exam_submit(
    req: ExamSubmitIn,
    current_user: CurrentUser = Depends(get_current_user),
) -> SubmitOut:
    """试卷来自 admin_exam_paper（P7 管理端组卷）。"""
    return await service.submit_exam(current_user.user_id, req)


# ========== 3. 统计看板 ==========

@router.get("/dashboard", response_model=DashboardOut, summary="个人学习看板")
async def dashboard(
    days: int = Query(7, ge=1, le=365, description="最近多少天明细"),
    current_user: CurrentUser = Depends(get_current_user),
) -> DashboardOut:
    """累计天数/时长、正确率、最近连续天数 + 最近 N 天明细。"""
    return await service.get_dashboard(current_user.user_id, days=days)


# ========== 4. 课程进度 ==========

@router.get("/courses", response_model=list[CourseProgressOut], summary="我的课程进度")
async def course_progress(
    series_id: int | None = Query(None, ge=1, description="指定系列 ID；为空则返回全部系列前 5 个"),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[CourseProgressOut]:
    """按系列→模块→课次三层结构返回完成率。"""
    return await service.get_course_progress(current_user.user_id, series_id=series_id)
