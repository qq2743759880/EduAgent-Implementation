"""管理端题库域 Pydantic 模型（task13）。

层级语义：
  question_bank（yn=0 软删，bank_code 唯一）
    └── question（yn=0 软删，question_code 唯一 per bank，options_json/answer_text/analysis_text）
    └── 批量导入（JSON 数组 → 校验 → 导入 → 结果报告）
    └── 组卷快照（session_exam + session_exam_question_rel）

全部 CRUD 响应壳使用契约①（成功 code=0 int / 失败 code=<字符串>）。
标签逻辑删除 — 改为 stem/analysis_text LIKE 检索，不再维护 tag 表。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════
# 题库（question_bank）
# ═══════════════════════════════════════════
class BankCreateAdmin(BaseModel):
    institution_id: int
    category_id: int
    bank_code: str = Field(..., min_length=1, max_length=64)
    bank_name: str = Field(..., min_length=1, max_length=128)


class BankUpdateAdmin(BaseModel):
    category_id: Optional[int] = None
    bank_name: Optional[str] = Field(None, min_length=1, max_length=128)


class BankResponseAdmin(BaseModel):
    id: int
    institution_id: int
    category_id: int
    bank_code: str
    bank_name: str
    yn: int
    created_at: datetime
    updated_at: datetime


class BankListDataAdmin(BaseModel):
    items: List[BankResponseAdmin]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# 题目（question）
# ═══════════════════════════════════════════
class QuestionAdminCreate(BaseModel):
    bank_id: int
    question_code: str = Field(..., min_length=1, max_length=64)
    question_type_id: int
    stem: str = Field(..., min_length=1)
    options_json: Optional[Any] = None
    answer_text: str = Field(..., min_length=1)
    analysis_text: Optional[str] = None


class QuestionAdminUpdate(BaseModel):
    question_type_id: Optional[int] = None
    stem: Optional[str] = Field(None, min_length=1)
    options_json: Optional[Any] = None
    answer_text: Optional[str] = Field(None, min_length=1)
    analysis_text: Optional[str] = None


class QuestionResponseAdmin(BaseModel):
    id: int
    bank_id: int
    question_code: str
    question_type_id: int
    stem: str
    options_json: Optional[Any] = None
    answer_text: str
    analysis_text: Optional[str] = None
    yn: int
    created_at: datetime
    updated_at: datetime


class QuestionListDataAdmin(BaseModel):
    items: List[QuestionResponseAdmin]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# 题型维表（dim_question_type，只读）
# ═══════════════════════════════════════════
class QuestionTypeResponse(BaseModel):
    id: int
    type_code: str
    type_name: str
    objective_flag: int
    auto_marking_flag: int
    sort_no: int


# ═══════════════════════════════════════════
# 批量导入
# ═══════════════════════════════════════════
class BatchImportItem(BaseModel):
    """单条导入题目（JSON 数组元素）。"""
    question_code: str = Field(..., min_length=1, max_length=64)
    question_type_id: int
    stem: str = Field(..., min_length=1)
    options_json: Optional[Any] = None
    answer_text: str = Field(..., min_length=1)
    analysis_text: Optional[str] = None


class BatchImportPreviewRow(BaseModel):
    """导入预览单行结果。"""
    row_index: int
    question_code: str
    valid: bool
    errors: List[str] = Field(default_factory=list)


class BatchImportPreviewResponse(BaseModel):
    """导入预览响应。"""
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: List[BatchImportPreviewRow]
    message: str


class BatchImportExecuteResponse(BaseModel):
    """导入执行响应（幂等：重复 question_code 返回原记录）。"""
    total: int
    imported: int
    skipped: int  # 幂等跳过（已存在）
    failed: int
    messages: List[str] = Field(default_factory=list)


# ═══════════════════════════════════════════
# 组卷快照（session_exam + session_exam_question_rel）
# ═══════════════════════════════════════════
class ExamCreateAdmin(BaseModel):
    session_id: int
    exam_code: str = Field(..., min_length=1, max_length=64)
    exam_name: str = Field(..., min_length=1, max_length=128)
    total_score: Decimal = Field(..., ge=0)
    pass_score: Decimal = Field(..., ge=0)
    duration_minutes: int = Field(..., ge=1)
    window_start_at: datetime
    deadline_at: datetime
    created_by: int


class ExamUpdateAdmin(BaseModel):
    exam_name: Optional[str] = Field(None, min_length=1, max_length=128)
    total_score: Optional[Decimal] = Field(None, ge=0)
    pass_score: Optional[Decimal] = Field(None, ge=0)
    duration_minutes: Optional[int] = Field(None, ge=1)
    window_start_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None


class ExamQuestionRelItem(BaseModel):
    """考试-题目关系（快照条目）。"""
    id: int
    exam_id: int
    question_id: int
    sort_no: int
    score: Decimal
    created_at: datetime
    updated_at: datetime


class ExamResponseAdmin(BaseModel):
    """考试完整响应（含快照题目列表）。"""
    id: int
    session_id: int
    exam_code: str
    exam_name: str
    total_score: Decimal
    pass_score: Decimal
    publish_status: str
    created_by: int
    duration_minutes: int
    window_start_at: datetime
    deadline_at: datetime
    publish_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    questions: List[ExamQuestionRelItem] = Field(default_factory=list, description="快照题目列表（发布后冻结）")


class ExamListDataAdmin(BaseModel):
    items: List[ExamResponseAdmin]
    total: int
    page: int
    page_size: int


class ExamPublishRequest(BaseModel):
    """发布考试 = 快照题目到 session_exam_question_rel。"""
    question_ids: List[dict] = Field(..., description="[{\"question_id\":int, \"sort_no\":int, \"score\":Decimal}]")


class ExamPublishResponse(BaseModel):
    exam_id: int
    exam_code: str
    publish_status: str
    question_count: int
    message: str


# ═══════════════════════════════════════════
# Quiz 出题响应（复用 quiz schemas 结构）
# ═══════════════════════════════════════════
class QuestionTypeListResponse(BaseModel):
    items: List[QuestionTypeResponse]
    total: int


class QuizQuestionResponse(BaseModel):
    """从 question 表出题的响应（给 interactive/quiz 消费）。"""
    question_id: int
    question_code: str
    question_type_id: int
    stem: str
    options_json: Optional[Any] = None
    analysis_text: Optional[str] = None
    answer_text: Optional[str] = None  # quiz 场景可能需要隐藏答案