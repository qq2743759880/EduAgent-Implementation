"""add description review fields to mcp_tool + review audit log table

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-08-26

task33: MCP 描述体检（规则评分 + FAST 重写）+ 审计日志。
- mcp_tool 增加三列：
    description_rewritten   FAST 重写后的五要素描述（原 description 仅展示）
    description_score       规则体检分值 0-100
    description_reviewed_at 最近一次体检时间
- 新增审计表 mcp_tool_description_review_log：每次体检记录 score/reasons/breaches/
  rewritten/rewritten_by_llm/operator_user_id，满足 task33 GWT①「审计日志」。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"SHOW COLUMNS FROM `{table}`"))
    return {str(r[0]) for r in rows}


def upgrade() -> None:
    conn = op.get_bind()
    names = _column_names(conn, "mcp_tool")
    if "description_rewritten" not in names:
        op.execute("ALTER TABLE `mcp_tool` ADD COLUMN `description_rewritten` TEXT NULL "
                   "COMMENT 'FAST重写后的五要素描述（原description仅展示）'")
    if "description_score" not in names:
        op.execute("ALTER TABLE `mcp_tool` ADD COLUMN `description_score` INT NULL "
                   "COMMENT '规则体检分值 0-100'")
    if "description_reviewed_at" not in names:
        op.execute("ALTER TABLE `mcp_tool` ADD COLUMN `description_reviewed_at` DATETIME NULL "
                   "COMMENT '最近描述体检时间'")
    conn.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS `mcp_tool_description_review_log` ("
        "  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,"
        "  `server_id` INT NOT NULL,"
        "  `tool_id` INT NOT NULL,"
        "  `tool_name` VARCHAR(128) NOT NULL,"
        "  `score` INT NOT NULL,"
        "  `reasons` TEXT NULL,"
        "  `breaches` TEXT NULL,"
        "  `rewritten` TEXT NULL,"
        "  `rewritten_by_llm` TINYINT NOT NULL DEFAULT 0 COMMENT '是否经FAST模型重写',"
        "  `original_desc` TEXT NULL,"
        "  `operator_user_id` INT NULL,"
        "  `trace_id` VARCHAR(64) NULL,"
        "  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "  PRIMARY KEY (`id`),"
        "  KEY `idx_rev_tool` (`tool_id`),"
        "  KEY `idx_rev_server` (`server_id`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci "
        "COMMENT='MCP 工具描述体检审计日志'"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS `mcp_tool_description_review_log`"))
    names = _column_names(conn, "mcp_tool")
    for col in ("description_rewritten", "description_score", "description_reviewed_at"):
        if col in names:
            op.execute(f"ALTER TABLE `mcp_tool` DROP COLUMN `{col}`")