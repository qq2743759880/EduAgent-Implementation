-- task04: knowledge_import_task 新表 + 通用 task_execution 任务表
-- 执行时间: 2026-08-17

CREATE TABLE IF NOT EXISTS knowledge_import_task (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL COMMENT '任务唯一标识',
    task_type VARCHAR(32) NOT NULL DEFAULT 'import' COMMENT '任务类型: import/reimport/delete',
    tenant_id VARCHAR(100) NOT NULL COMMENT '租户ID',
    visibility VARCHAR(20) NOT NULL DEFAULT 'private' COMMENT '可见性: private/public',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/running/succeeded/failed',
    total_chunks INT NOT NULL DEFAULT 0 COMMENT '总chunk数',
    imported_chunks INT NOT NULL DEFAULT 0 COMMENT '已导入chunk数',
    source_files JSON NULL COMMENT '源文件元数据 [{object_key,file_name,file_size,content_type}]',
    error TEXT NULL COMMENT '错误信息',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    UNIQUE KEY uk_knowledge_task_id (task_id),
    KEY idx_knowledge_task_tenant (tenant_id, status),
    KEY idx_knowledge_task_status (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识导入任务表（RAG管道双写）';

CREATE TABLE IF NOT EXISTS task_execution (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_code VARCHAR(64) NOT NULL COMMENT '任务编码',
    task_type VARCHAR(32) NOT NULL COMMENT '任务类型',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/succeeded/failed',
    tenant_id VARCHAR(100) NULL COMMENT '租户ID（可选）',
    progress_json JSON NULL COMMENT '进度详情JSON',
    params_json JSON NULL COMMENT '输入参数JSON',
    result_json JSON NULL COMMENT '输出结果JSON',
    error TEXT NULL COMMENT '错误信息',
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_task_execution_code (task_code),
    KEY idx_task_execution_type (task_type, status),
    KEY idx_task_execution_status (status, created_at),
    KEY idx_task_execution_tenant (tenant_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='通用任务执行表（durable execution）';