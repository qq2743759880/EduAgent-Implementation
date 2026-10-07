"""Durable, leased Video Knowledge production tasks in the existing EDU MySQL."""
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.domains.video_learning.task_schema import TASK_DDL
    op.execute(TASK_DDL)


def downgrade() -> None:
    raise RuntimeError("Keep auditable production task history; archive explicitly before removing this table")
