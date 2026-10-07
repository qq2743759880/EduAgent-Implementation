"""Publishable quiz metadata, database attempt idempotency, and Mastery V0 state.

Revision ID: 9a0b1c2d3e4f
Revises: d5e6f7a8b9c0

The schema changes are additive. Existing answer rows receive stable opaque
attempt IDs before the unique key is added; their new request hashes and
response snapshots remain NULL because the original requests are unavailable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a0b1c2d3e4f"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return {str(row[0]) for row in op.get_bind().execute(sa.text("SHOW TABLES"))}


def _columns(table: str) -> set[str]:
    return {
        str(row[0])
        for row in op.get_bind().execute(sa.text(f"SHOW COLUMNS FROM `{table}`"))
    }


def _indexes(table: str) -> set[str]:
    return {
        str(row[2])
        for row in op.get_bind().execute(sa.text(f"SHOW INDEX FROM `{table}`"))
    }


def _has_rows(table: str, where: str | None = None) -> bool:
    sql = f"SELECT 1 FROM `{table}`"
    if where:
        sql += f" WHERE {where}"
    sql += " LIMIT 1"
    return op.get_bind().execute(sa.text(sql)).first() is not None


def _add_column(table: str, name: str, ddl: str) -> None:
    if name not in _columns(table):
        op.execute(f"ALTER TABLE `{table}` ADD COLUMN `{name}` {ddl}")


def _drop_column(table: str, name: str) -> None:
    if name in _columns(table):
        op.execute(f"ALTER TABLE `{table}` DROP COLUMN `{name}`")


def upgrade() -> None:
    tables = _tables()
    if "question" not in tables or "quiz_answer_session" not in tables:
        raise RuntimeError("quiz metadata migration requires baseline question tables")

    if "quiz_question_publication" not in tables:
        op.execute(
            "CREATE TABLE `quiz_question_publication` ("
            " `question_id` BIGINT NOT NULL,"
            " `course_id` BIGINT NOT NULL COMMENT 'series_cohort_course.id',"
            " `question_version` VARCHAR(64) NOT NULL,"
            " `subject_code` VARCHAR(32) NOT NULL,"
            " `difficulty` VARCHAR(16) NOT NULL,"
            " `source` VARCHAR(128) NOT NULL,"
            " `review_status` VARCHAR(16) NOT NULL DEFAULT 'DRAFT',"
            " `published_at` DATETIME NULL,"
            " `reviewer_user_id` BIGINT NULL,"
            " `content_authorization_ref` VARCHAR(255) NULL,"
            " `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            " `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
            " PRIMARY KEY (`question_id`),"
            " KEY `idx_quiz_publication_course` (`course_id`,`review_status`,`subject_code`)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        )

    if "quiz_question_kp" not in _tables():
        op.execute(
            "CREATE TABLE `quiz_question_kp` ("
            " `question_id` BIGINT NOT NULL,"
            " `knowledge_code` VARCHAR(64) NOT NULL,"
            " `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            " PRIMARY KEY (`question_id`,`knowledge_code`),"
            " KEY `idx_quiz_kp_code_question` (`knowledge_code`,`question_id`)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        )

    _add_column("quiz_answer_session", "attempt_id", "CHAR(36) NULL")
    _add_column("quiz_answer_session", "request_hash", "CHAR(64) NULL")
    _add_column("quiz_answer_session", "response_json", "JSON NULL")
    _add_column("quiz_answer_session", "course_id", "BIGINT NULL")
    _add_column("quiz_answer_session", "question_version", "VARCHAR(64) NULL")
    _add_column("quiz_answer_session", "knowledge_codes_snapshot", "JSON NULL")
    _add_column("quiz_answer_session", "hint_used", "TINYINT(1) NOT NULL DEFAULT 0")
    _add_column("quiz_answer_session", "redo_of_attempt_id", "CHAR(36) NULL")

    # Existing rows predate idempotency. Repair null and duplicate candidate IDs
    # before constraining every populated (user, attempt) pair to one answer.
    op.execute(
        "CREATE TEMPORARY TABLE `_quiz_attempt_duplicate_rows` AS "
        "SELECT q.id FROM quiz_answer_session q JOIN ("
        " SELECT user_id, attempt_id, MIN(id) AS keep_id "
        " FROM quiz_answer_session WHERE attempt_id IS NOT NULL "
        " GROUP BY user_id, attempt_id HAVING COUNT(*) > 1"
        ") d ON d.user_id=q.user_id AND d.attempt_id=q.attempt_id "
        "WHERE q.id<>d.keep_id"
    )
    op.execute(
        "UPDATE quiz_answer_session q JOIN `_quiz_attempt_duplicate_rows` d ON d.id=q.id "
        "SET q.attempt_id=UUID()"
    )
    op.execute("DROP TEMPORARY TABLE `_quiz_attempt_duplicate_rows`")
    op.execute("UPDATE quiz_answer_session SET attempt_id=UUID() WHERE attempt_id IS NULL")
    # Keep the column nullable so the previous application can be redeployed
    # without breaking inserts. The new quiz service requires UUID attempt IDs;
    # nullable legacy writes remain outside the idempotency guarantee.
    if "uq_quiz_answer_user_attempt" not in _indexes("quiz_answer_session"):
        op.execute(
            "ALTER TABLE quiz_answer_session ADD UNIQUE KEY "
            "`uq_quiz_answer_user_attempt` (`user_id`,`attempt_id`)"
        )
    if "idx_quiz_answer_user_course_time" not in _indexes("quiz_answer_session"):
        op.execute(
            "ALTER TABLE quiz_answer_session ADD KEY `idx_quiz_answer_user_course_time` "
            "(`user_id`,`course_id`,`created_at`)"
        )

    if "user_kp_mastery" not in _tables():
        op.execute(
            "CREATE TABLE `user_kp_mastery` ("
            " `user_id` BIGINT UNSIGNED NOT NULL,"
            " `course_id` BIGINT NOT NULL,"
            " `knowledge_code` VARCHAR(64) NOT NULL,"
            " `status` VARCHAR(16) NOT NULL,"
            " `confidence` DECIMAL(7,6) NOT NULL DEFAULT 0,"
            " `weighted_accuracy` DECIMAL(7,6) NULL,"
            " `scored_evidence_count` INT NOT NULL DEFAULT 0,"
            " `unique_question_count` INT NOT NULL DEFAULT 0,"
            " `reason_json` JSON NOT NULL,"
            " `evidence_ids_json` JSON NOT NULL,"
            " `next_review_at` DATETIME NULL,"
            " `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
            " PRIMARY KEY (`user_id`,`course_id`,`knowledge_code`),"
            " KEY `idx_user_kp_mastery_due` (`user_id`,`next_review_at`)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        )


def downgrade() -> None:
    tables = _tables()

    # MySQL DDL autocommits, so check every destructive target before dropping
    # anything. Existing answer rows are retained; new idempotency/evidence and
    # publication state must be removed explicitly before the schema rollback.
    destructive = []
    for table in ("user_kp_mastery", "quiz_question_kp", "quiz_question_publication"):
        if table in tables and _has_rows(table):
            destructive.append(table)
    if "quiz_answer_session" in tables:
        columns = _columns("quiz_answer_session")
        evidence_columns = (
            "attempt_id", "request_hash", "response_json", "course_id", "question_version",
            "knowledge_codes_snapshot", "redo_of_attempt_id",
        )
        predicates = [f"`{name}` IS NOT NULL" for name in evidence_columns if name in columns]
        if "hint_used" in columns:
            predicates.append("`hint_used` <> 0")
        if predicates and _has_rows("quiz_answer_session", " OR ".join(predicates)):
            destructive.append(
                "quiz_answer_session new evidence columns "
                "(attempt_id/request_hash/response/course/KP/hint/redo)"
            )
    if destructive:
        raise RuntimeError(
            "Cannot downgrade quiz/mastery migration while new-only data exists: "
            + ", ".join(destructive)
            + ". Export or remove that data explicitly before retrying."
        )

    if "user_kp_mastery" in tables:
        op.execute("DROP TABLE `user_kp_mastery`")
    if "quiz_question_kp" in tables:
        op.execute("DROP TABLE `quiz_question_kp`")
    if "quiz_question_publication" in tables:
        op.execute("DROP TABLE `quiz_question_publication`")

    if "quiz_answer_session" in tables:
        indexes = _indexes("quiz_answer_session")
        for index in ("idx_quiz_answer_user_course_time", "uq_quiz_answer_user_attempt"):
            if index in indexes:
                op.execute(f"ALTER TABLE `quiz_answer_session` DROP INDEX `{index}`")
        for column in (
            "redo_of_attempt_id",
            "hint_used",
            "knowledge_codes_snapshot",
            "question_version",
            "course_id",
            "response_json",
            "request_hash",
            "attempt_id",
        ):
            _drop_column("quiz_answer_session", column)
