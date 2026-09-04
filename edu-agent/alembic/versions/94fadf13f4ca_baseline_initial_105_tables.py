"""baseline: initial 105 tables

Revision ID: 94fadf13f4ca
Revises:
Create Date: 2026-08-14 21:48:19.942446

说明：
- 项目建表用原生 SQL（无 ORM），故 baseline 迁移 = 执行 mysqldump 导出的
  初始 105 表 DDL（alembic/baseline_schema.sql）。
- 新环境部署：`alembic upgrade head` 即建全部表。
- 现有环境：`alembic stamp head` 标记当前 DB 已就绪（不重复建表）。
- 后续 DDL 变更请新增 revision（`alembic revision -m "..."` 后写 upgrade/downgrade）。
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94fadf13f4ca'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _run_schema_sql(conn) -> None:
    """执行 baseline DDL（关闭 FK 检查避免建表顺序问题）。

    用独立 pymysql 连接（含 MULTI_STATEMENTS）执行整个 SQL 文件，
    SQL 头尾自带 SET FOREIGN_KEY_CHECKS。
    """
    import pymysql
    from pymysql.constants import CLIENT

    url = str(conn.engine.url)
    # 从连接引擎拿回配置
    eng = conn.engine
    raw = pymysql.connect(
        host=eng.url.host or "localhost",
        port=eng.url.port or 3306,
        user=eng.url.username or "root",
        password=eng.url.password or "",
        database=eng.url.database or "edu",
        charset="utf8mb4",
        client_flag=CLIENT.MULTI_STATEMENTS,
        autocommit=True,
    )
    try:
        sql_file = Path(__file__).resolve().parent.parent / "baseline_schema.sql"
        ddl = sql_file.read_text(encoding="utf-8")
        with raw.cursor() as cur:
            cur.execute(ddl)
        raw.commit()
    finally:
        raw.close()


def upgrade() -> None:
    """执行初始 105 表 DDL。"""
    conn = op.get_bind()
    _run_schema_sql(conn)


def downgrade() -> None:
    """回滚：删除全部业务表（数据销毁，仅文档/测试用）。"""
    conn = op.get_bind()
    conn.execute(sa.text("SET FOREIGN_KEY_CHECKS=0"))
    for row in conn.execute(sa.text("SHOW TABLES")):
        table = list(row)[0]
        conn.execute(sa.text(f"DROP TABLE IF EXISTS `{table}`"))
    conn.execute(sa.text("SET FOREIGN_KEY_CHECKS=1"))
