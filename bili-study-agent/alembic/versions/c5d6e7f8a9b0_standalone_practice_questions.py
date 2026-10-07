"""Explicit public question-bank publications may be independent of a course."""
from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8a9b0"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("quiz_question_publication", "course_id", existing_type=sa.BigInteger(), nullable=True)


def downgrade():
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM quiz_question_publication WHERE course_id IS NULL")).scalar()
    if count:
        raise RuntimeError("Standalone publications exist; preserve or explicitly rebind them before changing nullability")
    op.alter_column("quiz_question_publication", "course_id", existing_type=sa.BigInteger(), nullable=False)
