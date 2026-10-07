"""drop redundant indexes violating leftmost-prefix rule

Revision ID: d1e2f3a4b5c6
Revises: 94fadf13f4ca
Create Date: 2026-08-15

依据：数据库体检报告 test-reports/db-healthcheck-2026-08-15.md F1 项。
sys.schema_redundant_indexes 审计发现 4 条冗余索引（2 张表）：

- admin_exam_paper_item.idx_admin_exam_paper_item_paper(paper_id)
  被 uk_admin_exam_paper_item_question(paper_id,question_id)
  与 uk_admin_exam_paper_item_sort(paper_id,sort_no) 的左起前缀覆盖。
- curriculum_session.idx_curriculum_session_module(module_id)
  被 uk_curriculum_session_no(module_id,session_no)
  与 idx_curriculum_session_module_yn(module_id,yn) 的左起前缀覆盖。

原理：联合索引 B+ 树按左起列排序，单独按前缀列过滤可复用联合索引；
冗余索引只增加写入维护成本。MySQL 8 外键自动建索引，FK 不受影响。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = '94fadf13f4ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `admin_exam_paper_item` DROP INDEX `idx_admin_exam_paper_item_paper`"
    )
    op.execute(
        "ALTER TABLE `curriculum_session` DROP INDEX `idx_curriculum_session_module`"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE `admin_exam_paper_item` ADD INDEX `idx_admin_exam_paper_item_paper` (`paper_id`)"
    )
    op.execute(
        "ALTER TABLE `curriculum_session` ADD INDEX `idx_curriculum_session_module` (`module_id`)"
    )
