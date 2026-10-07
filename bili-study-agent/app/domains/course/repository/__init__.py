"""课程域 repository 四件套（task11）。

series_repo / cohort_repo / session_repo / video_repo
—— 全部参数化 SQL（%s），排序走白名单映射，禁止拼接用户输入。
"""
from app.domains.course.repository.series_repo import CategoryRepo, SeriesRepo
from app.domains.course.repository.cohort_repo import CohortRepo
from app.domains.course.repository.session_repo import ModuleRepo, SessionRepo
from app.domains.course.repository.video_repo import VideoRepo

__all__ = [
    "SeriesRepo", "CategoryRepo", "CohortRepo",
    "ModuleRepo", "SessionRepo", "VideoRepo",
]
