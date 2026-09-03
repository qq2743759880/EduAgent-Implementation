# -*- coding: utf-8 -*-
"""P3 学习进度追踪 —— schemas。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ========== 1. 视频播放打点 ==========


class VideoTickIn(BaseModel):
    """单条视频播放打点。"""
    event_type: str = Field(..., description="事件类型：PLAY / PAUSE / TICK / SEEK / END", max_length=32)
    position_seconds: int = Field(..., ge=0, description="当前播放位置（秒）")
    playback_rate: float = Field(1.0, gt=0, le=4, description="播放倍率（0.5-4x）")
    network_type: str = Field("UNKNOWN", description="网络类型：WIFI / 4G / 5G / UNKNOWN", max_length=32)
    event_time: datetime = Field(description="客户端事件发生时间（带时区或本地时间都可）")
    event_payload: dict[str, Any] | None = Field(default=None, description="附加信息，如视频分辨率等")


class VideoTickBatchIn(BaseModel):
    """批量视频打点请求（30 秒一次，客户端可攒多条）。"""
    play_session_id: int = Field(..., gt=0, description="客户端播放会话 ID（同一视频窗口的自增）")
    session_id: int = Field(..., gt=0, description="课次 ID = curriculum_session.id")
    ticks: list[VideoTickIn] = Field(..., min_length=1, max_length=200, description="批量打点列表")


class VideoTickBatchOut(BaseModel):
    inserted: int = Field(..., ge=0, description="成功插入的条数（去重后）")
    study_seconds_delta: int = Field(..., ge=0, description="本批次累计贡献学习秒数（后 position - 前 position 正增量求和）")
    message: str = "ok"


# ========== 2. 作业/考试提交 ==========


class SubmittedAnswerIn(BaseModel):
    """一道题的作答。"""
    question_id: int = Field(..., gt=0, description="题目 ID = admin_question_bank.id")
    answer: str = Field(..., description="学生答案：单选'A'、多选'AC'、判断'1'/'0'、填空'answer'、主观'文本'")


class HomeworkSubmitIn(BaseModel):
    """作业提交请求（一课次一次作业）。"""
    session_id: int = Field(..., gt=0, description="课次 ID = series_cohort_session.id")
    homework_id: int = Field(..., gt=0, description="作业 ID = session_homework.id（外键必填）")
    answers: list[SubmittedAnswerIn] = Field(..., min_length=1, max_length=100, description="所有作答")


class ExamSubmitIn(BaseModel):
    """考试提交请求。"""
    exam_id: int = Field(..., gt=0, description="考试 ID = session_exam.id（外键必填）")
    answers: list[SubmittedAnswerIn] = Field(..., min_length=1, max_length=200, description="所有作答")
    duration_seconds: int = Field(..., ge=0, description="作答耗时（秒）")
    start_at: datetime = Field(description="开始答题时间")
    model_config = ConfigDict(extra="ignore")


class SubmitOut(BaseModel):
    """作业/考试提交返回：自动批改后的结果。"""
    submission_id: int = Field(..., gt=0, description="提交记录 ID")
    submit_no: str = Field(..., description="提交流水号（作业=SH- 前缀 / 考试=EX-）")
    total_score: float | None = Field(default=None, ge=0, description="本次总得分（主观题=0 由老师批改）")
    correct_count: int = Field(..., ge=0, description="自动判题正确题数")
    total_count: int = Field(..., ge=0, description="总题数")
    correct_rate: float | None = Field(default=None, ge=0, le=1, description="自动判题正确率")
    status: str = Field(..., description="状态：SUBMITTED / PARTIAL_GRADED / AUTO_GRADED")


# ========== 3. 统计看板 ==========


class DailyStatItem(BaseModel):
    """单日学习数据项。"""
    stat_date: date
    study_seconds: int = Field(..., ge=0, description="当日学习时长（秒）")
    video_ticks: int = 0
    homework_submitted: int = 0
    homework_correct_rate: float | None = None
    exam_submitted: int = 0
    exam_avg_score: float | None = None
    questions_attempted: int = 0
    questions_correct: int = 0


class DashboardOut(BaseModel):
    """统计看板总览（个人 C 端）。"""
    total_days: int = Field(..., ge=0, description="累计学习天数（daily_summary 有记录的不同日期数）")
    total_study_seconds: int = Field(..., ge=0, description="累计学习总时长（秒）")
    total_questions_attempted: int = Field(..., ge=0, description="累计答题数")
    total_questions_correct: int = Field(..., ge=0, description="累计正确题数")
    overall_correct_rate: float | None = Field(default=None, ge=0, le=1)
    active_courses_count: int = Field(0, ge=0, description="当前进行中的班次（enroll_status='active'）数")
    latest_streak_days: int = Field(..., ge=0, description="最近连续学习天数（截止昨天或今天）")
    recent_days: list[DailyStatItem] = Field(..., description="最近 N 天明细")


# ========== 4. 课程进度 ==========


class SessionProgressItem(BaseModel):
    """一个课次的进度。"""
    session_id: int
    session_title: str
    teaching_date: date | None = None
    video_watch_ratio: float = Field(0, ge=0, le=1, description="视频观看进度 0-1（=用户打点最大 position / session.duration_minutes*60）")
    homework_done: bool = Field(False, description="该课次是否已提交作业")
    homework_score: float | None = Field(default=None, description="作业分数（AUTO_GRADED 时为实际分）")


class ModuleProgressItem(BaseModel):
    """一个模块下所有课次进度。"""
    module_id: int
    module_title: str
    module_no: int
    overall_ratio: float = Field(0, ge=0, le=1, description="模块整体进度 = 课次视频*0.5 + 课次作业*0.5 的平均")
    sessions: list[SessionProgressItem]


class CourseProgressOut(BaseModel):
    """一个系列/班次的课程进度。"""
    series_id: int
    series_title: str
    overall_ratio: float = Field(0, ge=0, le=1, description="课程总进度 = 各模块平均")
    total_sessions: int = 0
    completed_sessions: int = Field(0, ge=0, description="完成课次数（视频>0.8 且作业完成）")
    modules: list[ModuleProgressItem]

    model_config = ConfigDict(extra="ignore")
