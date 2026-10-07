# -*- coding: utf-8 -*-
"""enrollment 域（task20 契约⑪前段）schemas：我的班次 + 报名 + 进度聚合。

对齐：
- 权威端点 GET /api/enrollments/me/cohorts?status=（前端 enrollments.ts EnrolledCohort[]，解锁 task47 /my-courses）
- api-request §1 POST /api/enrollments（后端满班 409 并发控制）
- enroll_status 枚举（edu.sql student_cohort_rel）：active/completed/cancelled/refunded
- 进度聚合真实：series_cohort_course（模块）+ series_cohort_session（课次）+ session_homework_submission（提交表）
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EnrollStatus = Literal["active", "completed", "cancelled", "refunded"]
DeliveryMode = Literal["online_live", "online_recorded", "offline_face_to_face"]


class EnrolledNextSession(BaseModel):
    """下次课（四级结构 module→session，供「继续学习」跳转）。"""
    series_id: int | None = None
    module_id: int | None = None
    module_title: str | None = None
    session_id: int | None = None
    session_title: str | None = None
    teaching_at: str | None = None       # 后端已格式化（teaching_date + start_time）


class EnrolledRefund(BaseModel):
    """退款信息（refunded 态展示「查看退款」）。"""
    refund_no: str | None = None
    refund_amount: str | None = None
    refunded_at: datetime | None = None


class EnrolledCohort(BaseModel):
    """我的班次单条（契约⑪ GET /api/enrollments/me/cohorts 元素）。"""
    enrollment_id: int                  # student_cohort_rel.id
    cohort_id: int
    cohort_name: str | None = None
    series_id: int
    series_name: str | None = None
    series_code: str | None = None
    subject_code: str | None = None
    level_code: str | None = None
    cover_url: str | None = None
    delivery_mode: DeliveryMode | None = None
    enroll_status: EnrollStatus

    overall_ratio: float | None = None   # 完成率 0-100
    module_done: int | None = None
    module_total: int | None = None
    session_done: int | None = None
    session_total: int | None = None

    next_session: EnrolledNextSession | None = None
    finished_at: datetime | None = None
    refund: EnrolledRefund | None = None


class EnrollCreateResult(BaseModel):
    """报名结果（手动报名，含满班 409 返回）。"""
    enrollment_id: int
    cohort_id: int
    series_id: int
    enroll_status: EnrollStatus
    enrolled_at: datetime


class EnrollCreateInput(BaseModel):
    """报名请求体。"""
    cohort_id: int = Field(..., gt=0)


class ProgressSession(BaseModel):
    session_id: int
    session_no: int
    session_title: str
    teaching_status: str
    done: bool = False                  # 该学生是否已提交（真实提交表判定）


class ProgressModule(BaseModel):
    module_id: int
    module_name: str
    stage_no: int
    sessions: list[ProgressSession] = []
    done_count: int = 0
    total_count: int = 0


class ProgressSnapshot(BaseModel):
    """进度快照（模块/课次完成明细，供前端进度条）。"""
    cohort_id: int
    series_id: int
    overall_ratio: float = 0.0
    module_done: int = 0
    module_total: int = 0
    session_done: int = 0
    session_total: int = 0
    modules: list[ProgressModule] = []