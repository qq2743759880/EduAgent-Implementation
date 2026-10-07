"""Pure DDL shared by the publication runtime and its additive migration."""

PUBLICATION_DDL = """
CREATE TABLE IF NOT EXISTS video_learning_publication (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 video_id BIGINT NOT NULL,
 artifact_id CHAR(64) NOT NULL,
 artifact_sha256 CHAR(64) NOT NULL,
 object_sha256 CHAR(64) NOT NULL,
 bucket VARCHAR(128) NOT NULL,
 object_key VARCHAR(512) NOT NULL,
 size_bytes BIGINT NOT NULL,
 rag_status VARCHAR(16) NOT NULL DEFAULT 'ready',
 previous_publication_id BIGINT UNSIGNED NULL,
 activated_at DATETIME(6) NULL,
 published_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 UNIQUE KEY uq_video_artifact (video_id, artifact_sha256),
 KEY idx_video_publication (video_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

EXERCISE_DDL = """
CREATE TABLE IF NOT EXISTS video_learning_exercise (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 video_id BIGINT NOT NULL,
 session_id BIGINT NOT NULL,
 generation CHAR(64) NOT NULL,
 artifact_sha256 CHAR(64) NOT NULL,
 bank_id BIGINT NOT NULL,
 question_count INT NOT NULL,
 package_sha256 CHAR(64) NOT NULL,
 package_json LONGTEXT NOT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 UNIQUE KEY uq_video_exercise_version (video_id,artifact_sha256),
 UNIQUE KEY uq_video_exercise_bank (bank_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""
