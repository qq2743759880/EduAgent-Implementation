"""W3 additive source-asset authority and dispatch metadata.

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(conn, table: str) -> set[str]:
    return {str(row[0]) for row in conn.execute(sa.text(f"SHOW COLUMNS FROM `{table}`"))}


def upgrade() -> None:
    conn = op.get_bind()
    task_columns = _columns(conn, "knowledge_import_task")
    if "security_scope" not in task_columns:
        conn.execute(sa.text(
            "ALTER TABLE `knowledge_import_task` ADD COLUMN `security_scope` "
            "VARCHAR(64) NOT NULL DEFAULT 'default' COMMENT '权限安全域'"
        ))

    asset_columns = _columns(conn, "import_source_asset")
    if "dispatched_epoch" not in asset_columns:
        conn.execute(sa.text(
            "ALTER TABLE `import_source_asset` ADD COLUMN `dispatched_epoch` INT NULL "
            "COMMENT '最近成功写入 Redis stream 的 execution_epoch'"
        ))
    if "dlq_epoch" not in asset_columns:
        conn.execute(sa.text(
            "ALTER TABLE `import_source_asset` ADD COLUMN `dlq_epoch` INT NULL "
            "COMMENT '最近成功持久化到 DLQ 的 failed execution_epoch'"
        ))
    for name, ddl in {
        "vector_status": "VARCHAR(24) NOT NULL DEFAULT 'not-produced' COMMENT '向量生成状态'",
        "graph_status": "VARCHAR(24) NOT NULL DEFAULT 'not-produced' COMMENT '图谱生成状态'",
        "graph_retry_needed": "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '图谱是否待修复'",
    }.items():
        if name not in asset_columns:
            conn.execute(sa.text(f"ALTER TABLE `import_source_asset` ADD COLUMN `{name}` {ddl}"))
    if "artifact_ref" in asset_columns:
        conn.execute(sa.text(
            "ALTER TABLE `import_source_asset` MODIFY COLUMN `artifact_ref` TEXT NULL "
            "COMMENT '完整 IR artifact 对象引用 JSON'"
        ))


def downgrade() -> None:
    conn = op.get_bind()
    asset_columns = _columns(conn, "import_source_asset")
    if "artifact_ref" in asset_columns:
        too_long = conn.execute(sa.text(
            "SELECT 1 FROM `import_source_asset` WHERE CHAR_LENGTH(`artifact_ref`) > 255 LIMIT 1"
        )).first()
        if too_long:
            raise RuntimeError("artifact_ref 含超过 255 字符的引用，拒绝有损 downgrade")
        conn.execute(sa.text(
            "ALTER TABLE `import_source_asset` MODIFY COLUMN `artifact_ref` VARCHAR(255) NULL "
            "COMMENT '解析产物引用（IR/清洗产物）'"
        ))
    if "dispatched_epoch" in asset_columns:
        conn.execute(sa.text("ALTER TABLE `import_source_asset` DROP COLUMN `dispatched_epoch`"))
    if "dlq_epoch" in asset_columns:
        conn.execute(sa.text("ALTER TABLE `import_source_asset` DROP COLUMN `dlq_epoch`"))
    task_columns = _columns(conn, "knowledge_import_task")
    if "security_scope" in task_columns:
        conn.execute(sa.text("ALTER TABLE `knowledge_import_task` DROP COLUMN `security_scope`"))
