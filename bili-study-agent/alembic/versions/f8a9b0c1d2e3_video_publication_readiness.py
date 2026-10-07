"""Retain previous approved video knowledge until new RAG is ready."""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("video_learning_publication")}
    additions = {
        "rag_status": "VARCHAR(16) NOT NULL DEFAULT 'ready'",
        "previous_publication_id": "BIGINT UNSIGNED NULL",
        "activated_at": "DATETIME(6) NULL",
    }
    for name, definition in additions.items():
        if name not in columns:
            op.execute(f"ALTER TABLE video_learning_publication ADD COLUMN {name} {definition}")


def downgrade():
    raise RuntimeError("Preserve publication readiness and lineage; revert code without deleting history")
