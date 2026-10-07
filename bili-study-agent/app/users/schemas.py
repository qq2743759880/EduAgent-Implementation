"""
用户画像数据模型（Pydantic v2）。

四个 JSON 列转成嵌套 Pydantic 模型（和前端表单一一对应）：
  learning_goals        → list[str]
  subject_preferences   → list[SubjectPreference]
  level_assessments     → list[LevelAssessment]
  interest_tags         → list[str]
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    SECRET = "secret"


class StudyStyle(str, Enum):
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    MIXED = "mixed"


class SubjectPreference(BaseModel):
    subject_code: str = Field(..., max_length=32, description="english/programming/math/... 对齐 curriculum")
    preference_score: int = Field(..., ge=1, le=5, description="1 不喜欢 → 5 特别喜欢")


class LevelAssessment(BaseModel):
    subject_code: str = Field(..., max_length=32)
    level_code: str = Field(..., max_length=8, description="L1-L5")
    assessed_at: Optional[datetime] = Field(default=None, description="PUT 为空时服务端自动填 NOW()")


class UserProfile(BaseModel):
    """GET /api/users/me/profile 响应体"""
    model_config = ConfigDict(from_attributes=True)

    nickname: Optional[str] = Field(default=None, max_length=64)
    avatar_url: Optional[str] = Field(default=None, max_length=255)
    gender: Optional[Gender] = None
    birthday: Optional[date] = None
    grade_code: Optional[str] = Field(default=None, max_length=32)
    school_name: Optional[str] = Field(default=None, max_length=128)
    region_code: Optional[str] = Field(default=None, max_length=32)
    weekly_available_hours: int = Field(..., ge=0, le=168)
    study_style: Optional[StudyStyle] = None
    target_qualification: Optional[str] = Field(default=None, max_length=128)
    learning_goals: list[str] = Field(default_factory=list)
    subject_preferences: list[SubjectPreference] = Field(default_factory=list)
    level_assessments: list[LevelAssessment] = Field(default_factory=list)
    interest_tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseModel):
    """PUT 请求体：全部 Optional，None 不改"""
    nickname: Optional[str] = Field(default=None, max_length=64)
    avatar_url: Optional[str] = Field(default=None, max_length=255)
    gender: Optional[Gender] = None
    birthday: Optional[date] = None
    grade_code: Optional[str] = Field(default=None, max_length=32)
    school_name: Optional[str] = Field(default=None, max_length=128)
    region_code: Optional[str] = Field(default=None, max_length=32)
    weekly_available_hours: Optional[int] = Field(default=None, ge=0, le=168)
    study_style: Optional[StudyStyle] = None
    target_qualification: Optional[str] = Field(default=None, max_length=128)
    learning_goals: Optional[list[str]] = Field(default=None)
    subject_preferences: Optional[list[SubjectPreference]] = Field(default=None)
    level_assessments: Optional[list[LevelAssessment]] = Field(default=None)
    interest_tags: Optional[list[str]] = Field(default=None)
