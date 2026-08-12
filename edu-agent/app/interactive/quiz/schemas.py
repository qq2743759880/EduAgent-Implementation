# -*- coding: utf-8 -*-
"""P5 互动习题 quiz schemas：6 题型 + 作答提交 + 判分反馈 + 错题本。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ========== 6 题型枚举 ==========
SINGLE, MULTI, JUDGE, FILL, DRAG_SORT, MATCH = (
    "SINGLE", "MULTI", "JUDGE", "FILL", "DRAG_SORT", "MATCH",
)


class Choice(BaseModel):
    """单选 / 多选 选项单元。"""
    key: str = Field(..., max_length=16, description="A/B/C/D 或自定义 key")
    text: str = Field(..., max_length=1000, description="选项内容")
    image_url: str | None = None


class MatchPair(BaseModel):
    """连线匹配：左侧项 <-> 右侧正确项。"""
    left_id: str = Field(..., max_length=32)
    left_text: str
    right_id: str = Field(..., max_length=32)
    right_text: str


# ========== 题目 ==========

class Question(BaseModel):
    """对外返回的一道互动习题（不含答案字段，但内置 mock 也会带上 correct 便于打靶自测）。

    题型 → required 字段：
      - SINGLE / MULTI：choices[], correct（单 key 或 key 数组）
      - JUDGE：无 choices；correct=true/false
      - FILL：correct（字符串 或 字符串数组 多空）
      - DRAG_SORT：items[] 可拖拽条目；correct 为按序的 item_id 数组
      - MATCH：pairs[]，用户作答 user_matches=[{left_id,right_id}]
    """
    question_id: int | None = Field(default=None, description="admin_question.id，null 表示内置 mock 题")
    custom_code: str = Field(..., max_length=64, description="若 question_id 为空则用 custom_code 唯一")
    subject_code: str = Field(..., max_length=32)
    question_type: str = Field(..., pattern=f"^({SINGLE}|{MULTI}|{JUDGE}|{FILL}|{DRAG_SORT}|{MATCH})$")
    title: str = Field(..., max_length=2000, description="题干文本（含 markdown/LaTeX 片段）")
    media: list[dict[str, Any]] = Field(default_factory=list, description="图片/音频/视频占位")
    score_max: float = Field(5.0, gt=0, description="满分")
    time_limit_sec: int | None = Field(default=None, ge=10)
    knowledge_codes: list[str] = Field(default_factory=list, description="关联知识点 code（对齐 P4 图谱）")
    # 题型具体
    choices: list[Choice] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list, description="DRAG_SORT 拖拽条目 [{item_id, label}]")
    pairs: list[MatchPair] = Field(default_factory=list, description="MATCH 正确配对数组（后端判分时用，对外返回做混淆：左右乱序）")
    correct: Any = Field(default=None, description="判分用正确答案，可选是否对外暴露（打靶允许对外）")
    hint: str | None = Field(default=None, max_length=1000)
    explain_template: str | None = Field(default=None, max_length=2000, description="判定后可结合大模型 RAG 生成完整解析")

    model_config = ConfigDict(extra="ignore")


# ========== 作答提交 ==========

class SubmitAnswer(BaseModel):
    """用户作答负载：question_type -> answer 格式约定。"""
    question_id: int | None = None
    custom_code: str = Field(..., max_length=64)
    question_type: str = Field(..., pattern=f"^({SINGLE}|{MULTI}|{JUDGE}|{FILL}|{DRAG_SORT}|{MATCH})$")
    answer: Any = Field(..., description="按题型：SINGLE 单 str / MULTI list[str] / JUDGE bool / FILL list[str] | str / DRAG_SORT list / MATCH list[{left_id,right_id}]")
    time_spent_sec: int = Field(0, ge=0)


class SubmitResult(BaseModel):
    session_id: int
    is_correct: bool
    score: float
    score_max: float
    explain_text: str
    rag_citation: list[str] = Field(default_factory=list, description="关联知识点标题，打靶可空")
    added_to_wrong_book: bool = Field(False, description="是否进入错题本")
    mastery_change: dict[str, float] = Field(default_factory=dict, description="关联知识点 mastery 新估值（可选）")
    created_at: datetime = Field(default_factory=datetime.now)


# ========== 错题本 ==========

class WrongBookEntry(BaseModel):
    id: int
    question_id: int | None
    custom_code: str | None
    subject_code: str | None
    question_type: str
    wrong_count: int
    correct_count: int
    status: str
    next_review_at: datetime | None
    last_wrong_answer: Any = None


class WrongBookList(BaseModel):
    items: list[WrongBookEntry]
    total: int
    page: int
    page_size: int
    filter_status: str
