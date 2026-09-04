# -*- coding: utf-8 -*-
"""study/learning 域（task21 契约⑪ task21 段）schemas。

对齐前端 study.ts（task40 权威）+ /learning 播放页：
- GET  /api/study/courses/{series_id}/access   访问鉴权（access_scope 矩阵）
- GET  /api/study/courses/{series_id}/outline  学习大纲（模块/课次/进度 + 资源过滤）
- POST /api/study/sessions/{session_id}/complete 课次完成态
- GET  /api/study/sessions/{session_id}        课次详情（session_asset 按 material_category + access_scope 过滤 + transcode）
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AccessScope = Literal["public", "trial", "enrolled_only", "internal_only"]
MaterialCategory = Literal["video", "handout", "exercise", "reference", "image"]
TranscodeStatus = Literal["pending", "in_progress", "completed", "failed"]


class StudyAccessResult(BaseModel):
    """班次访问鉴权（StudyAccessResult）。"""
    series_id: int
    cohort_id: int | None = None
    accessible: bool
    reason: str | None = None


class StudySessionOutlineItem(BaseModel):
    """课次大纲项。"""
    session_id: int
    session_title: str
    session_no: int
    duration_minutes: int
    video_url: str | None = None
    watch_ratio: float = 0.0
    homework_done: bool = False
    transcode_status: TranscodeStatus | None = None


class StudyModuleOutlineItem(BaseModel):
    """模块大纲项。"""
    module_id: int
    module_title: str
    module_no: int
    overall_ratio: float = 0.0
    sessions: list[StudySessionOutlineItem] = []


class StudyOutline(BaseModel):
    """学习大纲（StudyOutline）。"""
    series_id: int
    series_title: str
    overall_ratio: float = 0.0
    total_sessions: int = 0
    completed_sessions: int = 0
    modules: list[StudyModuleOutlineItem] = []


class SessionCompleteResult(BaseModel):
    """课次完成态。"""
    session_id: int
    completed: bool


class StudyAssetItem(BaseModel):
    """课次资源（按 material_category + access_scope 过滤后可访问项）。"""
    asset_id: int
    asset_code: str
    asset_name: str
    material_category: MaterialCategory
    access_scope: AccessScope
    file_url: str
    file_size: int | None = None


class StudyVideoInfo(BaseModel):
    """课次视频（transcode 状态，status=completed 才给可播 url）。"""
    video_id: int
    video_code: str
    video_title: str
    duration_seconds: int
    cover_url: str | None = None
    transcode_status: TranscodeStatus
    review_status: str
    video_url: str | None = None          # 仅 transcode_status=completed 返回
    chapters: list[dict] = []


class StudySessionDetail(BaseModel):
    """课次详情（GWT③ session_asset 过滤 + GWT④ transcode）。"""
    session_id: int
    session_no: int
    session_title: str
    teaching_status: str
    teaching_date: datetime | None = None
    module_id: int | None = None
    module_name: str | None = None
    series_id: int | None = None
    assets: list[StudyAssetItem] = []
    video: StudyVideoInfo | None = None