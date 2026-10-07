"""
分级课程数据模型（Pydantic v2）。

设计规则：
1. 只读响应体（Series/Cohort/Module/Session）：id + 全部业务字段
2. 写入请求体（SeriesCreate 等）：不含 id/created_at/updated_at（留给数据库生成）
3. 树形响应：SeriesTreeResponse（一次性返回 系列/模块/课次/班次 嵌套，前端免多次请求）
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 枚举
# ============================================================
class SubjectCode(str, Enum):
    """学科分类，和 curriculum_series.subject_code 对齐。"""
    ENGLISH = "english"
    PROGRAMMING = "programming"
    MATH = "math"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"

    @property
    def label(self) -> str:
        return {
            "english": "英语",
            "programming": "编程",
            "math": "数学",
            "physics": "物理",
            "chemistry": "化学",
        }[self.value]


class LevelCode(str, Enum):
    """难度分级，和 curriculum_series.level_code 对齐。"""
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class SaleStatus(str, Enum):
    DRAFT = "draft"
    ON_SALE = "on_sale"
    OFF_SALE = "off_sale"


class TeachingStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ============================================================
# 基础实体（只读）
# ============================================================
class Cohort(BaseModel):
    id: int
    series_id: int
    cohort_code: str
    cohort_name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    max_student_count: int
    current_student_count: int
    sale_price: Decimal
    yn: int
    created_at: datetime
    updated_at: datetime


class Session(BaseModel):
    id: int
    module_id: int
    session_no: int
    session_title: str
    description: Optional[str] = None
    teaching_status: TeachingStatus
    teaching_date: Optional[date] = None
    duration_minutes: int
    video_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Module(BaseModel):
    id: int
    series_id: int
    module_code: str
    module_name: str
    stage_no: int
    description: Optional[str] = None
    lesson_count: int
    total_hours: Decimal
    created_at: datetime
    updated_at: datetime
    sessions: list[Session] = Field(default_factory=list)


class Series(BaseModel):
    id: int
    series_code: str
    series_name: str
    subject_code: SubjectCode
    level_code: LevelCode
    level_name: str
    description: Optional[str] = None
    cover_url: Optional[str] = None
    target_hours: Decimal
    sale_status: SaleStatus
    sort_no: int
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# ============================================================
# 列表 + 分页
# ============================================================
class SeriesListItem(Series):
    """列表项额外统计字段（总课次 + 开班数量）。"""
    cohort_count: int = 0
    total_session_count: int = 0


class SeriesListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[SeriesListItem]


# ============================================================
# 详情 + 树
# ============================================================
class SeriesDetailResponse(BaseModel):
    series: Series
    cohorts: list[Cohort] = Field(default_factory=list)
    modules: list[Module] = Field(default_factory=list)


class SeriesTreeResponse(BaseModel):
    """系列 + 班次 + 模块 → 课次 完整嵌套树。"""
    series: Series
    cohorts: list[Cohort] = Field(default_factory=list)
    modules: list[Module] = Field(default_factory=list)
    summary_total_sessions: int = 0
    summary_total_hours: Decimal = Decimal("0")
