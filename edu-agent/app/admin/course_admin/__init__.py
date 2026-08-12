"""
P7 管理端控制台 - 课程管理 admin/course_admin 包。
"""
from __future__ import annotations

from app.admin.course_admin.schemas import (
    BindVideoToSessionRequest,
    CohortAdminCreate,
    CohortAdminUpdate,
    MaterialRedirectResponse,
    ModuleAdminCreate,
    ModuleAdminUpdate,
    QuestionOption,
    SeriesAdminCreate,
    SeriesAdminUpdate,
    SessionAdminCreate,
    SessionAdminUpdate,
    VideoAsset,
    VideoUploadFinalizeRequest,
    VideoUploadInitRequest,
    VideoUploadInitResponse,
)

__all__ = [
    "BindVideoToSessionRequest",
    "CohortAdminCreate",
    "CohortAdminUpdate",
    "MaterialRedirectResponse",
    "ModuleAdminCreate",
    "ModuleAdminUpdate",
    "QuestionOption",
    "SeriesAdminCreate",
    "SeriesAdminUpdate",
    "SessionAdminCreate",
    "SessionAdminUpdate",
    "VideoAsset",
    "VideoUploadFinalizeRequest",
    "VideoUploadInitRequest",
    "VideoUploadInitResponse",
]
