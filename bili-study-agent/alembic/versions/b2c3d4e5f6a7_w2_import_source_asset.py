"""W2-S2: import_source_asset table + knowledge_import_task.document_id

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-27

W2-S2（import_source_asset 迁移 + 身份持久化）：
- 新表 `import_source_asset`：task 1:N asset 细化（每源文件一行），
  parser job 的 claim/retry/lease 字段在此冻结；stage 为冻结词汇
  （queued_parser/parsing/ir_ready/ingested/failed），W2 只写
  queued_parser→ir_ready 两态（ADR-W2-01：W2 不 enqueue，真实消费在 S4）。
- `knowledge_import_task` additive 加列 `document_id VARCHAR(40) NULL`：
  task 级主文档标识（多文件任务取首文件 document_id；NULL=存量行）。
- FK 仅逻辑关联（不加物理外键）：项目基线风格为原生 SQL 无物理 FK，
  且 asset 生命周期独立于 task 行删除，索引 + 应用层保证即可。
- downgrade 只删新表/新列，不动任何存量数据列（数据不丢）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"SHOW COLUMNS FROM `{table}`"))
    return {str(r[0]) for r in rows}


def _table_names(conn) -> set[str]:
    rows = conn.execute(sa.text("SHOW TABLES"))
    return {str(r[0]) for r in rows}


def upgrade() -> None:
    conn = op.get_bind()

    # ---------- 1) 新表 import_source_asset ----------
    if "import_source_asset" not in _table_names(conn):
        conn.execute(sa.text(
            "CREATE TABLE `import_source_asset` ("
            "  `asset_id` VARCHAR(40) NOT NULL COMMENT '资产 ID（uuid 短 id）',"
            "  `task_id` VARCHAR(64) NOT NULL COMMENT '所属导入任务（逻辑关联 knowledge_import_task.task_id）',"
            "  `file_index` INT NOT NULL COMMENT '文件在任务内的序号（0 起）',"
            "  `bucket` VARCHAR(64) NULL COMMENT 'MinIO bucket',"
            "  `object_key` VARCHAR(255) NULL COMMENT 'MinIO object key',"
            "  `file_name` VARCHAR(255) NULL COMMENT '原始文件名',"
            "  `sha256` CHAR(64) NULL COMMENT '源文件 sha256（上传时计算）',"
            "  `size_bytes` BIGINT NULL COMMENT '文件大小（字节）',"
            "  `mime` VARCHAR(128) NULL COMMENT 'MIME 类型',"
            "  `document_id` VARCHAR(40) NOT NULL COMMENT '文档身份 ID（asset 创建时为每个文件生成 uuid 短 id）',"
            "  `stage` VARCHAR(24) NOT NULL DEFAULT 'queued_parser' COMMENT '冻结词汇：queued_parser/parsing/ir_ready/ingested/failed',"
            "  `retry_count` INT NOT NULL DEFAULT 0 COMMENT '重试次数',"
            "  `execution_epoch` INT NOT NULL DEFAULT 0 COMMENT '执行纪元（每次 CAS 成功 +1，防并发重复推进）',"
            "  `lease_owner` VARCHAR(64) NULL COMMENT '当前租约持有者（worker 标识）',"
            "  `lease_until` DATETIME NULL COMMENT '租约到期时间',"
            "  `parse_fingerprint` CHAR(16) NULL COMMENT '解析指纹（同指纹跳过重复解析）',"
            "  `artifact_ref` VARCHAR(255) NULL COMMENT '解析产物引用（IR/清洗产物）',"
            "  `error` VARCHAR(500) NULL COMMENT '失败原因',"
            "  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',"
            "  PRIMARY KEY (`asset_id`),"
            "  KEY `idx_isa_task` (`task_id`),"
            "  KEY `idx_isa_document` (`document_id`),"
            "  KEY `idx_isa_task_stage` (`task_id`,`stage`)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci "
            "COMMENT='导入源资产（task 1:N 细化，parser job 调度/租约/指纹）'"
        ))

    # ---------- 2) knowledge_import_task additive 加列 document_id ----------
    names = _column_names(conn, "knowledge_import_task")
    if "document_id" not in names:
        conn.execute(sa.text(
            "ALTER TABLE `knowledge_import_task` ADD COLUMN `document_id` VARCHAR(40) NULL "
            "COMMENT 'task 级主文档标识（多文件任务取首文件 document_id；NULL=存量行）' "
            "AFTER `user_id`"
        ))


def downgrade() -> None:
    conn = op.get_bind()

    # 回滚顺序：先删列，再删表（与 upgrade 相反）；只删新表/新列，存量数据不动。
    names = _column_names(conn, "knowledge_import_task")
    if "document_id" in names:
        conn.execute(sa.text(
            "ALTER TABLE `knowledge_import_task` DROP COLUMN `document_id`"
        ))

    if "import_source_asset" in _table_names(conn):
        conn.execute(sa.text("DROP TABLE IF EXISTS `import_source_asset`"))
