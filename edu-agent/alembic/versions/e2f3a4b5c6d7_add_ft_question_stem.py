"""add FULLTEXT ngram index on question.stem

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-15

依据：数据库体检报告 F4 项。
question.stem 的 LIKE '%kw%' 查询为全表扫描（type=ALL，前导通配符无法走 B-Tree）。
方案选型：MySQL 内置 FULLTEXT + ngram（中文 2-gram 分词），万级题库无新组件成本。
用法：MATCH(stem) AGAINST('函数' IN NATURAL LANGUAGE MODE)。
注意：MATCH...AGAINST 是词匹配（非子串匹配），语义与 LIKE 不同——接入应用层前需确认业务预期。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `question` ADD FULLTEXT INDEX `ft_question_stem` (`stem`) WITH PARSER ngram"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE `question` DROP INDEX `ft_question_stem`")
