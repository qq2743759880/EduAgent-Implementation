"""Align source-asset task_id collation with its task authority.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _collation(conn, table: str, column: str) -> str | None:
    row = conn.execute(sa.text(
        "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column"
    ), {"table": table, "column": column}).first()
    return str(row[0]) if row and row[0] else None


def upgrade() -> None:
    conn = op.get_bind()
    parent = _collation(conn, "knowledge_import_task", "task_id")
    child = _collation(conn, "import_source_asset", "task_id")
    if not parent or not child:
        raise RuntimeError("cannot inspect task_id collation for W3 authority join")
    if child != parent:
        conn.execute(sa.text(
            "ALTER TABLE `import_source_asset` MODIFY COLUMN `task_id` "
            f"VARCHAR(64) CHARACTER SET utf8mb4 COLLATE {parent} NOT NULL"
        ))


def downgrade() -> None:
    conn = op.get_bind()
    child = _collation(conn, "import_source_asset", "task_id")
    if child and child != "utf8mb4_general_ci":
        conn.execute(sa.text(
            "ALTER TABLE `import_source_asset` MODIFY COLUMN `task_id` "
            "VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL"
        ))
