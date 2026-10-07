"""Additive durable operator task table; independent from playable video rows."""
TASK_DDL = """
CREATE TABLE IF NOT EXISTS video_knowledge_task (
 id CHAR(32) NOT NULL PRIMARY KEY,
 session_id BIGINT NOT NULL,
 bvid VARCHAR(32) NOT NULL,
 page INT NOT NULL,
 transcript_mode VARCHAR(16) NOT NULL,
 created_by BIGINT NOT NULL,
 status VARCHAR(32) NOT NULL DEFAULT 'queued',
 stage VARCHAR(32) NOT NULL DEFAULT 'acquiring',
 attempt INT NOT NULL DEFAULT 0,
 data_json LONGTEXT NOT NULL,
 error_code VARCHAR(80) NULL,
 error_message VARCHAR(512) NULL,
 reviewed_by BIGINT NULL,
 reviewed_at DATETIME(6) NULL,
 lease_token CHAR(32) NULL,
 lease_expires_at DATETIME(6) NULL,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
 KEY idx_video_task_queue (status, created_at),
 KEY idx_video_task_session (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""
