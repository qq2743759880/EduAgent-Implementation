"""
P7 管理端控制台 - 题库管理 schemas。
表：admin_question_bank / admin_question_tag / admin_question_to_tag / admin_exam_paper / admin_exam_paper_item
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# 枚举
# ============================================================
class QuestionType(str):
    SINGLE = "single_choice"
    MULTI = "multi_choice"
    JUDGE = "true_false"
    FILL = "fill_blank"
    SHORT = "short_answer"


# ============================================================
# 标签
# ============================================================
class QuestionTag(BaseModel):
    id: int
    tag_type: str
    tag_code: str
    tag_name: str
    subject_code: Optional[str] = None
    description: Optional[str] = None
    sort_no: int
    yn: int
    created_at: datetime
    updated_at: datetime


class QuestionTagCreate(BaseModel):
    tag_type: str = Field(..., max_length=32)
    tag_code: str = Field(..., max_length=64)
    tag_name: str = Field(..., max_length=64)
    subject_code: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = None
    sort_no: int = 0


# ============================================================
# 题目
# ============================================================
class QuestionOption(BaseModel):
    label: str
    content: str


class QuestionAdminCreate(BaseModel):
    question_code: str = Field(..., max_length=64)
    subject_code: str = Field(..., max_length=32)
    question_type: str = Field(..., max_length=32)
    difficulty_level: Literal["L1", "L2", "L3", "L4", "L5"] = "L2"
    stem_html: str = Field(..., min_length=1)
    analysis_html: Optional[str] = None
    options_json: list[QuestionOption] = Field(default_factory=list)
    correct_answer: str = Field(..., max_length=128)
    correct_answer_detail: Optional[str] = None
    default_score: int = Field(default=5, ge=0)
    knowledge_point_codes: list[str] = Field(default_factory=list)
    tag_ids: list[int] = Field(default_factory=list)


class QuestionAdminUpdate(BaseModel):
    subject_code: Optional[str] = None
    question_type: Optional[str] = None
    difficulty_level: Optional[Literal["L1", "L2", "L3", "L4", "L5"]] = None
    stem_html: Optional[str] = None
    analysis_html: Optional[str] = None
    options_json: Optional[list[QuestionOption]] = None
    correct_answer: Optional[str] = None
    correct_answer_detail: Optional[str] = None
    default_score: Optional[int] = None
    knowledge_point_codes: Optional[list[str]] = None
    tag_ids: Optional[list[int]] = None
    yn: Optional[int] = None


class QuestionBankItem(BaseModel):
    id: int
    question_code: str
    subject_code: str
    question_type: str
    difficulty_level: str
    stem_preview: str
    default_score: int
    yn: int
    created_at: datetime
    updated_at: datetime
    tags: list[QuestionTag] = Field(default_factory=list)


class QuestionBankDetail(BaseModel):
    id: int
    question_code: str
    subject_code: str
    question_type: str
    difficulty_level: str
    stem_html: str
    analysis_html: Optional[str] = None
    options_json: list[QuestionOption] = Field(default_factory=list)
    correct_answer: str
    correct_answer_detail: Optional[str] = None
    default_score: int
    knowledge_point_codes: list[str] = Field(default_factory=list)
    yn: int
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    tags: list[QuestionTag] = Field(default_factory=list)


class QuestionBankListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[QuestionBankItem]


# ============================================================
# 批量导入（简化：JSON 数组直接入库）
# ============================================================
class QuestionBatchImportResponse(BaseModel):
    total: int
    imported: int
    skipped: int
    failed: int
    messages: list[str] = Field(default_factory=list)


# ============================================================
# 试卷
# ============================================================
class ExamPaperItem(BaseModel):
    id: int
    paper_id: int
    question_id: int
    sort_no: int
    score: int
    created_at: datetime


class ExamPaper(BaseModel):
    id: int
    paper_code: str
    paper_title: str
    subject_code: str
    total_score: int
    duration_minutes: int
    pass_score: int
    description: Optional[str] = None
    yn: int
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    items: list[ExamPaperItem] = Field(default_factory=list)


class ExamPaperAdminCreate(BaseModel):
    paper_code: str = Field(..., max_length=64)
    paper_title: str = Field(..., max_length=256)
    subject_code: str = Field(..., max_length=32)
    total_score: int = Field(default=100, ge=0)
    duration_minutes: int = Field(default=120, ge=1)
    pass_score: int = Field(default=60, ge=0)
    description: Optional[str] = None
    items: list[dict] = Field(default_factory=list)   # [{"question_id": int, "sort_no": int, "score": int}]


class PaperGenerateSpec(BaseModel):
    subject_code: str
    total_score: int = Field(default=100, ge=0)
    duration_minutes: int = Field(default=120, ge=1)
    pass_score: int = Field(default=60, ge=0)
    difficulty_level: Optional[Literal["L1", "L2", "L3", "L4", "L5"]] = None
    tag_ids: list[int] = Field(default_factory=list)
    per_question_score: int = Field(default=5, ge=1)


class PaperComposeRequest(BaseModel):
    spec: PaperGenerateSpec
    paper_code: str = Field(..., max_length=64)
    paper_title: str = Field(..., max_length=256)
    expected_question_count: int = Field(default=20, ge=1, le=200)


class PaperComposeResult(BaseModel):
    draft_paper_id: int
    paper_code: str
    paper_title: str
    selected_count: int
    total_score: int
    message: str
    items: list[dict] = Field(default_factory=list)
