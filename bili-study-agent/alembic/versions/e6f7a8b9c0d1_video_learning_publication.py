"""Append-only references to immutable native video learning artifacts."""
from alembic import op

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.domains.video_learning.schema import PUBLICATION_DDL
    op.execute(PUBLICATION_DDL)


def downgrade() -> None:
    raise RuntimeError("Publication history is append-only; archive it explicitly before rollback")
