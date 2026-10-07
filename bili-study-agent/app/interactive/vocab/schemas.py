# -*- coding: utf-8 -*-
"""P5 单词闯关 vocab schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class VocabCard(BaseModel):
    """一张「今日单词卡」。"""
    card_id: int = Field(..., description="user_vocab_card.id，POST recall 时回传")
    entry_id: int = Field(..., description="vocab_entry.id")
    word: str
    level_code: str
    subject_code: str = "english"
    phonetic_us: str | None = None
    meaning_cn: str = Field(..., description="释义，打靶时 daily 默认返回（给学习/选择模式直接对照）")
    example_en: str | None = None
    example_cn: str | None = None
    topic_tag: str | None = None
    image_hint: str | None = None
    audio_us: str | None = None
    mastery_status: str = Field(..., description="NEW/LEARNING/REVIEW/MASTERED")
    due_in_minutes: int | None = Field(default=None, description="到期后多少分钟；未到期则为 0")
    suggested_quiz_type: str = Field(..., pattern=r"^(PICK|LISTEN|SPELL|CLOZE)$")


class DailyPlan(BaseModel):
    """GET /vocab/daily 返回：今日应学 N 张 + 额外推荐 N 张。"""
    user_id: int
    date_label: str = Field(..., description="YYYY-MM-DD 本地日期")
    target_level_code: str = Field(..., description="今日主打 Lx")
    due_cards: list[VocabCard] = Field(..., description="已到期应复习卡片")
    new_cards: list[VocabCard] = Field(..., description="新推送卡片（新词 N 个）")
    total_new_quota: int = Field(..., ge=0, description="今日新词配额，默认 20")
    total_review_quota: int = Field(..., ge=0, description="今日复习配额，默认 60")
    summary: dict = Field(default_factory=dict, description="统计：已掌握/学习中/新词数/应复习数")


class RecallIn(BaseModel):
    """SM-2 quality 上报：0（完全忘了）到 5（秒答完美回忆）。"""
    card_id: int = Field(..., ge=1)
    quality: int = Field(..., ge=0, le=5, description="0/1 记错；2 模糊；3/4 记得；5 秒答")
    response_ms: int | None = Field(default=None, ge=0, description="反应时间（毫秒），可选")
    quiz_type: str = Field(default="PICK", pattern=r"^(PICK|LISTEN|SPELL|CLOZE)$")


class RecallOut(BaseModel):
    card_id: int
    quality: int
    mastery_status: str
    new_ease_factor: float
    new_interval_days: int
    new_due_at: datetime
    total_reviews: int
    streak_increment: int = Field(default=0, description="连续答对次数变化，通常 +1 或 0")
    ok: bool = True


class ProgressStat(BaseModel):
    """GET /vocab/progress 总览。"""
    user_id: int
    level_code: str
    total_words: int = Field(..., description="该等级词库词条数")
    mastered: int = Field(..., description="用户已掌握 MASTERED")
    learning: int = Field(..., description="LEARNING+REVIEW 学习中")
    new_today: int = Field(..., description="今日新增学习 NEW")
    reviewed_today: int = Field(..., description="今日复习数")
    streak_days: int = Field(..., ge=0, description="连续打卡天数（有 recall 就 +1）")
    total_reviews: int = Field(..., ge=0)
    accuracy_30d: float = Field(0.0, ge=0, le=1, description="30 天内正确率 quality>=3 / 总 review 数")
    expected_days_to_level_up: int | None = Field(default=None, ge=0, description="估计掌握 90% 该级词所需天数")
