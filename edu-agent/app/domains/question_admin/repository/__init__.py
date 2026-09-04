"""question_admin 仓储层（4 Repo）。"""

from app.domains.question_admin.repository.bank_repo import BankAdminRepo
from app.domains.question_admin.repository.question_repo import QuestionAdminRepo
from app.domains.question_admin.repository.exam_repo import ExamAdminRepo
from app.domains.question_admin.repository.dim_repo import DimQuestionTypeRepo

__all__ = [
    "BankAdminRepo",
    "QuestionAdminRepo",
    "ExamAdminRepo",
    "DimQuestionTypeRepo",
]