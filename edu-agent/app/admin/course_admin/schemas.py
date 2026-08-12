"""
P7 管理端控制台 - 课程管理 schemas。
复用到 curriculum_* 表结构 + admin_course_video_asset 表。
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.curriculum.schemas import LevelCode, SaleStatus, SubjectCode, TeachingStatus


# ============================================================
# 课程 CRUD：系列 / 班次 / 模块 / 课次
# ============================================================
class SeriesAdminCreate(BaseModel):
    series_code: str = Field(..., min_length=2, max_length=64)
    series_name: str = Field(..., min_length=1, max_length=128)
    subject_code: SubjectCode
    level_code: LevelCode
    level_name: str = Field(..., max_length=32)
    description: Optional[str] = None
    cover_url: Optional[str] = None
    target_hours: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    sale_status: SaleStatus = SaleStatus.ON_SALE
    sort_no: int = 0


class SeriesAdminUpdate(BaseModel):
    series_name: Optional[str] = Field(default=None, max_length=128)
    subject_code: Optional[SubjectCode] = None
    level_code: Optional[LevelCode] = None
    level_name: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = None
    cover_url: Optional[str] = None
    target_hours: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    sale_status: Optional[SaleStatus] = None
    sort_no: Optional[int] = None


class CohortAdminCreate(BaseModel):
    series_id: int
    cohort_code: str = Field(..., max_length=64)
    cohort_name: str = Field(..., max_length=128)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    max_student_count: int = Field(default=200, ge=1)
    sale_price: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    yn: Literal[0, 1] = 1


class CohortAdminUpdate(BaseModel):
    series_id: Optional[int] = None
    cohort_name: Optional[str] = Field(default=None, max_length=128)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    max_student_count: Optional[int] = None
    current_student_count: Optional[int] = None
    sale_price: Optional[Decimal] = None
    yn: Optional[Literal[0, 1]] = None


class ModuleAdminCreate(BaseModel):
    series_id: int
    module_code: str = Field(..., max_length=64)
    module_name: str = Field(..., max_length=128)
    stage_no: int = Field(..., ge=1)
    description: Optional[str] = None
    lesson_count: int = Field(default=0, ge=0)
    total_hours: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)


class ModuleAdminUpdate(BaseModel):
    series_id: Optional[int] = None
    module_name: Optional[str] = Field(default=None, max_length=128)
    stage_no: Optional[int] = None
    description: Optional[str] = None
    lesson_count: Optional[int] = None
    total_hours: Optional[Decimal] = None


class SessionAdminCreate(BaseModel):
    module_id: int
    session_no: int = Field(..., ge=1)
    session_title: str = Field(..., max_length=128)
    description: Optional[str] = None
    teaching_status: TeachingStatus = TeachingStatus.SCHEDULED
    teaching_date: Optional[date] = None
    duration_minutes: int = Field(default=45, ge=1)
    video_url: Optional[str] = None


class SessionAdminUpdate(BaseModel):
    module_id: Optional[int] = None
    session_no: Optional[int] = None
    session_title: Optional[str] = None
    description: Optional[str] = None
    teaching_status: Optional[TeachingStatus] = None
    teaching_date: Optional[date] = None
    duration_minutes: Optional[int] = None
    video_url: Optional[str] = None


# ============================================================
# 视频资产
# ============================================================
class QuestionOption(BaseModel):
    """占位：避免 QuestionOption 拼写差异（题库里真正定义，这里只是复用时友好导入）。"""
    label: str
    content: str


class VideoUploadInitRequest(BaseModel):
    origin_file_name: str = Field(..., max_length=255)
    file_size: int = Field(default=0, ge=0)
    content_hash: Optional[str] = Field(default=None, max_length=64)
    duration_seconds: int = Field(default=0, ge=0)
    asset_title: Optional[str] = Field(default=None, max_length=128)
    bind_session_id: Optional[int] = None


class VideoUploadInitResponse(BaseModel):
    """
    占位式 MinIO：不真写对象存储。
    - upload_type: "direct_form_post"（真实：预签名表单 POST）
    - upload_url: "/api/admin/courses/videos/_dev_direct_put"（打靶可用：用 Finalize 接口跳过直传）
    - form_fields: {"key": object_key, "Content-Type": "video/mp4", ...}
    - transcode_status_tip: "当前占位：无需 ffmpeg，执行 Finalize 即置 ready"
    """
    asset_id: str
    upload_type: str
    upload_url: str
    form_fields: dict[str, Any]
    transcode_status_tip: str
    expires_at: datetime
    bind_session_id: Optional[int]


class VideoUploadFinalizeRequest(BaseModel):
    asset_id: str
    object_key: Optional[str] = Field(default=None, max_length=255)
    transcode_error: Optional[str] = Field(default=None, max_length=255)
    play_720_url: Optional[str] = Field(default=None, max_length=255)
    play_1080_url: Optional[str] = Field(default=None, max_length=255)
    final_duration_seconds: int = Field(default=0, ge=0)


class VideoAsset(BaseModel):
    id: int
    asset_id: str
    session_id: Optional[int]
    asset_title: str
    origin_file_name: str
    object_key: Optional[str]
    bucket_name: Optional[str]
    file_size: int
    duration_seconds: int
    transcode_status: str
    transcode_message: Optional[str]
    play_720_url: Optional[str]
    play_1080_url: Optional[str]
    content_hash: Optional[str]
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime


class BindVideoToSessionRequest(BaseModel):
    asset_id: str
    session_id: int = Field(..., ge=1)


class MaterialRedirectResponse(BaseModel):
    """课件 PDF/PPT/DOCX 走 P1 知识库上传管道（返回上传链接提示，由前端直接请求 P1 接口）。"""
    redirect_endpoint: str
    method: str
    auth_header_required: bool
    supported_content_types: list[str]
    tip: str
