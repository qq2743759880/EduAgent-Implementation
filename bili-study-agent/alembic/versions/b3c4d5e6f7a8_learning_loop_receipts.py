"""Durable Pilot learning loop and review action receipts.

Revision ID: b3c4d5e6f7a8
Revises: 9a0b1c2d3e4f
"""
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "9a0b1c2d3e4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE `learning_loop` ("
        "`id` CHAR(36) NOT NULL PRIMARY KEY,"
        "`user_id` BIGINT NOT NULL,"
        "`course_id` BIGINT NOT NULL COMMENT 'series_cohort_course.id',"
        "`session_id` BIGINT NOT NULL COMMENT 'series_cohort_session.id',"
        "`status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',"
        "`activated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),"
        "`updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),"
        "KEY `idx_learning_loop_user_time` (`user_id`,`activated_at`),"
        "KEY `idx_learning_loop_status_time` (`status`,`activated_at`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    )
    op.execute(
        "CREATE TABLE `learning_next_action` ("
        "`id` BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,"
        "`learning_loop_id` CHAR(36) NOT NULL,"
        "`user_id` BIGINT NOT NULL,"
        "`quiz_answer_session_id` BIGINT UNSIGNED NOT NULL,"
        "`kind` VARCHAR(32) NOT NULL,"
        "`status` VARCHAR(16) NOT NULL,"
        "`due_at` DATETIME(6) NULL,"
        "`executed_at` DATETIME(6) NULL,"
        "`created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),"
        "UNIQUE KEY `uq_learning_action_evidence_kind` (`learning_loop_id`,`quiz_answer_session_id`,`kind`),"
        "KEY `idx_learning_action_due` (`status`,`due_at`),"
        "CONSTRAINT `fk_learning_action_loop` FOREIGN KEY (`learning_loop_id`) REFERENCES `learning_loop` (`id`),"
        "CONSTRAINT `fk_learning_action_answer` FOREIGN KEY (`quiz_answer_session_id`) REFERENCES `quiz_answer_session` (`id`)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    )
    op.execute("ALTER TABLE `quiz_answer_session` ADD COLUMN `learning_loop_id` "
               "CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL")
    op.execute("ALTER TABLE `quiz_answer_session` ADD KEY `idx_quiz_answer_loop` (`learning_loop_id`)")


def downgrade() -> None:
    op.execute("ALTER TABLE `quiz_answer_session` DROP INDEX `idx_quiz_answer_loop`")
    op.execute("ALTER TABLE `quiz_answer_session` DROP COLUMN `learning_loop_id`")
    op.execute("DROP TABLE `learning_next_action`")
    op.execute("DROP TABLE `learning_loop`")
