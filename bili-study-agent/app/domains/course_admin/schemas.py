"""管理端课程域 CRUD 请求/响应 Pydantic 模型（task12）。

层级语义（与 task11 C 端一致）：
    series（软删 → sale_status=off_sale，表无 yn 列，状态机控制）
      └── series_cohort（yn=0 软删——该表有 yn 列）
            └── series_cohort_course（物理 DELETE，表无 yn 列，stage_no 唯一 per cohort_id）
                  └── series_cohort_session（物理 DELETE，表无 yn 列，session_no 唯一 per module，teaching_status 为教学状态）
                        └── session_asset（物理 DELETE，表无 yn 列）→ session_video（物理 DELETE，transcode/review 状态机）→ session_video_chapter（物理 DELETE）

全部 CRUD 响应壳使用契约①（成功 code=0 int / 失败 code=<字符串>）。
409xx 错误码适用场景：系列编码重复/班次编码重复/模块同班次阶段号重复/课次同模块课次号重复。
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════
# Series（课程系列）
# ═══════════════════════════════════════════
class SeriesCreateAdmin(BaseModel):
    institution_id: int
    delivery_mode: str = Field(..., pattern=r"^(online_live|online_recorded|offline_face_to_face)$")
    series_code: str = Field(..., min_length=1, max_length=64)
    series_name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    cover_url: Optional[str] = None
    target_learner_identity_codes: Optional[List[str]] = None
    target_learning_goal_codes: Optional[List[str]] = None
    target_grade_codes: Optional[List[str]] = None
    sale_status: str = Field("draft", pattern=r"^(draft|on_sale|off_sale)$")
    created_by: int


class SeriesUpdateAdmin(BaseModel):
    delivery_mode: Optional[str] = Field(None, pattern=r"^(online_live|online_recorded|offline_face_to_face)$")
    series_name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    cover_url: Optional[str] = None
    target_learner_identity_codes: Optional[List[str]] = None
    target_learning_goal_codes: Optional[List[str]] = None
    target_grade_codes: Optional[List[str]] = None
    sale_status: Optional[str] = Field(None, pattern=r"^(draft|on_sale|off_sale)$")


class SeriesResponseAdmin(BaseModel):
    id: int
    institution_id: int
    delivery_mode: str
    series_code: str
    series_name: str
    description: Optional[str] = None
    cover_url: Optional[str] = None
    target_learner_identity_codes: Optional[List[str]] = None
    target_learning_goal_codes: Optional[List[str]] = None
    target_grade_codes: Optional[List[str]] = None
    sale_status: str
    created_by: int
    created_at: datetime
    updated_at: datetime


class SeriesListDataAdmin(BaseModel):
    items: List[SeriesResponseAdmin]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# Cohort（班次）
# ═══════════════════════════════════════════
class CohortCreateAdmin(BaseModel):
    institution_id: int
    series_id: int
    campus_id: Optional[int] = None
    head_teacher_id: int
    cohort_code: str = Field(..., min_length=1, max_length=64)
    cohort_name: str = Field(..., min_length=1, max_length=128)
    sale_price: Decimal = Field(..., ge=0)
    max_student_count: int = Field(..., ge=1)
    current_student_count: int = Field(0, ge=0)
    start_date: date
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class CohortUpdateAdmin(BaseModel):
    campus_id: Optional[int] = None
    head_teacher_id: Optional[int] = None
    cohort_name: Optional[str] = Field(None, min_length=1, max_length=128)
    sale_price: Optional[Decimal] = Field(None, ge=0)
    max_student_count: Optional[int] = Field(None, ge=1)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class CohortResponseAdmin(BaseModel):
    id: int
    institution_id: int
    series_id: int
    campus_id: Optional[int] = None
    head_teacher_id: int
    cohort_code: str
    cohort_name: str
    sale_price: Decimal
    max_student_count: int
    current_student_count: int
    yn: int
    start_date: date
    end_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime


class CohortListDataAdmin(BaseModel):
    items: List[CohortResponseAdmin]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# Module（模块 = series_cohort_course）
# ═══════════════════════════════════════════
class ModuleCreateAdmin(BaseModel):
    cohort_id: int
    module_code: str = Field(..., min_length=1, max_length=64)
    module_name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    lesson_count: int = Field(..., ge=1)
    total_hours: Decimal = Field(..., ge=0)
    stage_no: int = Field(..., ge=1)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class ModuleUpdateAdmin(BaseModel):
    module_name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    lesson_count: Optional[int] = Field(None, ge=1)
    total_hours: Optional[Decimal] = Field(None, ge=0)
    stage_no: Optional[int] = Field(None, ge=1)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ModuleResponseAdmin(BaseModel):
    id: int
    cohort_id: int
    module_code: str
    module_name: str
    description: Optional[str] = None
    lesson_count: int
    total_hours: Decimal
    stage_no: int
    start_date: date
    end_date: date
    created_at: datetime
    updated_at: datetime


class ModuleListDataAdmin(BaseModel):
    items: List[ModuleResponseAdmin]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# Session（课次 = series_cohort_session）
# ═══════════════════════════════════════════
class SessionCreateAdmin(BaseModel):
    series_cohort_course_id: int
    room_id: Optional[int] = None
    session_no: int = Field(..., ge=1)
    session_title: str = Field(..., min_length=1, max_length=128)
    teaching_status: str = Field("scheduled", pattern=r"^(scheduled|in_progress|completed|cancelled)$")
    checkin_required: int = Field(0, ge=0, le=1)
    teaching_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None


class SessionUpdateAdmin(BaseModel):
    room_id: Optional[int] = None
    session_title: Optional[str] = Field(None, min_length=1, max_length=128)
    teaching_status: Optional[str] = Field(None, pattern=r"^(scheduled|in_progress|completed|cancelled)$")
    checkin_required: Optional[int] = Field(None, ge=0, le=1)
    teaching_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None


class SessionResponseAdmin(BaseModel):
    id: int
    series_cohort_course_id: int
    room_id: Optional[int] = None
    session_no: int
    session_title: str
    teaching_status: str
    checkin_required: int
    teaching_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    created_at: datetime
    updated_at: datetime


class SessionListDataAdmin(BaseModel):
    items: List[SessionResponseAdmin]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# Session Asset（课次资源基表）
# ═══════════════════════════════════════════
class AssetCreateAdmin(BaseModel):
    session_id: int
    asset_code: str = Field(..., min_length=1, max_length=64)
    asset_name: str = Field(..., min_length=1, max_length=128)
    file_type: str = Field(..., max_length=32)
    material_category: str = Field(..., pattern=r"^(video|handout|exercise|reference|image)$")
    sort_no: int = Field(0, ge=0)
    access_scope: str = Field("enrolled_only", pattern=r"^(public|trial|enrolled_only|internal_only)$")
    file_url: str = Field(..., max_length=255)
    file_size: Optional[int] = Field(None, ge=0)
    uploader_user_id: int


class AssetResponseAdmin(BaseModel):
    id: int
    session_id: int
    asset_code: str
    asset_name: str
    file_type: str
    material_category: str
    sort_no: int
    access_scope: str
    file_url: str
    file_size: Optional[int] = None
    uploader_user_id: int
    created_at: datetime
    updated_at: datetime


class AssetListDataAdmin(BaseModel):
    items: List[AssetResponseAdmin]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# Session Video（课次视频）
# ═══════════════════════════════════════════
class VideoCreateAdmin(BaseModel):
    asset_id: int
    video_code: str = Field(..., min_length=1, max_length=64)
    video_title: str = Field(..., min_length=1, max_length=128)
    cover_url: Optional[str] = None
    duration_seconds: int = Field(0, ge=0)
    resolution_label: Optional[str] = None
    bitrate_kbps: int = Field(0, ge=0)
    transcode_status: str = Field("pending", pattern=r"^(pending|in_progress|completed|failed)$")
    review_status: str = Field("pending", pattern=r"^(pending|approved|rejected)$")


class VideoUpdateAdmin(BaseModel):
    video_title: Optional[str] = Field(None, min_length=1, max_length=128)
    cover_url: Optional[str] = None
    duration_seconds: Optional[int] = Field(None, ge=0)
    resolution_label: Optional[str] = None
    bitrate_kbps: Optional[int] = Field(None, ge=0)
    transcode_status: Optional[str] = Field(None, pattern=r"^(pending|in_progress|completed|failed)$")
    review_status: Optional[str] = Field(None, pattern=r"^(pending|approved|rejected)$")


class VideoResponseAdmin(BaseModel):
    id: int
    asset_id: int
    video_code: str
    video_title: str
    cover_url: Optional[str] = None
    duration_seconds: int
    resolution_label: Optional[str] = None
    bitrate_kbps: int
    transcode_status: str
    review_status: str
    created_at: datetime
    updated_at: datetime


class VideoListDataAdmin(BaseModel):
    items: List[VideoResponseAdmin]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# Video Chapter（视频章节）
# ═══════════════════════════════════════════
class ChapterCreateAdmin(BaseModel):
    video_id: int
    chapter_no: int = Field(..., ge=1)
    chapter_title: str = Field(..., min_length=1, max_length=128)
    start_second: int = Field(..., ge=0)
    end_second: int = Field(..., ge=1)

    @model_validator(mode="after")
    def check_seconds(self):
        if self.start_second >= self.end_second:
            raise ValueError("start_second 必须小于 end_second")
        return self


class ChapterUpdateAdmin(BaseModel):
    chapter_title: Optional[str] = Field(None, min_length=1, max_length=128)
    start_second: Optional[int] = Field(None, ge=0)
    end_second: Optional[int] = Field(None, ge=1)


class ChapterResponseAdmin(BaseModel):
    id: int
    video_id: int
    chapter_no: int
    chapter_title: str
    start_second: int
    end_second: int
    created_at: datetime
    updated_at: datetime


class ChapterListDataAdmin(BaseModel):
    items: List[ChapterResponseAdmin]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# 视频分片上传
# ═══════════════════════════════════════════
class ChunkedUploadInitRequest(BaseModel):
    session_id: int
    file_name: str = Field(..., min_length=1, max_length=255)
    file_size: int = Field(..., ge=1)
    chunk_count: int = Field(..., ge=1)


class ChunkedUploadInitResponse(BaseModel):
    upload_id: str = Field(..., description="分片上传唯一 ID")
    chunk_size: int = Field(..., description="每分片大小（字节），最后一片可能更小")
    upload_urls: List[str] = Field(default_factory=list, description="各分片预签名 PUT URL（MinIO 可用时）")
    strategy: str = Field("chunked", description="chunked / local_fallback")


class ChunkedUploadFinalizeRequest(BaseModel):
    upload_id: str


class ChunkedUploadFinalizeResponse(BaseModel):
    upload_id: str
    asset_id: int
    video_id: int
    transcode_status: str = Field("pending")


class BindVideoRequest(BaseModel):
    session_id: int
    video_id: int
    sort_no: int = Field(0, ge=0)


class TranscodeStatusResponse(BaseModel):
    video_id: int
    transcode_status: str
    review_status: str