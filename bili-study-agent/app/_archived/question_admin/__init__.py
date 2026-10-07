"""
P7 管理端控制台 - 题库管理 admin/question_admin 包。
"""
from __future__ import annotations

from app.admin.question_admin.schemas import (
    ExamPaper,
    ExamPaperAdminCreate,
    ExamPaperItem,
    PaperComposeRequest,
    PaperComposeResult,
    PaperGenerateSpec,
    QuestionAdminCreate,
    QuestionAdminUpdate,
    QuestionBankDetail,
    QuestionBankItem,
    QuestionBankListResponse,
    QuestionOption,
    QuestionTag,
    QuestionTagCreate,
    QuestionType,
)

__all__ = [
    "ExamPaper",
    "ExamPaperAdminCreate",
    "ExamPaperItem",
    "PaperComposeRequest",
    "PaperComposeResult",
    "PaperGenerateSpec",
    "QuestionAdminCreate",
    "QuestionAdminUpdate",
    "QuestionBankDetail",
    "QuestionBankItem",
    "QuestionBankListResponse",
    "QuestionOption",
    "QuestionTag",
    "QuestionTagCreate",
    "QuestionType",
]
