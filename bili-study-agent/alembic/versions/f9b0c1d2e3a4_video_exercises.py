"""Add immutable video exercise packages; reuse existing quiz publication tables."""
from alembic import op
from app.domains.video_learning.schema import EXERCISE_DDL

revision = 'f9b0c1d2e3a4'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(EXERCISE_DDL)


def downgrade():
    # Preserve published questions/history on code rollback; no automatic data deletion.
    pass
