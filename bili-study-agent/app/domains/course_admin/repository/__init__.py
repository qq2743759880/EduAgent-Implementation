"""course_admin 仓储层（6 Repo）。"""

from app.domains.course_admin.repository.series_repo import SeriesAdminRepo
from app.domains.course_admin.repository.cohort_repo import CohortAdminRepo
from app.domains.course_admin.repository.module_repo import ModuleAdminRepo
from app.domains.course_admin.repository.session_repo import SessionAdminRepo
from app.domains.course_admin.repository.asset_repo import AssetAdminRepo
from app.domains.course_admin.repository.video_repo import (
    ChapterAdminRepo,
    VideoAdminRepo,
)

__all__ = [
    "SeriesAdminRepo",
    "CohortAdminRepo",
    "ModuleAdminRepo",
    "SessionAdminRepo",
    "AssetAdminRepo",
    "VideoAdminRepo",
    "ChapterAdminRepo",
]