-- task-S1 全流程 HITL 护栏审计表
-- 对齐：Claude 解释→提议→同意→行动 透明护栏 + Codex auto-review（3 连续拒绝熔断）
-- 落库字段覆盖 AC2 四步审计：explain_text / propose_text / operator / trace_id，用户界面可见。
--
-- 部署前执行（目标库已有业务库 edu）：
--   mysql -u<user> -p edu < refactor_sql/task-S1-create-hitl-approval.sql
-- 重复执行安全（IF NOT EXISTS）。
--
-- 注意：MysqlHitlStore 的查询带 `yn=1` 软删过滤，故本表必须含 yn 列。
CREATE TABLE IF NOT EXISTS `hitl_approval` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `action_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '护栏动作唯一 ID（幂等/续审键）',
  `action_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'write_file|exec_command|network_access|refund',
  `target` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '动作目标（文件/命令/URL/订单）',
  `params_json` mediumtext COLLATE utf8mb4_unicode_ci COMMENT '动作参数 JSON',
  `risk_level` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'L2' COMMENT 'L1|L2|L3',
  `status` enum('pending','approved','rejected','executed','escalated') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT 'AC1~AC4 状态机',
  `explain_text` text COLLATE utf8mb4_unicode_ci COMMENT 'AC2 解释文本（用户可见）',
  `propose_text` text COLLATE utf8mb4_unicode_ci COMMENT 'AC2 提议执行方案（用户可见）',
  `operator` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '触发/待审批操作者标识',
  `approver` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '批准者（人工/管理员）',
  `trace_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '链路 trace id',
  `ai_verdict` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'approve|reject|escalate|breaker',
  `ai_reason` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'AI 审查理由',
  `ai_confidence` decimal(3,2) DEFAULT NULL COMMENT 'AI 审查置信度 0.00~1.00',
  `reject_count` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '同动作类型连续拒绝计数（熔断依据）',
  `server_id` bigint(20) unsigned DEFAULT NULL COMMENT 'MCP 写工具来源 server（执行阶段定位）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间（超时 T0）',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `yn` tinyint(4) NOT NULL DEFAULT '1' COMMENT '软删除 1=有效 0=已删',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_hitl_action` (`action_id`),
  KEY `idx_hitl_type_status_created` (`action_type`,`status`,`created_at`),
  KEY `idx_hitl_trace` (`trace_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='task-S1 全流程 HITL 审批审计表';
