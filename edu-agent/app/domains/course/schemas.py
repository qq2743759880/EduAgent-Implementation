"""
课程域 Pydantic 模型（task11 契约冻结② —— snake_case 全列）。

契约要点（前端 TraeWork task44/45/46 消费）：
- 全字段 snake_case，与 edu.sql 列名一一对应
- 列表分页统一外层 {total, page, page_size, items}（C-B 全站权威，无 page_meta 双轨，C2 已删）
- 价格：series 主表无价格，min_price 为班次最低价聚合（ sale_price 1999~5999 ）
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# 系列（series 表）
# ============================================================
class SeriesListItem(BaseModel):
    """系列列表项（含跨表聚合字段）。"""

    id: int
    institution_id: int
    delivery_mode: str = Field(..., description="交付模式：online_live/online_recorded/offline_face_to_face")
    series_code: str
    series_name: str
    description: Optional[str] = None
    cover_url: Optional[str] = None
    target_learner_identity_codes: Optional[List[str]] = None
    target_learning_goal_codes: Optional[List[str]] = None
    target_grade_codes: Optional[List[str]] = None
    sale_status: str = Field(..., description="售卖状态：on_sale")
    min_price: Optional[Decimal] = Field(None, description="最低班次价（聚合，展示价）")
    category_names: List[str] = Field(default_factory=list, description="分类名列表（聚合）")
    created_at: datetime
    updated_at: datetime


class SeriesListData(BaseModel):
    """系列列表分页 DTO（C-B：全站 {total,page,page_size,items} 权威，C2 已删 page_meta 双轨）。"""

    total: int
    page: int
    page_size: int
    items: List[SeriesListItem]


class CategoryBrief(BaseModel):
    id: int
    category_code: str
    category_name: str
    category_level: int


class SeriesDetail(BaseModel):
    """系列详情（全列 + 聚合）。"""

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
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    categories: List[CategoryBrief] = Field(default_factory=list)
    cohort_count: int = Field(0, description="在售班次数（聚合）")
    created_at: datetime
    updated_at: datetime


# ============================================================
# 班次（series_cohort 表）
# ============================================================
class Cohort(BaseModel):
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
    yn: int = Field(1, description="有效标记：1=在售 0=下架")
    start_date: date
    end_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime


class CohortListData(BaseModel):
    """班次列表分页 DTO（C-B：全站 {total,page,page_size,items} 权威，C2 已删 page_meta 双轨）。"""

    total: int
    page: int
    page_size: int
    items: List[Cohort]


# ============================================================
# 模块（series_cohort_course 表，挂 cohort）
# ============================================================
class Module(BaseModel):
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


# ============================================================
# 课次（series_cohort_session 表，挂模块）
# ============================================================
class SessionVideo(BaseModel):
    """课次视频（session_video 表，经 session_asset.material_category='video' 关联）。"""

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
    file_url: Optional[str] = Field(None, description="资产文件地址（session_asset.file_url）")


class Session(BaseModel):
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
    videos: List[SessionVideo] = Field(default_factory=list)


class ModuleWithSessions(Module):
    """模块 + 其下课次（含视频）。"""

    sessions: List[Session] = Field(default_factory=list)


# ============================================================
# 端点响应 data 载荷
# ============================================================
class CohortDetail(BaseModel):
    """班次详情（含模块列表）。"""

    cohort: Cohort
    modules: List[Module]


class CohortModulesData(BaseModel):
    """班次模块列表（每模块含课次）。"""

    cohort_id: int
    modules: List[ModuleWithSessions]
