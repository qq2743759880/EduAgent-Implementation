-- Current EduAgent schema-only installation snapshot. NO rows, credentials or AUTO_INCREMENT counters.

-- Install ONLY into an empty, independently configured database.

SET NAMES utf8mb4;

SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE `_rwtest` (
  `id` int(11) NOT NULL,
  `v` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `channel_commission_bill` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `bill_no` varchar(64) NOT NULL,
  `channel_id` bigint(20) NOT NULL,
  `settle_period` varchar(32) NOT NULL,
  `bill_status` varchar(32) NOT NULL COMMENT '枚举：pending,approved,paid',
  `order_count` int(11) NOT NULL,
  `commission_amount` decimal(12,2) NOT NULL,
  `approver_user_id` bigint(20) DEFAULT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `settled_at` datetime DEFAULT NULL,
  `paid_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_channel_commission_bill_no` (`institution_id`,`bill_no`),
  KEY `fk_channel_commission_bill_channel` (`channel_id`),
  KEY `fk_channel_commission_bill_approver` (`approver_user_id`),
  CONSTRAINT `fk_channel_commission_bill_approver` FOREIGN KEY (`approver_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_channel_commission_bill_channel` FOREIGN KEY (`channel_id`) REFERENCES `dim_channel` (`id`),
  CONSTRAINT `fk_channel_commission_bill_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='渠道返佣账单表';

CREATE TABLE `channel_commission_item` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `bill_id` bigint(20) NOT NULL,
  `order_item_id` bigint(20) NOT NULL,
  `commission_rate` decimal(8,4) NOT NULL,
  `base_amount` decimal(12,2) NOT NULL,
  `commission_amount` decimal(12,2) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_channel_commission_item_order_item` (`bill_id`,`order_item_id`),
  KEY `fk_channel_commission_item_institution` (`institution_id`),
  KEY `fk_channel_commission_item_order_item` (`order_item_id`),
  CONSTRAINT `fk_channel_commission_item_bill` FOREIGN KEY (`bill_id`) REFERENCES `channel_commission_bill` (`id`),
  CONSTRAINT `fk_channel_commission_item_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_channel_commission_item_order_item` FOREIGN KEY (`order_item_id`) REFERENCES `order_item` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='渠道返佣明细表';

CREATE TABLE `chat_message` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '自增主键（内部用）',
  `message_id` varchar(64) NOT NULL COMMENT '对外消息 ID（m_xxx 短 uuid）',
  `session_id` varchar(64) NOT NULL COMMENT '关联 chat_session.session_id',
  `user_id` bigint(20) NOT NULL COMMENT '冗余所属用户，方便按 (user_id, created_at) 全局查聊天历史/合规',
  `role` varchar(16) NOT NULL COMMENT 'user / assistant / system',
  `content` mediumtext NOT NULL COMMENT '消息正文（assistant 为最终合并回答）',
  `rag_query_rewrite` varchar(1024) DEFAULT NULL COMMENT 'HyDE/改写后的查询',
  `rag_retrieved_count` int(11) DEFAULT NULL COMMENT '检索召回 doc 数量（断崖前）',
  `rag_final_count` int(11) DEFAULT NULL COMMENT '重排+断崖后喂给 LLM 的 doc 数量',
  `rag_docs_json` mediumtext COMMENT 'RetrievedDoc[] JSON（前端点击引用）',
  `rag_error` varchar(1024) DEFAULT NULL COMMENT '降级说明 / 链路异常摘要',
  `latency_ms` int(11) DEFAULT NULL COMMENT '整轮耗时毫秒（包含检索+生成+落库）',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `mcp_tool_calls_json` mediumtext COMMENT 'P8: MCP 工具调用记录 JSON 数组 [{call_id,tool_name,args_summary,status,latency_ms,result_summary}]',
  `mcp_called_count` int(11) DEFAULT NULL COMMENT 'P8: 本轮 MCP 工具被触发的次数（冗余统计）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_chat_message_message_id` (`message_id`),
  KEY `idx_chat_message_session_created` (`session_id`,`created_at`),
  KEY `idx_chat_message_user_created` (`user_id`,`created_at`),
  KEY `idx_chat_message_role_created` (`role`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P2 RAG 聊天消息（轮次级落库 + RAG 审计字段）';

CREATE TABLE `chat_session` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '自增主键（内部用）',
  `session_id` varchar(64) NOT NULL COMMENT '对外会话 ID（s_xxx 短 uuid）',
  `user_id` bigint(20) NOT NULL COMMENT '所属用户 ID，对应 sys_user.id',
  `title` varchar(128) NOT NULL COMMENT '会话标题：首条问题前 30 字回填',
  `visibility` varchar(16) NOT NULL DEFAULT 'private' COMMENT '预留协作场景：private/shared',
  `message_count` int(11) NOT NULL DEFAULT '0' COMMENT '消息条数（冗余计数，避免实时 COUNT）',
  `last_message_at` datetime(3) DEFAULT NULL COMMENT '最后对话时间，用于列表排序',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  `yn` tinyint(4) NOT NULL DEFAULT '1' COMMENT '软删标记 1=有效 0=删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_chat_session_session_id` (`session_id`),
  KEY `idx_chat_session_user_lastmsg` (`user_id`,`last_message_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P2 RAG 会话元数据（一对一用户，可多个会话）';

CREATE TABLE `coding_challenge` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `level_code` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'L2',
  `lang_code` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'python / javascript / java / cpp',
  `prompt` varchar(2000) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '题目描述（输入输出要求）',
  `starter_code` text COLLATE utf8mb4_unicode_ci COMMENT '初始模板代码（函数签名等）',
  `test_cases_json` json NOT NULL COMMENT '[{"input":"1 2","expected":"3","is_hidden":false}, ...]',
  `tags_json` json DEFAULT NULL COMMENT '标签数组',
  `points` int(10) unsigned NOT NULL DEFAULT '100',
  `yn` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P5 编程挑战题库';

CREATE TABLE `coding_submission` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) unsigned NOT NULL,
  `challenge_id` bigint(20) unsigned NOT NULL,
  `lang_code` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code_text` mediumtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `run_mode` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'RUN=只跑非隐藏用例；SUBMIT=跑全量',
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Pending' COMMENT 'Pending/Running/Pass/PartialFail/CompileError/RuntimeError/SandboxError',
  `pass_count` int(10) unsigned NOT NULL DEFAULT '0',
  `total_count` int(10) unsigned NOT NULL DEFAULT '0',
  `results_json` json DEFAULT NULL COMMENT '各用例结果列表',
  `stdout_text` text COLLATE utf8mb4_unicode_ci,
  `stderr_text` text COLLATE utf8mb4_unicode_ci,
  `duration_ms` int(10) unsigned DEFAULT NULL,
  `sandbox_provider` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'PISTON_REAL / PISTON_MOCK / LOCAL_MOCK',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_challenge` (`user_id`,`challenge_id`,`created_at`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P5 编程提交/运行记录';

CREATE TABLE `cohort_discussion_post` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `topic_id` bigint(20) NOT NULL,
  `parent_post_id` bigint(20) DEFAULT NULL,
  `author_user_id` bigint(20) NOT NULL,
  `content_text` text NOT NULL,
  `like_count` int(11) NOT NULL DEFAULT '0',
  `reply_count` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_cohort_discussion_post_institution` (`institution_id`),
  KEY `fk_cohort_discussion_post_topic` (`topic_id`),
  KEY `fk_cohort_discussion_post_parent` (`parent_post_id`),
  KEY `fk_cohort_discussion_post_author` (`author_user_id`),
  CONSTRAINT `fk_cohort_discussion_post_author` FOREIGN KEY (`author_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_cohort_discussion_post_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_cohort_discussion_post_parent` FOREIGN KEY (`parent_post_id`) REFERENCES `cohort_discussion_post` (`id`),
  CONSTRAINT `fk_cohort_discussion_post_topic` FOREIGN KEY (`topic_id`) REFERENCES `cohort_discussion_topic` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='班次讨论回复表';

CREATE TABLE `cohort_discussion_topic` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `cohort_id` bigint(20) NOT NULL,
  `creator_user_id` bigint(20) NOT NULL,
  `topic_title` varchar(255) NOT NULL,
  `content_text` text NOT NULL,
  `is_pinned` tinyint(4) NOT NULL DEFAULT '0' COMMENT '枚举：0,1',
  `is_closed` tinyint(4) NOT NULL DEFAULT '0' COMMENT '枚举：0,1',
  `view_count` int(11) NOT NULL DEFAULT '0',
  `reply_count` int(11) NOT NULL DEFAULT '0',
  `last_reply_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_cohort_discussion_topic_institution` (`institution_id`),
  KEY `fk_cohort_discussion_topic_cohort` (`cohort_id`),
  KEY `fk_cohort_discussion_topic_creator` (`creator_user_id`),
  CONSTRAINT `fk_cohort_discussion_topic_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`),
  CONSTRAINT `fk_cohort_discussion_topic_creator` FOREIGN KEY (`creator_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_cohort_discussion_topic_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='班次讨论主题表';

CREATE TABLE `cohort_review` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `cohort_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `review_no` varchar(64) NOT NULL,
  `score_overall` tinyint(4) NOT NULL,
  `score_teacher` tinyint(4) NOT NULL,
  `score_content` tinyint(4) NOT NULL,
  `score_service` tinyint(4) NOT NULL,
  `review_tags` json DEFAULT NULL,
  `review_content` text,
  `anonymous_flag` tinyint(4) NOT NULL DEFAULT '0' COMMENT '枚举：0,1',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `reviewed_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cohort_review_no` (`institution_id`,`review_no`),
  UNIQUE KEY `uk_cohort_review_once` (`cohort_id`,`student_id`),
  KEY `fk_cohort_review_user` (`user_id`),
  KEY `fk_cohort_review_student` (`student_id`),
  CONSTRAINT `fk_cohort_review_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`),
  CONSTRAINT `fk_cohort_review_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_cohort_review_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_cohort_review_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='班次评价表';

CREATE TABLE `community_comment` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `post_id` bigint(20) unsigned NOT NULL,
  `author_id` bigint(20) unsigned NOT NULL,
  `author_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `parent_id` bigint(20) unsigned DEFAULT NULL COMMENT '父评论，NULL=一楼',
  `reply_to_id` bigint(20) unsigned DEFAULT NULL COMMENT '回复的目标评论 id（@）',
  `content_md` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `like_count` int(10) unsigned NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_post` (`post_id`,`created_at` DESC),
  KEY `idx_author` (`author_id`,`created_at` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P6 社区评论/回复';

CREATE TABLE `community_post` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `board_code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'general' COMMENT '版块：english/math/programming/general',
  `author_id` bigint(20) unsigned NOT NULL,
  `author_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_md` mediumtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `tags_json` json DEFAULT NULL COMMENT '["单词学习","编程入门"]',
  `is_pinned` tinyint(1) NOT NULL DEFAULT '0',
  `is_locked` tinyint(1) NOT NULL DEFAULT '0',
  `view_count` int(10) unsigned NOT NULL DEFAULT '0',
  `like_count` int(10) unsigned NOT NULL DEFAULT '0',
  `comment_count` int(10) unsigned NOT NULL DEFAULT '0',
  `favorite_count` int(10) unsigned NOT NULL DEFAULT '0',
  `hot_score` decimal(16,6) NOT NULL DEFAULT '0.000000' COMMENT '（点赞*2+评论*3+收藏*1.5）/ log2(小时+2)',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_board_created` (`board_code`,`created_at` DESC),
  KEY `idx_author` (`author_id`,`created_at` DESC),
  KEY `idx_hot` (`hot_score` DESC),
  KEY `idx_board_pin_hot_created` (`board_code`,`is_pinned`,`hot_score`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P6 社区帖子';

CREATE TABLE `community_react` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) unsigned NOT NULL,
  `target_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'POST / COMMENT',
  `target_id` bigint(20) unsigned NOT NULL,
  `react_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'LIKE / FAVORITE',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_react_user_target` (`user_id`,`target_type`,`target_id`,`react_type`),
  KEY `idx_target` (`target_type`,`target_id`,`react_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P6 社区反应（点赞/收藏）';

CREATE TABLE `consultation_record` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `cohort_id` bigint(20) NOT NULL,
  `consultant_user_id` bigint(20) NOT NULL,
  `source_channel_id` bigint(20) NOT NULL,
  `consult_channel` varchar(32) NOT NULL COMMENT '枚举：phone,online_chat,wechat,offline_visit',
  `contact_mobile` varchar(32) NOT NULL,
  `consult_content` text,
  `consulted_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_consultation_user` (`user_id`),
  KEY `fk_consultation_cohort` (`cohort_id`),
  KEY `fk_consultation_consultant` (`consultant_user_id`),
  KEY `fk_consultation_source_channel` (`source_channel_id`),
  CONSTRAINT `fk_consultation_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`),
  CONSTRAINT `fk_consultation_consultant` FOREIGN KEY (`consultant_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_consultation_source_channel` FOREIGN KEY (`source_channel_id`) REFERENCES `dim_channel` (`id`),
  CONSTRAINT `fk_consultation_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='咨询记录表';

CREATE TABLE `coupon` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) DEFAULT NULL,
  `issuer_scope` varchar(32) NOT NULL COMMENT '枚举：platform,institution',
  `coupon_code` varchar(64) NOT NULL,
  `coupon_name` varchar(128) NOT NULL,
  `coupon_type` varchar(32) NOT NULL COMMENT '枚举：cash,discount,trial,gift',
  `discount_amount` decimal(12,2) DEFAULT NULL,
  `discount_rate` decimal(8,4) DEFAULT NULL,
  `threshold_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `total_count` int(11) NOT NULL,
  `per_user_limit` int(11) NOT NULL DEFAULT '1',
  `receive_count` int(11) NOT NULL DEFAULT '0',
  `used_count` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `valid_from` datetime NOT NULL,
  `valid_to` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_coupon_code` (`coupon_code`),
  KEY `fk_coupon_institution` (`institution_id`),
  CONSTRAINT `fk_coupon_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='优惠券主表';

CREATE TABLE `coupon_category_rel` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `coupon_id` bigint(20) NOT NULL,
  `category_id` bigint(20) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_coupon_category_rel` (`coupon_id`,`category_id`),
  KEY `fk_coupon_category_rel_category` (`category_id`),
  CONSTRAINT `fk_coupon_category_rel_category` FOREIGN KEY (`category_id`) REFERENCES `dim_course_category` (`id`),
  CONSTRAINT `fk_coupon_category_rel_coupon` FOREIGN KEY (`coupon_id`) REFERENCES `coupon` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='优惠券分类适用范围关系表';

CREATE TABLE `coupon_receive_record` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `coupon_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `receive_no` varchar(64) NOT NULL,
  `receive_source` varchar(32) NOT NULL COMMENT '枚举：coupon_center,activity_page,series_detail,order_settlement,consultation',
  `receive_status` varchar(32) NOT NULL COMMENT '枚举：unused,used,expired',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `received_at` datetime NOT NULL,
  `used_at` datetime DEFAULT NULL,
  `expired_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_coupon_receive_record_no` (`receive_no`),
  KEY `idx_coupon_receive_record_user_coupon` (`user_id`,`coupon_id`),
  KEY `fk_coupon_receive_record_coupon` (`coupon_id`),
  CONSTRAINT `fk_coupon_receive_record_coupon` FOREIGN KEY (`coupon_id`) REFERENCES `coupon` (`id`),
  CONSTRAINT `fk_coupon_receive_record_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='领券记录表';

CREATE TABLE `coupon_series_rel` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `coupon_id` bigint(20) NOT NULL,
  `series_id` bigint(20) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_coupon_series_rel` (`coupon_id`,`series_id`),
  KEY `fk_coupon_series_rel_series` (`series_id`),
  CONSTRAINT `fk_coupon_series_rel_coupon` FOREIGN KEY (`coupon_id`) REFERENCES `coupon` (`id`),
  CONSTRAINT `fk_coupon_series_rel_series` FOREIGN KEY (`series_id`) REFERENCES `series` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='优惠券课程系列适用范围关系表';

CREATE TABLE `course_review` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `series_id` bigint(20) NOT NULL COMMENT '课程系列 ID',
  `user_id` bigint(20) NOT NULL COMMENT '评价用户 ID',
  `rating` tinyint(4) NOT NULL COMMENT '评分 1~5',
  `content` varchar(2000) DEFAULT NULL COMMENT '评价内容',
  `yn` tinyint(4) NOT NULL DEFAULT '1' COMMENT '有效标记：1=有效 0=软删',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_course_review_series_user` (`series_id`,`user_id`),
  KEY `idx_course_review_series` (`series_id`,`yn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程系列评价表';

CREATE TABLE `dim_channel` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `channel_category_code` varchar(64) NOT NULL,
  `channel_category_name` varchar(64) NOT NULL,
  `channel_code` varchar(64) NOT NULL,
  `channel_name` varchar(64) NOT NULL,
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dim_channel_code` (`channel_category_code`,`channel_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机构招生渠道维表';

CREATE TABLE `dim_course_category` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `parent_id` bigint(20) DEFAULT NULL,
  `category_code` varchar(64) NOT NULL,
  `category_name` varchar(128) NOT NULL,
  `category_level` tinyint(4) NOT NULL,
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dim_course_category_code` (`category_code`),
  KEY `fk_dim_course_category_parent` (`parent_id`),
  CONSTRAINT `fk_dim_course_category_parent` FOREIGN KEY (`parent_id`) REFERENCES `dim_course_category` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程分类维表';

CREATE TABLE `dim_education_level` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `level_code` varchar(64) NOT NULL,
  `level_name` varchar(64) NOT NULL,
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dim_education_level_code` (`level_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学历层次维表';

CREATE TABLE `dim_grade` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `parent_id` bigint(20) DEFAULT NULL,
  `grade_code` varchar(64) NOT NULL,
  `grade_name` varchar(64) NOT NULL,
  `grade_type` varchar(16) NOT NULL COMMENT '枚举：stage,grade',
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dim_grade_code` (`grade_code`),
  KEY `fk_dim_grade_parent` (`parent_id`),
  CONSTRAINT `fk_dim_grade_parent` FOREIGN KEY (`parent_id`) REFERENCES `dim_grade` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学业层级维表';

CREATE TABLE `dim_learner_identity` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `identity_code` varchar(64) NOT NULL,
  `identity_name` varchar(64) NOT NULL,
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dim_learner_identity_code` (`identity_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学习者身份维表';

CREATE TABLE `dim_learning_goal` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `goal_code` varchar(64) NOT NULL,
  `goal_name` varchar(64) NOT NULL,
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dim_learning_goal_code` (`goal_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学习目标维表';

CREATE TABLE `dim_question_type` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `type_code` varchar(64) NOT NULL,
  `type_name` varchar(64) NOT NULL,
  `objective_flag` tinyint(4) NOT NULL DEFAULT '1' COMMENT '枚举：0,1',
  `auto_marking_flag` tinyint(4) NOT NULL DEFAULT '1' COMMENT '枚举：0,1',
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dim_question_type_code` (`type_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='题型维表';

CREATE TABLE `gamification_badge` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `badge_code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `badge_name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `badge_desc` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `category` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'LEARNING/ACHIEVEMENT/SOCIAL',
  `icon_emoji` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '?️/⚡/? 等',
  `rarity` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'COMMON' COMMENT 'COMMON/RARE/EPIC/LEGENDARY',
  `trigger_rule` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '业务触发规则代码',
  `rule_value` int(10) unsigned NOT NULL DEFAULT '1' COMMENT '触发阈值',
  `reward_points` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '解锁时赠送积分',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `badge_code` (`badge_code`),
  KEY `idx_category` (`category`,`yn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P6 徽章定义';

CREATE TABLE `graph_edge` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `from_node_id` bigint(20) NOT NULL,
  `to_node_id` bigint(20) NOT NULL,
  `rel_type` varchar(32) NOT NULL COMMENT 'CONTAINS(包含) / PREREQUISITE(先修) / RELATED_TO(相关) / TESTS(考核)',
  `weight` decimal(6,4) NOT NULL DEFAULT '1.0000' COMMENT '关系权重 0-1，用于推荐打分',
  `properties_json` json DEFAULT NULL COMMENT '扩展属性',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_graph_edge_rel` (`from_node_id`,`to_node_id`,`rel_type`),
  KEY `idx_graph_edge_to` (`to_node_id`,`rel_type`),
  KEY `idx_graph_edge_type` (`rel_type`,`weight`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P4 学习图谱关系表（PREREQUISITE/CONTAINS/… 有向边）';

CREATE TABLE `graph_node` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `label` varchar(32) NOT NULL COMMENT 'CourseSeries / CourseModule / KnowledgePoint / QuestionTag',
  `code` varchar(64) NOT NULL COMMENT '业务编码：series_code | module_code | KP-xxx | tag_code',
  `name` varchar(128) NOT NULL COMMENT '节点显示名',
  `subject_code` varchar(32) DEFAULT NULL COMMENT '学科 english / programming / math',
  `parent_id` bigint(20) DEFAULT NULL COMMENT '父节点（series → module 的树形归属，也可用 CONTAINS 关系表示，这里冗余方便前端树）',
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `properties_json` json DEFAULT NULL COMMENT '扩展属性：difficulty、alias、description 等',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_graph_node_label_code` (`label`,`code`),
  KEY `idx_graph_node_subject` (`subject_code`),
  KEY `idx_graph_node_parent` (`parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P4 学习图谱节点表（Neo4j 不可用时的 MySQL 替代实现）';

CREATE TABLE `hitl_approval` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `action_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '护栏动作唯一 ID（幂等/续审键）',
  `action_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'write_file|exec_command|network_access|refund',
  `target` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '动作目标（文件/命令/URL/订单）',
  `params_json` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '动作参数 JSON',
  `risk_level` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'L2' COMMENT 'L1|L2|L3',
  `status` enum('pending','approved','rejected','executed','escalated') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT 'AC1~AC4 状态机',
  `explain_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'AC2 解释文本（用户可见）',
  `propose_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'AC2 提议执行方案（用户可见）',
  `operator` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '触发/待审批操作者标识',
  `approver` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '批准者（人工/管理员）',
  `trace_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '链路 trace id',
  `ai_verdict` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'approve|reject|escalate|breaker',
  `ai_reason` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'AI 审查理由',
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

CREATE TABLE `import_source_asset` (
  `asset_id` varchar(40) COLLATE utf8mb4_general_ci NOT NULL COMMENT '资产 ID（uuid 短 id）',
  `task_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `file_index` int(11) NOT NULL COMMENT '文件在任务内的序号（0 起）',
  `bucket` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'MinIO bucket',
  `object_key` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'MinIO object key',
  `file_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '原始文件名',
  `sha256` char(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '源文件 sha256（上传时计算）',
  `size_bytes` bigint(20) DEFAULT NULL COMMENT '文件大小（字节）',
  `mime` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'MIME 类型',
  `document_id` varchar(40) COLLATE utf8mb4_general_ci NOT NULL COMMENT '文档身份 ID（asset 创建时为每个文件生成 uuid 短 id）',
  `stage` varchar(24) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'queued_parser' COMMENT '冻结词汇：queued_parser/parsing/ir_ready/ingested/failed',
  `retry_count` int(11) NOT NULL DEFAULT '0' COMMENT '重试次数',
  `execution_epoch` int(11) NOT NULL DEFAULT '0' COMMENT '执行纪元（每次 CAS 成功 +1，防并发重复推进）',
  `lease_owner` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '当前租约持有者（worker 标识）',
  `lease_until` datetime DEFAULT NULL COMMENT '租约到期时间',
  `parse_fingerprint` char(16) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '解析指纹（同指纹跳过重复解析）',
  `artifact_ref` text COLLATE utf8mb4_general_ci COMMENT '完整 IR artifact 对象引用 JSON',
  `error` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '失败原因',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `dispatched_epoch` int(11) DEFAULT NULL COMMENT '最近成功写入 Redis stream 的 execution_epoch',
  `dlq_epoch` int(11) DEFAULT NULL COMMENT '最近成功持久化到 DLQ 的 failed execution_epoch',
  `vector_status` varchar(24) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'not-produced' COMMENT '向量生成状态',
  `graph_status` varchar(24) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'not-produced' COMMENT '图谱生成状态',
  `graph_retry_needed` tinyint(1) NOT NULL DEFAULT '0' COMMENT '图谱是否待修复',
  PRIMARY KEY (`asset_id`),
  KEY `idx_isa_task` (`task_id`),
  KEY `idx_isa_document` (`document_id`),
  KEY `idx_isa_task_stage` (`task_id`,`stage`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='导入源资产（task 1:N 细化，parser job 调度/租约/指纹）';

CREATE TABLE `knowledge_import_task` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `task_id` varchar(64) NOT NULL COMMENT '任务唯一标识',
  `task_type` varchar(32) NOT NULL DEFAULT 'import' COMMENT '任务类型: import/reimport/delete',
  `tenant_id` varchar(100) NOT NULL COMMENT '租户ID',
  `visibility` varchar(20) NOT NULL DEFAULT 'private' COMMENT '可见性: private/public',
  `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/running/succeeded/failed',
  `user_id` bigint(20) DEFAULT NULL,
  `document_id` varchar(40) DEFAULT NULL COMMENT 'task 级主文档标识（多文件任务取首文件 document_id；NULL=存量行）',
  `total_chunks` int(11) NOT NULL DEFAULT '0' COMMENT '总chunk数',
  `imported_chunks` int(11) NOT NULL DEFAULT '0' COMMENT '已导入chunk数',
  `source_files` json DEFAULT NULL COMMENT '源文件元数据列表 [{object_key,file_name,file_size,content_type}]',
  `error` text COMMENT '错误信息',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `started_at` datetime DEFAULT NULL,
  `finished_at` datetime DEFAULT NULL,
  `security_scope` varchar(64) NOT NULL DEFAULT 'default' COMMENT '权限安全域',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_knowledge_task_id` (`task_id`),
  KEY `idx_knowledge_task_tenant` (`tenant_id`,`status`),
  KEY `idx_knowledge_task_status` (`status`,`created_at`),
  KEY `idx_knowledge_task_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='知识导入任务表（RAG管道双写）';

CREATE TABLE `learning_daily_summary` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL COMMENT '用户 ID',
  `stat_date` date NOT NULL COMMENT '统计日期（本地时区）',
  `study_seconds` int(11) NOT NULL DEFAULT '0' COMMENT '当日学习总时长（秒）：含视频+作业+考试',
  `video_ticks` int(11) NOT NULL DEFAULT '0' COMMENT '当日接收到的有效视频打点数量',
  `homework_submitted` int(11) NOT NULL DEFAULT '0' COMMENT '当日提交的作业次数',
  `homework_correct_rate` decimal(5,4) DEFAULT NULL COMMENT '当日作业平均正确率 0-1',
  `exam_submitted` int(11) NOT NULL DEFAULT '0' COMMENT '当日提交的考试次数',
  `exam_avg_score` decimal(8,2) DEFAULT NULL COMMENT '当日考试平均分',
  `questions_attempted` int(11) NOT NULL DEFAULT '0' COMMENT '当日作答题目数',
  `questions_correct` int(11) NOT NULL DEFAULT '0' COMMENT '当日做对题目数',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_stat_date` (`user_id`,`stat_date`),
  KEY `idx_stat_date` (`stat_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P3 学习进度每日汇总表';

CREATE TABLE `learning_loop` (
  `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `course_id` bigint(20) NOT NULL COMMENT 'series_cohort_course.id',
  `session_id` bigint(20) NOT NULL COMMENT 'series_cohort_session.id',
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'ACTIVE',
  `activated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `idx_learning_loop_user_time` (`user_id`,`activated_at`),
  KEY `idx_learning_loop_status_time` (`status`,`activated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `learning_next_action` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `learning_loop_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `quiz_answer_session_id` bigint(20) unsigned NOT NULL,
  `kind` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `due_at` datetime(6) DEFAULT NULL,
  `executed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_learning_action_evidence_kind` (`learning_loop_id`,`quiz_answer_session_id`,`kind`),
  KEY `idx_learning_action_due` (`status`,`due_at`),
  KEY `fk_learning_action_answer` (`quiz_answer_session_id`),
  CONSTRAINT `fk_learning_action_answer` FOREIGN KEY (`quiz_answer_session_id`) REFERENCES `quiz_answer_session` (`id`),
  CONSTRAINT `fk_learning_action_loop` FOREIGN KEY (`learning_loop_id`) REFERENCES `learning_loop` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `learning_path_instance` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `path_code` varchar(64) NOT NULL COMMENT '路径唯一码，可作为 target_id 回写到 recommend_feedback',
  `title` varchar(255) NOT NULL COMMENT '例如「PHP 后端入门 6 周路径」',
  `subject_code` varchar(32) DEFAULT NULL,
  `total_sessions` int(11) NOT NULL DEFAULT '0',
  `total_hours` decimal(8,2) NOT NULL DEFAULT '0.00',
  `nodes_json` json NOT NULL COMMENT '路径节点有序数组（含 node_code/name/estimated_hours/prerequisite_codes）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_learning_path_code` (`path_code`),
  KEY `idx_learning_path_user` (`user_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P4 学习路径快照实例（下发前端 & 可反馈）';

CREATE TABLE `mcp_server` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `server_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '服务器内部编码，英文唯一（如 stdio-echodemo）',
  `display_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '展示名称',
  `description` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '功能/用途说明',
  `provider` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'self' COMMENT '提供方：self / feishu / github / custom',
  `transport` enum('stdio','sse','http') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'stdio' COMMENT '传输协议',
  `run_command` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'stdio 命令（如 python / npx / uvx）',
  `run_args_json` mediumtext COLLATE utf8mb4_unicode_ci COMMENT '命令参数数组 JSON（如 ["-m","p8_stdio_demo_server"]）',
  `working_dir` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '子进程工作目录（默认 PROJECT_ROOT）',
  `base_url` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'SSE 入口 URL 或 HTTP Server URL',
  `http_headers_json` mediumtext COLLATE utf8mb4_unicode_ci COMMENT 'SSE/HTTP 自定义请求头 JSON',
  `env_json` mediumtext COLLATE utf8mb4_unicode_ci COMMENT '环境变量 JSON（stdio 注入到子进程 envs）',
  `connect_timeout_ms` int(10) unsigned NOT NULL DEFAULT '5000' COMMENT '连接超时（毫秒），默认 5 秒',
  `call_timeout_ms` int(10) unsigned NOT NULL DEFAULT '30000' COMMENT '单次工具调用超时（毫秒），默认 30 秒',
  `enabled` tinyint(4) NOT NULL DEFAULT '1' COMMENT '是否启用（1=启用，0=禁用不参与对话工具注入）',
  `yn` tinyint(4) NOT NULL DEFAULT '1' COMMENT '软删除（1=存在，0=删除）',
  `created_by` bigint(20) unsigned NOT NULL DEFAULT '0' COMMENT '管理员 user_id',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `last_health_at` datetime DEFAULT NULL COMMENT '最近一次健康检查时间',
  `last_health_ok` tinyint(4) DEFAULT NULL COMMENT '最近健康检查是否成功',
  `last_error` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '最近一次调用/检查失败原因',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_mcp_server_code` (`server_code`),
  KEY `idx_mcp_transport_enabled` (`transport`,`enabled`,`yn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='MCP Server 注册';

CREATE TABLE `mcp_tool` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `server_id` bigint(20) unsigned NOT NULL,
  `tool_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '工具名（server 内唯一）',
  `display_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '中文展示名（便于管理端显示）',
  `description` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '工具功能描述（来自 tools/list 返回）',
  `input_schema_json` mediumtext COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'JSON Schema（properties/required）',
  `output_schema_json` mediumtext COLLATE utf8mb4_unicode_ci COMMENT '可选：工具输出 JSON Schema',
  `category` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'general' COMMENT '工具分类：knowledge/quiz/search/code/data/general',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `discovered_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `description_rewritten` text COLLATE utf8mb4_unicode_ci COMMENT 'FAST重写后的五要素描述（原description仅展示）',
  `description_score` int(11) DEFAULT NULL COMMENT '规则体检分值 0-100',
  `description_reviewed_at` datetime DEFAULT NULL COMMENT '最近描述体检时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_mcp_tool_server_name` (`server_id`,`tool_name`),
  KEY `idx_mcp_tool_name` (`tool_name`),
  KEY `idx_mcp_tool_category` (`category`,`yn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='MCP 工具元数据';

CREATE TABLE `mcp_tool_call_log` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `call_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '业务唯一 ID（如 {trace_id}:{seq}），用于幂等查',
  `server_id` bigint(20) unsigned NOT NULL,
  `tool_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `args_json` mediumtext COLLATE utf8mb4_unicode_ci COMMENT '调用参数 JSON',
  `result_json` mediumtext COLLATE utf8mb4_unicode_ci COMMENT '调用结果 JSON（SUCCESS）',
  `error_json` mediumtext COLLATE utf8mb4_unicode_ci COMMENT '失败完整错误 JSON（error dict / trace / structured）',
  `status` enum('SUCCESS','ERROR','TIMEOUT','SKIPPED','REJECTION_LIMIT','MANUAL_GUIDE') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'SUCCESS' COMMENT '调用状态：SUCCESS/ERROR/TIMEOUT/SKIPPED/REJECTION_LIMIT（拒绝熔断）/MANUAL_GUIDE（人工指南）',
  `latency_ms` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '耗时（毫秒）',
  `user_id` bigint(20) unsigned NOT NULL DEFAULT '0' COMMENT '发起用户（管理端=管理员uid，聊天=学生uid）',
  `tenant_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'trace 用租户 id',
  `trace_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '链路 trace id',
  `error_message` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '失败时错误消息',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_mcp_call_id` (`call_id`),
  KEY `idx_mcp_call_server_tool_created` (`server_id`,`tool_name`,`created_at`),
  KEY `idx_mcp_call_user_created` (`user_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='MCP 工具调用日志';

CREATE TABLE `mcp_tool_description_review_log` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `server_id` int(11) NOT NULL,
  `tool_id` int(11) NOT NULL,
  `tool_name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `score` int(11) NOT NULL,
  `reasons` text COLLATE utf8mb4_general_ci,
  `breaches` text COLLATE utf8mb4_general_ci,
  `rewritten` text COLLATE utf8mb4_general_ci,
  `rewritten_by_llm` tinyint(4) NOT NULL DEFAULT '0' COMMENT '是否经FAST模型重写',
  `original_desc` text COLLATE utf8mb4_general_ci,
  `operator_user_id` int(11) DEFAULT NULL,
  `trace_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_rev_tool` (`tool_id`),
  KEY `idx_rev_server` (`server_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='MCP 工具描述体检审计日志';

CREATE TABLE `order` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `order_no` varchar(64) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `coupon_receive_record_id` bigint(20) DEFAULT NULL,
  `order_source_channel_id` bigint(20) DEFAULT NULL,
  `order_status` varchar(32) NOT NULL COMMENT '枚举：pending,paid,completed,cancelled,partial_refunded,refunded',
  `total_amount` decimal(12,2) NOT NULL,
  `discount_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `payable_amount` decimal(12,2) NOT NULL,
  `paid_amount` decimal(12,2) DEFAULT NULL,
  `refund_amount` decimal(12,2) DEFAULT NULL,
  `remark` text,
  `paid_at` datetime DEFAULT NULL,
  `cancel_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_order_no` (`institution_id`,`order_no`),
  KEY `fk_order_student` (`student_id`),
  KEY `fk_order_coupon_receive_record` (`coupon_receive_record_id`),
  KEY `fk_order_source_channel` (`order_source_channel_id`),
  KEY `idx_order_user_status_created` (`user_id`,`order_status`,`created_at`),
  KEY `idx_order_no` (`order_no`),
  CONSTRAINT `fk_order_coupon_receive_record` FOREIGN KEY (`coupon_receive_record_id`) REFERENCES `coupon_receive_record` (`id`),
  CONSTRAINT `fk_order_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_order_source_channel` FOREIGN KEY (`order_source_channel_id`) REFERENCES `dim_channel` (`id`),
  CONSTRAINT `fk_order_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_order_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单主表';

CREATE TABLE `order_item` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `order_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `cohort_id` bigint(20) NOT NULL,
  `order_item_status` varchar(32) NOT NULL COMMENT '枚举：pending,paid,completed,cancelled,refunded',
  `item_name` varchar(255) NOT NULL,
  `unit_price` decimal(12,2) NOT NULL,
  `discount_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `payable_amount` decimal(12,2) NOT NULL,
  `service_period_days` int(11) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_order_item_institution` (`institution_id`),
  KEY `fk_order_item_order` (`order_id`),
  KEY `fk_order_item_user` (`user_id`),
  KEY `fk_order_item_student` (`student_id`),
  KEY `fk_order_item_cohort` (`cohort_id`),
  CONSTRAINT `fk_order_item_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`),
  CONSTRAINT `fk_order_item_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_order_item_order` FOREIGN KEY (`order_id`) REFERENCES `order` (`id`),
  CONSTRAINT `fk_order_item_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_order_item_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单明细表';

CREATE TABLE `org_campus` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `campus_code` varchar(64) NOT NULL,
  `campus_name` varchar(128) NOT NULL,
  `province` varchar(64) DEFAULT NULL,
  `city` varchar(64) DEFAULT NULL,
  `district` varchar(64) DEFAULT NULL,
  `address` varchar(255) DEFAULT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_org_campus_code` (`institution_id`,`campus_code`),
  CONSTRAINT `fk_org_campus_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='校区表';

CREATE TABLE `org_campus_manager` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `campus_id` bigint(20) NOT NULL,
  `staff_id` bigint(20) NOT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_org_campus_manager_campus` (`campus_id`),
  KEY `fk_org_campus_manager_staff` (`staff_id`),
  CONSTRAINT `fk_org_campus_manager_campus` FOREIGN KEY (`campus_id`) REFERENCES `org_campus` (`id`),
  CONSTRAINT `fk_org_campus_manager_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff_profile` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='校区负责人表';

CREATE TABLE `org_classroom` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `campus_id` bigint(20) DEFAULT NULL,
  `room_code` varchar(64) NOT NULL,
  `room_name` varchar(128) NOT NULL,
  `room_type` varchar(32) NOT NULL COMMENT '枚举：physical,live',
  `max_capacity` int(11) DEFAULT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_org_classroom_code` (`institution_id`,`room_code`),
  KEY `fk_org_classroom_campus` (`campus_id`),
  CONSTRAINT `fk_org_classroom_campus` FOREIGN KEY (`campus_id`) REFERENCES `org_campus` (`id`),
  CONSTRAINT `fk_org_classroom_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教室资源表';

CREATE TABLE `org_department` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `campus_id` bigint(20) DEFAULT NULL,
  `parent_id` bigint(20) DEFAULT NULL,
  `dept_code` varchar(64) NOT NULL,
  `dept_name` varchar(128) NOT NULL,
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_org_department_code` (`institution_id`,`dept_code`),
  KEY `fk_org_department_campus` (`campus_id`),
  KEY `fk_org_department_parent` (`parent_id`),
  CONSTRAINT `fk_org_department_campus` FOREIGN KEY (`campus_id`) REFERENCES `org_campus` (`id`),
  CONSTRAINT `fk_org_department_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_org_department_parent` FOREIGN KEY (`parent_id`) REFERENCES `org_department` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='部门表';

CREATE TABLE `org_department_manager` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `department_id` bigint(20) NOT NULL,
  `staff_id` bigint(20) NOT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_org_department_manager_department` (`department_id`),
  KEY `fk_org_department_manager_staff` (`staff_id`),
  CONSTRAINT `fk_org_department_manager_department` FOREIGN KEY (`department_id`) REFERENCES `org_department` (`id`),
  CONSTRAINT `fk_org_department_manager_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff_profile` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='部门负责人表';

CREATE TABLE `org_institution` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_code` varchar(64) NOT NULL,
  `institution_name` varchar(128) NOT NULL,
  `institution_type` varchar(32) NOT NULL COMMENT '枚举：training_center,school,education_brand,enterprise_academy',
  `province` varchar(64) DEFAULT NULL,
  `city` varchar(64) DEFAULT NULL,
  `district` varchar(64) DEFAULT NULL,
  `address` varchar(255) DEFAULT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_org_institution_code` (`institution_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机构主表';

CREATE TABLE `org_institution_manager` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `staff_id` bigint(20) NOT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_org_institution_manager_institution` (`institution_id`),
  KEY `fk_org_institution_manager_staff` (`staff_id`),
  CONSTRAINT `fk_org_institution_manager_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_org_institution_manager_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff_profile` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机构负责人表';

CREATE TABLE `org_staff_role` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `role_code` varchar(64) NOT NULL,
  `role_name` varchar(64) NOT NULL,
  `role_category` varchar(32) NOT NULL COMMENT '枚举：teacher,academic,sales,operations,service,management',
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_org_staff_role_code` (`institution_id`,`role_code`),
  CONSTRAINT `fk_org_staff_role_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机构职员角色表';

CREATE TABLE `payment_record` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `order_id` bigint(20) NOT NULL,
  `payment_no` varchar(64) NOT NULL,
  `payment_channel` varchar(32) NOT NULL COMMENT '枚举：wechat_pay,alipay,bank_card,offline_transfer,public_account,campus_cashier',
  `payment_status` varchar(32) NOT NULL COMMENT '枚举：pending,paid,failed,closed,partial_refunded,refunded',
  `amount` decimal(12,2) NOT NULL,
  `third_party_trade_no` varchar(128) DEFAULT NULL,
  `refund_amount` decimal(12,2) DEFAULT NULL,
  `paid_at` datetime DEFAULT NULL,
  `refund_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_payment_record_no` (`institution_id`,`payment_no`),
  KEY `fk_payment_record_order` (`order_id`),
  CONSTRAINT `fk_payment_record_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_payment_record_order` FOREIGN KEY (`order_id`) REFERENCES `order` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='支付记录表';

CREATE TABLE `question` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `bank_id` bigint(20) NOT NULL,
  `question_code` varchar(64) NOT NULL,
  `question_type_id` bigint(20) NOT NULL,
  `stem` text NOT NULL,
  `options_json` json DEFAULT NULL,
  `answer_text` text NOT NULL,
  `analysis_text` text,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_question_code` (`bank_id`,`question_code`),
  KEY `fk_question_type` (`question_type_id`),
  CONSTRAINT `fk_question_bank` FOREIGN KEY (`bank_id`) REFERENCES `question_bank` (`id`),
  CONSTRAINT `fk_question_type` FOREIGN KEY (`question_type_id`) REFERENCES `dim_question_type` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='题目主表';

CREATE TABLE `question_bank` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `category_id` bigint(20) NOT NULL,
  `bank_code` varchar(64) NOT NULL,
  `bank_name` varchar(128) NOT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_question_bank_code` (`institution_id`,`bank_code`),
  KEY `fk_question_bank_category` (`category_id`),
  CONSTRAINT `fk_question_bank_category` FOREIGN KEY (`category_id`) REFERENCES `dim_course_category` (`id`),
  CONSTRAINT `fk_question_bank_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='题库主表';

CREATE TABLE `quiz_answer_session` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) unsigned NOT NULL,
  `question_id` bigint(20) unsigned DEFAULT NULL COMMENT 'admin_question.id（若为内置题库题）',
  `custom_question_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '非内置题：mock/外部接入的可追溯 code',
  `subject_code` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `question_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'SINGLE / MULTI / JUDGE / FILL / DRAG_SORT / MATCH',
  `prompt_json` json DEFAULT NULL COMMENT '题目本身（题干、选项、正确答案、解析草稿）',
  `user_answer_json` json NOT NULL COMMENT '用户作答快照',
  `is_correct` tinyint(1) NOT NULL,
  `score` decimal(6,2) NOT NULL DEFAULT '0.00',
  `time_spent_sec` int(10) unsigned NOT NULL DEFAULT '0',
  `explain_text` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '即时反馈：解析文本（可由 RAG/LLM 生成，打靶可回退模板）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `attempt_id` char(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `request_hash` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `response_json` json DEFAULT NULL,
  `course_id` bigint(20) DEFAULT NULL,
  `question_version` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `knowledge_codes_snapshot` json DEFAULT NULL,
  `hint_used` tinyint(1) NOT NULL DEFAULT '0',
  `redo_of_attempt_id` char(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `learning_loop_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_quiz_answer_user_attempt` (`user_id`,`attempt_id`),
  KEY `idx_quiz_session_user_time` (`user_id`,`created_at`),
  KEY `idx_quiz_session_question` (`question_id`,`custom_question_code`),
  KEY `idx_quiz_answer_user_course_time` (`user_id`,`course_id`,`created_at`),
  KEY `idx_quiz_answer_loop` (`learning_loop_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P5 quiz 每次答题独立记录';

CREATE TABLE `quiz_question_kp` (
  `question_id` bigint(20) NOT NULL,
  `knowledge_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`question_id`,`knowledge_code`),
  KEY `idx_quiz_kp_code_question` (`knowledge_code`,`question_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `quiz_question_publication` (
  `question_id` bigint(20) NOT NULL,
  `course_id` bigint(20) DEFAULT NULL,
  `question_version` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `difficulty` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'DRAFT',
  `published_at` datetime DEFAULT NULL,
  `reviewer_user_id` bigint(20) DEFAULT NULL,
  `content_authorization_ref` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`question_id`),
  KEY `idx_quiz_publication_course` (`course_id`,`review_status`,`subject_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `quiz_wrong_book` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) unsigned NOT NULL,
  `question_id` bigint(20) unsigned DEFAULT NULL,
  `custom_question_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `subject_code` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `question_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `wrong_count` int(10) unsigned NOT NULL DEFAULT '1' COMMENT '累计错误次数',
  `correct_count` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '错题复习时做对的次数（达到阈值可移除）',
  `last_wrong_answer_json` json DEFAULT NULL,
  `master_threshold` int(10) unsigned NOT NULL DEFAULT '3' COMMENT '连续做对几次移除',
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE 仍在 / MASTERED 已掌握 / ARCHIVED 手动归档',
  `next_review_at` datetime DEFAULT NULL COMMENT '下一次建议复习时间（可选地用 SM-2）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_wrongbook_user_question` (`user_id`,`question_id`,`custom_question_code`),
  KEY `idx_wrongbook_user_status` (`user_id`,`status`,`next_review_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P5 quiz 错题本';

CREATE TABLE `rag_audit_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `audit_id` varchar(64) NOT NULL COMMENT '审计 ID（a_xxx 短 uuid），前端回放用',
  `user_id` bigint(20) NOT NULL COMMENT '发起用户 ID',
  `session_id` varchar(64) DEFAULT NULL COMMENT '会话 ID（临时问答可为 NULL）',
  `user_message_id` varchar(64) DEFAULT NULL COMMENT 'chat_message.user 那条 message_id',
  `assistant_message_id` varchar(64) DEFAULT NULL COMMENT 'chat_message.assistant 那条 message_id',
  `role` varchar(16) NOT NULL DEFAULT 'student' COMMENT '发起角色 student/admin/teacher/manager',
  `query` text NOT NULL COMMENT '用户原始提问',
  `rewrite_query` text COMMENT 'HyDE/扩展后的查询',
  `retrieved_count` int(11) DEFAULT NULL COMMENT '检索召回数量（断崖前）',
  `final_count` int(11) DEFAULT NULL COMMENT '最终喂给 LLM 的 doc 数',
  `llm_model` varchar(64) DEFAULT NULL COMMENT '实际用的模型名或降级标识（fallback_rule 等）',
  `latency_ms` int(11) NOT NULL COMMENT '整轮耗时毫秒（检索+生成+落库）',
  `degraded_reason` varchar(1024) DEFAULT NULL COMMENT '降级说明',
  `is_stream` tinyint(4) NOT NULL DEFAULT '0' COMMENT '是否流式 1=是 0=否',
  `error_message` varchar(1024) DEFAULT NULL COMMENT '异常信息（若有）',
  `param_preset_id` bigint(20) DEFAULT NULL COMMENT '应用的检索参数预设 ID（可空=default）',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_rag_audit_audit_id` (`audit_id`),
  KEY `idx_rag_audit_user_created` (`user_id`,`created_at`),
  KEY `idx_rag_audit_session` (`session_id`),
  KEY `idx_rag_audit_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P7 管理端 RAG：问答审计日志（全链路回放）';

CREATE TABLE `rag_collection_meta` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `collection_name` varchar(128) NOT NULL COMMENT 'Milvus collection 名（固定 knowledge_chunk_v1）',
  `partition_name` varchar(128) NOT NULL COMMENT 'Partition 名（_default / user_{id} 等）',
  `tenant_id` varchar(128) DEFAULT NULL COMMENT 'Partition 对应租户 ID（_default 为 NULL，私有分区为 user_id）',
  `display_name` varchar(256) NOT NULL COMMENT '展示名（如"公共知识库"、"uid 802 私有库"）',
  `row_count` bigint(20) NOT NULL DEFAULT '0' COMMENT '该 Partition 当前 chunk 行数',
  `source_count` int(11) NOT NULL DEFAULT '0' COMMENT '来源文档数（近似，不强制精确）',
  `last_rebuild_at` datetime(3) DEFAULT NULL COMMENT '最后一次重建索引时间',
  `last_snapshot_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '最后一次元数据快照时间',
  `status` varchar(32) NOT NULL DEFAULT 'ready' COMMENT 'ready / rebuilding / error',
  `status_message` varchar(512) DEFAULT NULL,
  `visibility` varchar(16) NOT NULL DEFAULT 'public' COMMENT 'public/private（对应导入时的 visibility）',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_rag_collection_partition` (`collection_name`,`partition_name`),
  KEY `idx_rag_tenant` (`tenant_id`),
  KEY `idx_rag_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P7 管理端 RAG：知识库 Partition 元数据快照';

CREATE TABLE `rag_param_preset` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `preset_name` varchar(64) NOT NULL COMMENT '预设名（如 高质量/平衡/低延迟）',
  `is_default` tinyint(4) NOT NULL DEFAULT '0' COMMENT '1=默认预设（全局一条）',
  `description` varchar(512) DEFAULT NULL,
  `top_k` int(11) NOT NULL DEFAULT '20' COMMENT '单通道召回上限',
  `final_max_k` int(11) NOT NULL DEFAULT '6' COMMENT '断崖后最终喂给 LLM 的上限',
  `cutoff_drop_ratio` decimal(5,3) NOT NULL DEFAULT '0.400' COMMENT '断崖阈值（0.05~0.9）',
  `rrf_k` int(11) NOT NULL DEFAULT '60' COMMENT 'RRF 融合 k 值',
  `use_hyde` tinyint(4) NOT NULL DEFAULT '1' COMMENT '是否启用 HyDE 1=是 0=否',
  `enable_graph` tinyint(4) NOT NULL DEFAULT '1' COMMENT '是否启用图谱扩展 1=是 0=否',
  `llm_model_pref` varchar(64) NOT NULL DEFAULT 'fast' COMMENT 'fast/quality/local',
  `created_by` bigint(20) DEFAULT NULL COMMENT '创建者 user_id（系统内置=1）',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `default_flag` tinyint(4) GENERATED ALWAYS AS ((case when ((`is_default` = 1) and (`yn` = 1)) then 1 else NULL end)) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_rag_preset_name` (`preset_name`),
  UNIQUE KEY `uk_rag_preset_default_flag` (`default_flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P7 管理端 RAG：检索参数预设';

CREATE TABLE `ranking_snapshot` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `snapshot_date` date NOT NULL,
  `rank_scope` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'DAILY/WEEKLY/MONTHLY/ALL_TIME',
  `rank_dim` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'POINTS/STUDY_MIN/BADGE_COUNT',
  `user_id` bigint(20) unsigned NOT NULL,
  `rank_no` int(10) unsigned NOT NULL,
  `metric_value` int(10) unsigned NOT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_snapshot_rank` (`snapshot_date`,`rank_scope`,`rank_dim`,`rank_no`),
  KEY `idx_user` (`user_id`,`rank_scope`,`rank_dim`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P6 排行榜日快照（排行榜查询 3 维度 × 4 时间范围）';

CREATE TABLE `recommend_feedback` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `scene_code` varchar(32) NOT NULL COMMENT 'PATH（推荐路径）/ NEXT（下一步）/ NODE（知识点）',
  `target_id` varchar(128) NOT NULL COMMENT '被反馈对象业务 id：series_id | knowledge_point code | 路径 hash',
  `feedback_type` varchar(16) NOT NULL COMMENT 'HELPFUL / NOT_INTERESTED / ALREADY_LEARNED / TOO_HARD',
  `score_delta` decimal(5,2) NOT NULL DEFAULT '0.00' COMMENT '对该目标的推荐分修正：HELPFUL +0.5，NOT_INTERESTED -1.0',
  `extra_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_recommend_fb_user_scene_target` (`user_id`,`scene_code`,`target_id`,`feedback_type`),
  KEY `idx_recommend_fb_target` (`scene_code`,`target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P4 推荐结果反馈（协同过滤/个性化修正输入）';

CREATE TABLE `refund_request` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `refund_no` varchar(64) NOT NULL,
  `order_id` bigint(20) NOT NULL,
  `order_item_id` bigint(20) NOT NULL,
  `payment_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `refund_type` varchar(32) NOT NULL COMMENT '枚举：personal_reason,course_unsatisfied,schedule_conflict,duplicate_purchase',
  `refund_reason` text NOT NULL,
  `refund_status` varchar(32) NOT NULL COMMENT '枚举：pending,approved,rejected,refunded',
  `apply_amount` decimal(12,2) NOT NULL,
  `approved_amount` decimal(12,2) DEFAULT NULL,
  `approver_user_id` bigint(20) DEFAULT NULL,
  `remark` text,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `applied_at` datetime NOT NULL,
  `approved_at` datetime DEFAULT NULL,
  `refunded_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_refund_request_no` (`institution_id`,`refund_no`),
  KEY `fk_refund_request_order` (`order_id`),
  KEY `fk_refund_request_order_item` (`order_item_id`),
  KEY `fk_refund_request_payment` (`payment_id`),
  KEY `fk_refund_request_user` (`user_id`),
  KEY `fk_refund_request_student` (`student_id`),
  KEY `fk_refund_request_approver` (`approver_user_id`),
  CONSTRAINT `fk_refund_request_approver` FOREIGN KEY (`approver_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_refund_request_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_refund_request_order` FOREIGN KEY (`order_id`) REFERENCES `order` (`id`),
  CONSTRAINT `fk_refund_request_order_item` FOREIGN KEY (`order_item_id`) REFERENCES `order_item` (`id`),
  CONSTRAINT `fk_refund_request_payment` FOREIGN KEY (`payment_id`) REFERENCES `payment_record` (`id`),
  CONSTRAINT `fk_refund_request_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_refund_request_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='退款申请表';

CREATE TABLE `risk_alert_event` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `alert_no` varchar(64) NOT NULL,
  `alert_type` varchar(32) NOT NULL COMMENT '枚举：refund_anomaly,learning_anomaly,exam_anomaly,ugc_anomaly,operation_anomaly',
  `risk_level` varchar(32) NOT NULL COMMENT '枚举：low,medium,high,critical',
  `related_user_id` bigint(20) DEFAULT NULL,
  `related_student_id` bigint(20) DEFAULT NULL,
  `cohort_id` bigint(20) DEFAULT NULL,
  `session_id` bigint(20) DEFAULT NULL,
  `order_item_id` bigint(20) DEFAULT NULL,
  `refund_request_id` bigint(20) DEFAULT NULL,
  `related_exam_attempt_id` bigint(20) DEFAULT NULL,
  `ugc_content_type` varchar(32) DEFAULT NULL COMMENT '枚举：topic,post,review',
  `ugc_content_id` bigint(20) DEFAULT NULL,
  `alert_source` varchar(32) NOT NULL COMMENT '枚举：rule_engine,manual_report,model_detection,scheduled_job',
  `alert_reason` text NOT NULL,
  `event_payload` json DEFAULT NULL,
  `alert_status` varchar(32) NOT NULL COMMENT '枚举：pending,in_progress,closed',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `detected_at` datetime NOT NULL,
  `closed_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_risk_alert_event_no` (`institution_id`,`alert_no`),
  KEY `fk_risk_alert_event_user` (`related_user_id`),
  KEY `fk_risk_alert_event_student` (`related_student_id`),
  KEY `fk_risk_alert_event_cohort` (`cohort_id`),
  KEY `fk_risk_alert_event_session` (`session_id`),
  KEY `fk_risk_alert_event_order_item` (`order_item_id`),
  KEY `fk_risk_alert_event_refund_request` (`refund_request_id`),
  KEY `fk_risk_alert_event_exam_attempt` (`related_exam_attempt_id`),
  CONSTRAINT `fk_risk_alert_event_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`),
  CONSTRAINT `fk_risk_alert_event_exam_attempt` FOREIGN KEY (`related_exam_attempt_id`) REFERENCES `session_exam_submission` (`id`),
  CONSTRAINT `fk_risk_alert_event_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_risk_alert_event_order_item` FOREIGN KEY (`order_item_id`) REFERENCES `order_item` (`id`),
  CONSTRAINT `fk_risk_alert_event_refund_request` FOREIGN KEY (`refund_request_id`) REFERENCES `refund_request` (`id`),
  CONSTRAINT `fk_risk_alert_event_session` FOREIGN KEY (`session_id`) REFERENCES `series_cohort_session` (`id`),
  CONSTRAINT `fk_risk_alert_event_student` FOREIGN KEY (`related_student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_risk_alert_event_user` FOREIGN KEY (`related_user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风险预警事件表';

CREATE TABLE `risk_disposal_record` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `alert_id` bigint(20) NOT NULL,
  `handler_user_id` bigint(20) NOT NULL,
  `action_type` varchar(32) NOT NULL COMMENT '枚举：review,contact_user,freeze_account,mark_false_positive,close_alert',
  `action_result` varchar(32) NOT NULL COMMENT '枚举：pending_follow_up,confirmed_risk,false_positive,resolved',
  `action_note` text,
  `handled_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_risk_disposal_record_alert` (`alert_id`),
  KEY `fk_risk_disposal_record_handler` (`handler_user_id`),
  CONSTRAINT `fk_risk_disposal_record_alert` FOREIGN KEY (`alert_id`) REFERENCES `risk_alert_event` (`id`),
  CONSTRAINT `fk_risk_disposal_record_handler` FOREIGN KEY (`handler_user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='风险处置记录表';

CREATE TABLE `series` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `delivery_mode` varchar(32) NOT NULL COMMENT '枚举：online_live,online_recorded,offline_face_to_face',
  `series_code` varchar(64) NOT NULL,
  `series_name` varchar(128) NOT NULL,
  `description` text,
  `cover_url` varchar(255) DEFAULT NULL,
  `target_learner_identity_codes` json DEFAULT NULL,
  `target_learning_goal_codes` json DEFAULT NULL,
  `target_grade_codes` json DEFAULT NULL,
  `sale_status` varchar(32) NOT NULL COMMENT '枚举：draft,on_sale,off_sale',
  `created_by` bigint(20) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_series_code` (`institution_id`,`series_code`),
  KEY `fk_series_created_by` (`created_by`),
  KEY `idx_series_inst_sale` (`institution_id`,`sale_status`),
  CONSTRAINT `fk_series_created_by` FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_series_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程系列主表';

CREATE TABLE `series_category_rel` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `series_id` bigint(20) NOT NULL,
  `category_id` bigint(20) NOT NULL,
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_series_category_rel` (`series_id`,`category_id`),
  KEY `fk_series_category_rel_category` (`category_id`),
  CONSTRAINT `fk_series_category_rel_category` FOREIGN KEY (`category_id`) REFERENCES `dim_course_category` (`id`),
  CONSTRAINT `fk_series_category_rel_series` FOREIGN KEY (`series_id`) REFERENCES `series` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程系列分类关系表';

CREATE TABLE `series_cohort` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `series_id` bigint(20) NOT NULL,
  `campus_id` bigint(20) DEFAULT NULL,
  `head_teacher_id` bigint(20) NOT NULL,
  `cohort_code` varchar(64) NOT NULL,
  `cohort_name` varchar(128) NOT NULL,
  `sale_price` decimal(12,2) NOT NULL COMMENT '班次售价',
  `max_student_count` int(11) NOT NULL,
  `current_student_count` int(11) NOT NULL DEFAULT '0',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `start_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_series_cohort_code` (`institution_id`,`cohort_code`),
  KEY `fk_series_cohort_campus` (`campus_id`),
  KEY `fk_series_cohort_teacher` (`head_teacher_id`),
  KEY `idx_series_cohort_series` (`series_id`),
  CONSTRAINT `fk_series_cohort_campus` FOREIGN KEY (`campus_id`) REFERENCES `org_campus` (`id`),
  CONSTRAINT `fk_series_cohort_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_series_cohort_series` FOREIGN KEY (`series_id`) REFERENCES `series` (`id`),
  CONSTRAINT `fk_series_cohort_teacher` FOREIGN KEY (`head_teacher_id`) REFERENCES `staff_profile` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='班次主表';

CREATE TABLE `series_cohort_course` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `cohort_id` bigint(20) NOT NULL,
  `module_code` varchar(64) NOT NULL,
  `module_name` varchar(128) NOT NULL,
  `description` text,
  `lesson_count` int(11) NOT NULL,
  `total_hours` decimal(8,2) NOT NULL,
  `stage_no` int(11) NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_series_cohort_course_stage` (`cohort_id`,`stage_no`),
  UNIQUE KEY `uk_series_cohort_course_module` (`cohort_id`,`module_code`),
  CONSTRAINT `fk_series_cohort_course_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='班次课程模块表';

CREATE TABLE `series_cohort_session` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `series_cohort_course_id` bigint(20) NOT NULL,
  `room_id` bigint(20) DEFAULT NULL,
  `session_no` int(11) NOT NULL,
  `session_title` varchar(128) NOT NULL,
  `teaching_status` varchar(32) NOT NULL COMMENT '枚举：scheduled,in_progress,completed,cancelled',
  `checkin_required` tinyint(4) NOT NULL DEFAULT '0' COMMENT '枚举：0,1',
  `teaching_date` date NOT NULL,
  `start_time` time DEFAULT NULL,
  `end_time` time DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_series_cohort_session_no` (`series_cohort_course_id`,`session_no`),
  KEY `fk_series_cohort_session_room` (`room_id`),
  CONSTRAINT `fk_series_cohort_session_course` FOREIGN KEY (`series_cohort_course_id`) REFERENCES `series_cohort_course` (`id`),
  CONSTRAINT `fk_series_cohort_session_room` FOREIGN KEY (`room_id`) REFERENCES `org_classroom` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课次主表';

CREATE TABLE `series_exposure_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `series_id` bigint(20) NOT NULL,
  `exposure_scene` varchar(32) NOT NULL COMMENT '枚举：recommendation,search,activity,category,learning_center',
  `position_no` int(11) NOT NULL,
  `device_type` varchar(32) DEFAULT NULL,
  `exposed_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_series_exposure_log_user` (`user_id`),
  KEY `fk_series_exposure_log_series` (`series_id`),
  CONSTRAINT `fk_series_exposure_log_series` FOREIGN KEY (`series_id`) REFERENCES `series` (`id`),
  CONSTRAINT `fk_series_exposure_log_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程系列曝光日志表';

CREATE TABLE `series_favorite` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `series_id` bigint(20) NOT NULL,
  `favorite_source` varchar(32) NOT NULL COMMENT '枚举：series_detail,search_result,recommendation,activity_page',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_series_favorite` (`user_id`,`series_id`),
  KEY `fk_series_favorite_series` (`series_id`),
  CONSTRAINT `fk_series_favorite_series` FOREIGN KEY (`series_id`) REFERENCES `series` (`id`),
  CONSTRAINT `fk_series_favorite_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程系列收藏表';

CREATE TABLE `series_search_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `keyword_text` varchar(255) NOT NULL,
  `search_source` varchar(32) NOT NULL COMMENT '枚举：home_page,course_list_page,category_page,learning_center',
  `result_count` int(11) NOT NULL DEFAULT '0',
  `clicked_series_id` bigint(20) DEFAULT NULL,
  `searched_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_series_search_log_user` (`user_id`),
  KEY `fk_series_search_log_series` (`clicked_series_id`),
  CONSTRAINT `fk_series_search_log_series` FOREIGN KEY (`clicked_series_id`) REFERENCES `series` (`id`),
  CONSTRAINT `fk_series_search_log_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程搜索日志表';

CREATE TABLE `series_visit_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `series_id` bigint(20) NOT NULL,
  `ref_exposure_id` bigint(20) DEFAULT NULL,
  `visit_source` varchar(32) NOT NULL COMMENT '枚举：recommendation,search_result,activity_page,favorite_list,shopping_cart,direct_access',
  `stay_seconds` int(11) NOT NULL DEFAULT '0',
  `enter_at` datetime NOT NULL,
  `leave_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_series_visit_log_user` (`user_id`),
  KEY `fk_series_visit_log_exposure` (`ref_exposure_id`),
  KEY `idx_series_visit_log_series_created` (`series_id`,`created_at`),
  CONSTRAINT `fk_series_visit_log_exposure` FOREIGN KEY (`ref_exposure_id`) REFERENCES `series_exposure_log` (`id`),
  CONSTRAINT `fk_series_visit_log_series` FOREIGN KEY (`series_id`) REFERENCES `series` (`id`),
  CONSTRAINT `fk_series_visit_log_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课程系列访问日志表';

CREATE TABLE `service_ticket` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `ticket_no` varchar(64) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `order_item_id` bigint(20) NOT NULL,
  `refund_request_id` bigint(20) DEFAULT NULL,
  `ticket_type` varchar(32) NOT NULL COMMENT '枚举：after_sales,complaint,refund',
  `ticket_source` varchar(32) NOT NULL COMMENT '枚举：user_app,customer_service,system_auto,admin_manual',
  `priority_level` varchar(32) NOT NULL COMMENT '枚举：low,medium,high,urgent',
  `ticket_status` varchar(32) NOT NULL COMMENT '枚举：pending,in_progress,closed',
  `assignee_user_id` bigint(20) DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `ticket_content` text NOT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `first_response_at` datetime DEFAULT NULL,
  `closed_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_service_ticket_no` (`institution_id`,`ticket_no`),
  KEY `fk_service_ticket_student` (`student_id`),
  KEY `fk_service_ticket_order_item` (`order_item_id`),
  KEY `fk_service_ticket_refund_request` (`refund_request_id`),
  KEY `fk_service_ticket_assignee` (`assignee_user_id`),
  KEY `idx_service_ticket_user_status` (`user_id`,`ticket_status`),
  CONSTRAINT `fk_service_ticket_assignee` FOREIGN KEY (`assignee_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_service_ticket_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_service_ticket_order_item` FOREIGN KEY (`order_item_id`) REFERENCES `order_item` (`id`),
  CONSTRAINT `fk_service_ticket_refund_request` FOREIGN KEY (`refund_request_id`) REFERENCES `refund_request` (`id`),
  CONSTRAINT `fk_service_ticket_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_service_ticket_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='客服工单表';

CREATE TABLE `service_ticket_follow_record` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `ticket_id` bigint(20) NOT NULL,
  `follow_user_id` bigint(20) NOT NULL,
  `follow_type` varchar(32) NOT NULL COMMENT '枚举：reply_user,status_update,refund_review,internal_note,escalation',
  `follow_channel` varchar(32) NOT NULL COMMENT '枚举：phone,user_app,sms,wechat,internal_system,offline',
  `follow_result` varchar(32) NOT NULL COMMENT '枚举：pending_follow_up,user_confirmed,user_unreachable,resolved,escalated',
  `follow_content` text NOT NULL,
  `followed_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_service_ticket_follow_record_ticket` (`ticket_id`),
  KEY `fk_service_ticket_follow_record_user` (`follow_user_id`),
  CONSTRAINT `fk_service_ticket_follow_record_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `service_ticket` (`id`),
  CONSTRAINT `fk_service_ticket_follow_record_user` FOREIGN KEY (`follow_user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='工单跟进记录表';

CREATE TABLE `service_ticket_satisfaction_survey` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `survey_no` varchar(64) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `ticket_id` bigint(20) NOT NULL,
  `score_value` tinyint(4) DEFAULT NULL,
  `comment_text` text,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `surveyed_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_service_ticket_satisfaction_survey_no` (`survey_no`),
  UNIQUE KEY `uk_service_ticket_satisfaction_survey_ticket` (`ticket_id`),
  KEY `fk_service_ticket_satisfaction_survey_user` (`user_id`),
  KEY `fk_service_ticket_satisfaction_survey_student` (`student_id`),
  CONSTRAINT `fk_service_ticket_satisfaction_survey_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_service_ticket_satisfaction_survey_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `service_ticket` (`id`),
  CONSTRAINT `fk_service_ticket_satisfaction_survey_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='工单满意度调查表';

CREATE TABLE `session_asset` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `session_id` bigint(20) NOT NULL,
  `asset_code` varchar(64) NOT NULL,
  `asset_name` varchar(128) NOT NULL,
  `file_type` varchar(32) NOT NULL,
  `material_category` varchar(32) NOT NULL COMMENT '枚举：video,handout,exercise,reference,image',
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `access_scope` varchar(32) NOT NULL COMMENT '枚举：public,trial,enrolled_only,internal_only',
  `file_url` varchar(255) NOT NULL,
  `file_size` bigint(20) DEFAULT NULL,
  `uploader_user_id` bigint(20) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_asset_code` (`session_id`,`asset_code`),
  KEY `fk_session_asset_uploader` (`uploader_user_id`),
  CONSTRAINT `fk_session_asset_session` FOREIGN KEY (`session_id`) REFERENCES `series_cohort_session` (`id`),
  CONSTRAINT `fk_session_asset_uploader` FOREIGN KEY (`uploader_user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课次资源表';

CREATE TABLE `session_attendance` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `session_id` bigint(20) NOT NULL,
  `cohort_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `attendance_status` varchar(32) NOT NULL COMMENT '枚举：pending,present,absent,leave,late',
  `leave_type` varchar(32) DEFAULT NULL,
  `remark` text,
  `checkin_time` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_attendance` (`session_id`,`student_id`),
  KEY `fk_session_attendance_institution` (`institution_id`),
  KEY `fk_session_attendance_cohort` (`cohort_id`),
  KEY `fk_session_attendance_user` (`user_id`),
  KEY `fk_session_attendance_student` (`student_id`),
  KEY `idx_session_attendance_session_status` (`session_id`,`attendance_status`),
  CONSTRAINT `fk_session_attendance_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`),
  CONSTRAINT `fk_session_attendance_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_session_attendance_session` FOREIGN KEY (`session_id`) REFERENCES `series_cohort_session` (`id`),
  CONSTRAINT `fk_session_attendance_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_session_attendance_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课次考勤表';

CREATE TABLE `session_exam` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `session_id` bigint(20) NOT NULL,
  `exam_code` varchar(64) NOT NULL,
  `exam_name` varchar(128) NOT NULL,
  `total_score` decimal(8,2) NOT NULL,
  `pass_score` decimal(8,2) NOT NULL,
  `publish_status` varchar(32) NOT NULL COMMENT '枚举：draft,published,closed',
  `created_by` bigint(20) NOT NULL,
  `duration_minutes` int(11) NOT NULL,
  `window_start_at` datetime NOT NULL,
  `deadline_at` datetime NOT NULL,
  `publish_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_exam_code` (`session_id`,`exam_code`),
  KEY `fk_session_exam_created_by` (`created_by`),
  CONSTRAINT `fk_session_exam_created_by` FOREIGN KEY (`created_by`) REFERENCES `staff_profile` (`id`),
  CONSTRAINT `fk_session_exam_session` FOREIGN KEY (`session_id`) REFERENCES `series_cohort_session` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课次考试表';

CREATE TABLE `session_exam_question_rel` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `exam_id` bigint(20) NOT NULL,
  `question_id` bigint(20) NOT NULL,
  `sort_no` int(11) NOT NULL,
  `score` decimal(8,2) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_exam_question_rel` (`exam_id`,`question_id`),
  UNIQUE KEY `uk_session_exam_question_sort` (`exam_id`,`sort_no`),
  KEY `fk_session_exam_question_rel_question` (`question_id`),
  CONSTRAINT `fk_session_exam_question_rel_exam` FOREIGN KEY (`exam_id`) REFERENCES `session_exam` (`id`),
  CONSTRAINT `fk_session_exam_question_rel_question` FOREIGN KEY (`question_id`) REFERENCES `question` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='考试题目关系表';

CREATE TABLE `session_exam_submission` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `exam_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `attempt_no` varchar(64) NOT NULL,
  `attempt_status` varchar(32) NOT NULL COMMENT '枚举：not_started,in_progress,submitted,absent,timeout',
  `duration_seconds` int(11) DEFAULT NULL,
  `score_value` decimal(8,2) DEFAULT NULL,
  `start_at` datetime DEFAULT NULL,
  `submit_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_exam_submission_no` (`institution_id`,`attempt_no`),
  UNIQUE KEY `uk_session_exam_submission_once` (`exam_id`,`student_id`),
  KEY `fk_session_exam_submission_user` (`user_id`),
  KEY `fk_session_exam_submission_student` (`student_id`),
  CONSTRAINT `fk_session_exam_submission_exam` FOREIGN KEY (`exam_id`) REFERENCES `session_exam` (`id`),
  CONSTRAINT `fk_session_exam_submission_exam_id` FOREIGN KEY (`exam_id`) REFERENCES `session_exam` (`id`),
  CONSTRAINT `fk_session_exam_submission_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_session_exam_submission_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_session_exam_submission_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='考试作答表';

CREATE TABLE `session_homework` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `session_id` bigint(20) NOT NULL,
  `homework_code` varchar(64) NOT NULL,
  `homework_name` varchar(128) NOT NULL,
  `created_by` bigint(20) NOT NULL,
  `due_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_homework_code` (`session_id`,`homework_code`),
  KEY `fk_session_homework_created_by` (`created_by`),
  CONSTRAINT `fk_session_homework_created_by` FOREIGN KEY (`created_by`) REFERENCES `staff_profile` (`id`),
  CONSTRAINT `fk_session_homework_session` FOREIGN KEY (`session_id`) REFERENCES `series_cohort_session` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课次作业表';

CREATE TABLE `session_homework_question_rel` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `homework_id` bigint(20) NOT NULL,
  `question_id` bigint(20) NOT NULL,
  `sort_no` int(11) NOT NULL,
  `score` decimal(8,2) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_homework_question_rel` (`homework_id`,`question_id`),
  UNIQUE KEY `uk_session_homework_question_sort` (`homework_id`,`sort_no`),
  KEY `fk_session_homework_question_rel_question` (`question_id`),
  CONSTRAINT `fk_session_homework_question_rel_homework` FOREIGN KEY (`homework_id`) REFERENCES `session_homework` (`id`),
  CONSTRAINT `fk_session_homework_question_rel_question` FOREIGN KEY (`question_id`) REFERENCES `question` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='作业题目关系表';

CREATE TABLE `session_homework_submission` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `homework_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `session_id` bigint(20) NOT NULL,
  `submit_no` varchar(64) NOT NULL,
  `submit_status` varchar(32) NOT NULL COMMENT '枚举：submitted,expired_unsubmitted',
  `total_score` decimal(8,2) DEFAULT NULL,
  `correction_status` varchar(32) NOT NULL COMMENT '枚举：pending,corrected',
  `corrected_by` bigint(20) DEFAULT NULL,
  `feedback_text` text,
  `submitted_at` datetime DEFAULT NULL,
  `corrected_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_homework_submission_no` (`institution_id`,`submit_no`),
  UNIQUE KEY `uk_session_homework_submission_once` (`homework_id`,`student_id`),
  KEY `fk_session_homework_submission_user` (`user_id`),
  KEY `fk_session_homework_submission_student` (`student_id`),
  KEY `fk_session_homework_submission_session` (`session_id`),
  KEY `fk_session_homework_submission_teacher` (`corrected_by`),
  CONSTRAINT `fk_session_homework_submission_homework` FOREIGN KEY (`homework_id`) REFERENCES `session_homework` (`id`),
  CONSTRAINT `fk_session_homework_submission_homework_id` FOREIGN KEY (`homework_id`) REFERENCES `session_homework` (`id`),
  CONSTRAINT `fk_session_homework_submission_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_session_homework_submission_session` FOREIGN KEY (`session_id`) REFERENCES `series_cohort_session` (`id`),
  CONSTRAINT `fk_session_homework_submission_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_session_homework_submission_teacher` FOREIGN KEY (`corrected_by`) REFERENCES `staff_profile` (`id`),
  CONSTRAINT `fk_session_homework_submission_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='作业提交表';

CREATE TABLE `session_teacher_rel` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `session_id` bigint(20) NOT NULL,
  `teacher_id` bigint(20) NOT NULL,
  `sort_no` int(11) NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_teacher_rel` (`session_id`,`teacher_id`),
  KEY `fk_session_teacher_rel_teacher` (`teacher_id`),
  CONSTRAINT `fk_session_teacher_rel_session` FOREIGN KEY (`session_id`) REFERENCES `series_cohort_session` (`id`),
  CONSTRAINT `fk_session_teacher_rel_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `staff_profile` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课次教师关系表';

CREATE TABLE `session_video` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `asset_id` bigint(20) NOT NULL,
  `video_code` varchar(64) NOT NULL,
  `video_title` varchar(128) NOT NULL,
  `cover_url` varchar(255) DEFAULT NULL,
  `duration_seconds` int(11) NOT NULL,
  `resolution_label` varchar(32) DEFAULT NULL,
  `bitrate_kbps` int(11) NOT NULL,
  `transcode_status` varchar(32) NOT NULL COMMENT '枚举：pending,in_progress,completed,failed',
  `review_status` varchar(32) NOT NULL COMMENT '枚举：pending,approved,rejected',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_video_code` (`asset_id`,`video_code`),
  CONSTRAINT `fk_session_video_asset` FOREIGN KEY (`asset_id`) REFERENCES `session_asset` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课次视频表';

CREATE TABLE `session_video_chapter` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `video_id` bigint(20) NOT NULL,
  `chapter_no` int(11) NOT NULL,
  `chapter_title` varchar(128) NOT NULL,
  `start_second` int(11) NOT NULL,
  `end_second` int(11) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_video_chapter_no` (`video_id`,`chapter_no`),
  CONSTRAINT `fk_session_video_chapter_video` FOREIGN KEY (`video_id`) REFERENCES `session_video` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='课次视频章节表';

CREATE TABLE `session_video_play` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `video_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `play_session_no` varchar(64) NOT NULL,
  `device_type` varchar(32) NOT NULL COMMENT '枚举：mobile,tablet,desktop',
  `client_type` varchar(32) NOT NULL COMMENT '枚举：app,h5,pc_web,mini_program',
  `device_os` varchar(32) NOT NULL COMMENT '枚举：ios,android,windows,macos,linux,harmonyos,unknown',
  `last_position_seconds` int(11) NOT NULL DEFAULT '0',
  `progress_percent` decimal(5,2) NOT NULL DEFAULT '0.00',
  `completed_flag` tinyint(4) NOT NULL DEFAULT '0' COMMENT '枚举：0,1',
  `exit_reason` varchar(32) DEFAULT NULL,
  `watched_seconds` int(11) NOT NULL DEFAULT '0',
  `started_at` datetime NOT NULL,
  `ended_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_video_play_no` (`institution_id`,`play_session_no`),
  KEY `fk_session_video_play_video` (`video_id`),
  KEY `fk_session_video_play_user` (`user_id`),
  KEY `fk_session_video_play_student` (`student_id`),
  CONSTRAINT `fk_session_video_play_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_session_video_play_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_session_video_play_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_session_video_play_video` FOREIGN KEY (`video_id`) REFERENCES `session_video` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='视频播放会话表';

CREATE TABLE `session_video_play_event` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `play_session_id` bigint(20) NOT NULL,
  `event_type` varchar(32) NOT NULL COMMENT '枚举：play,pause,resume,seek,complete,exit',
  `position_seconds` int(11) NOT NULL,
  `playback_rate` decimal(4,2) NOT NULL,
  `network_type` varchar(32) NOT NULL COMMENT '枚举：wifi,mobile_5g,mobile_4g,mobile_3g,ethernet,offline,unknown',
  `event_payload` json DEFAULT NULL,
  `event_time` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_session_video_play_event_play_session_id` (`play_session_id`),
  CONSTRAINT `fk_session_video_play_event_play_session_id` FOREIGN KEY (`play_session_id`) REFERENCES `session_video_play` (`id`),
  CONSTRAINT `fk_session_video_play_event_session` FOREIGN KEY (`play_session_id`) REFERENCES `session_video_play` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='视频播放事件表';

CREATE TABLE `shopping_cart_item` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `cohort_id` bigint(20) NOT NULL,
  `unit_price` decimal(12,2) NOT NULL,
  `cart_source` varchar(32) NOT NULL COMMENT '枚举：series_detail,search_result,recommendation,activity_page',
  `added_at` datetime NOT NULL,
  `removed_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_shopping_cart_item` (`user_id`,`cohort_id`),
  KEY `fk_shopping_cart_item_cohort` (`cohort_id`),
  CONSTRAINT `fk_shopping_cart_item_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`),
  CONSTRAINT `fk_shopping_cart_item_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='购物车明细表';

CREATE TABLE `staff_profile` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `institution_id` bigint(20) NOT NULL,
  `campus_id` bigint(20) DEFAULT NULL,
  `dept_id` bigint(20) DEFAULT NULL,
  `staff_no` varchar(64) NOT NULL,
  `staff_role_id` bigint(20) NOT NULL,
  `teacher_intro` text,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_staff_profile_no` (`institution_id`,`staff_no`),
  UNIQUE KEY `uk_staff_profile_user` (`institution_id`,`user_id`),
  KEY `fk_staff_profile_user` (`user_id`),
  KEY `fk_staff_profile_campus` (`campus_id`),
  KEY `fk_staff_profile_dept` (`dept_id`),
  KEY `fk_staff_profile_role` (`staff_role_id`),
  CONSTRAINT `fk_staff_profile_campus` FOREIGN KEY (`campus_id`) REFERENCES `org_campus` (`id`),
  CONSTRAINT `fk_staff_profile_dept` FOREIGN KEY (`dept_id`) REFERENCES `org_department` (`id`),
  CONSTRAINT `fk_staff_profile_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_staff_profile_role` FOREIGN KEY (`staff_role_id`) REFERENCES `org_staff_role` (`id`),
  CONSTRAINT `fk_staff_profile_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='职员档案表';

CREATE TABLE `student_cohort_rel` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `student_id` bigint(20) NOT NULL,
  `cohort_id` bigint(20) NOT NULL,
  `order_item_id` bigint(20) NOT NULL,
  `enroll_status` varchar(32) NOT NULL COMMENT '枚举：active,completed,cancelled,refunded',
  `enroll_at` datetime NOT NULL,
  `completed_at` datetime DEFAULT NULL,
  `cancelled_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_student_cohort_rel_order_item` (`order_item_id`),
  UNIQUE KEY `uk_student_cohort_rel_student_cohort` (`student_id`,`cohort_id`),
  KEY `fk_student_cohort_rel_institution` (`institution_id`),
  KEY `fk_student_cohort_rel_cohort` (`cohort_id`),
  KEY `idx_student_cohort_user_enroll` (`user_id`,`enroll_status`),
  CONSTRAINT `fk_student_cohort_rel_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`),
  CONSTRAINT `fk_student_cohort_rel_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_student_cohort_rel_order_item` FOREIGN KEY (`order_item_id`) REFERENCES `order_item` (`id`),
  CONSTRAINT `fk_student_cohort_rel_student` FOREIGN KEY (`student_id`) REFERENCES `student_profile` (`id`),
  CONSTRAINT `fk_student_cohort_rel_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学员班次关系表';

CREATE TABLE `student_profile` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `learner_identity_id` bigint(20) NOT NULL,
  `learning_goal_id` bigint(20) NOT NULL,
  `education_level_id` bigint(20) DEFAULT NULL,
  `grade_id` bigint(20) DEFAULT NULL,
  `school_name` varchar(128) DEFAULT NULL,
  `entrance_year` int(11) DEFAULT NULL,
  `industry_name` varchar(128) DEFAULT NULL,
  `job_role_name` varchar(128) DEFAULT NULL,
  `career_stage` varchar(64) DEFAULT NULL,
  `years_of_experience` int(11) DEFAULT NULL,
  `profile_note` text,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_student_profile_user` (`user_id`),
  KEY `fk_student_profile_identity` (`learner_identity_id`),
  KEY `fk_student_profile_goal` (`learning_goal_id`),
  KEY `fk_student_profile_education` (`education_level_id`),
  KEY `fk_student_profile_grade` (`grade_id`),
  CONSTRAINT `fk_student_profile_education` FOREIGN KEY (`education_level_id`) REFERENCES `dim_education_level` (`id`),
  CONSTRAINT `fk_student_profile_goal` FOREIGN KEY (`learning_goal_id`) REFERENCES `dim_learning_goal` (`id`),
  CONSTRAINT `fk_student_profile_grade` FOREIGN KEY (`grade_id`) REFERENCES `dim_grade` (`id`),
  CONSTRAINT `fk_student_profile_identity` FOREIGN KEY (`learner_identity_id`) REFERENCES `dim_learner_identity` (`id`),
  CONSTRAINT `fk_student_profile_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='学员档案表';

CREATE TABLE `sys_user` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `account` varchar(64) NOT NULL,
  `username` varchar(64) NOT NULL,
  `nickname` varchar(64) NOT NULL,
  `real_name` varchar(64) DEFAULT NULL,
  `mobile` varchar(32) DEFAULT NULL,
  `email` varchar(128) DEFAULT NULL,
  `gender` varchar(16) DEFAULT NULL,
  `avatar_url` varchar(255) DEFAULT NULL,
  `birthday` date DEFAULT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `status` tinyint(4) NOT NULL DEFAULT '1',
  `last_login_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sys_user_account` (`account`),
  UNIQUE KEY `uk_sys_user_mobile` (`mobile`),
  UNIQUE KEY `uk_sys_user_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='平台账号主表';

CREATE TABLE `sys_user_auth` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL COMMENT '对应 sys_user.id',
  `password_hash` varchar(255) NOT NULL COMMENT 'bcrypt 哈希值（不要存明文）',
  `role_code` varchar(32) NOT NULL DEFAULT 'student' COMMENT '角色：student/teacher/manager/admin',
  `last_password_change_at` datetime DEFAULT NULL COMMENT '最近一次修改密码时间',
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sys_user_auth_user` (`user_id`),
  KEY `idx_sys_user_auth_role` (`role_code`),
  CONSTRAINT `fk_sys_user_auth_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户认证&角色扩展表';

CREATE TABLE `task_execution` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `task_code` varchar(64) NOT NULL COMMENT '任务编码',
  `task_type` varchar(32) NOT NULL COMMENT '任务类型',
  `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/succeeded/failed',
  `tenant_id` varchar(100) DEFAULT NULL COMMENT '租户ID（可选）',
  `progress_json` json DEFAULT NULL COMMENT '进度详情JSON',
  `params_json` json DEFAULT NULL COMMENT '输入参数JSON',
  `result_json` json DEFAULT NULL COMMENT '输出结果JSON',
  `error` text COMMENT '错误信息',
  `retry_count` int(11) NOT NULL DEFAULT '0',
  `max_retries` int(11) NOT NULL DEFAULT '3',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `started_at` datetime DEFAULT NULL,
  `finished_at` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_task_execution_code` (`task_code`),
  KEY `idx_task_execution_type` (`task_type`,`status`),
  KEY `idx_task_execution_status` (`status`,`created_at`),
  KEY `idx_task_execution_tenant` (`tenant_id`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='通用任务执行表（durable execution）';

CREATE TABLE `teacher_compensation_bill` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `bill_no` varchar(64) NOT NULL,
  `teacher_id` bigint(20) NOT NULL,
  `settle_period` varchar(32) NOT NULL,
  `bill_status` varchar(32) NOT NULL COMMENT '枚举：pending,approved,paid',
  `lesson_count` int(11) NOT NULL,
  `base_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `bonus_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `deduction_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `payable_amount` decimal(12,2) NOT NULL,
  `approver_user_id` bigint(20) DEFAULT NULL,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `settled_at` datetime DEFAULT NULL,
  `paid_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_teacher_compensation_bill_no` (`institution_id`,`bill_no`),
  KEY `fk_teacher_compensation_bill_teacher` (`teacher_id`),
  KEY `fk_teacher_compensation_bill_approver` (`approver_user_id`),
  CONSTRAINT `fk_teacher_compensation_bill_approver` FOREIGN KEY (`approver_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_teacher_compensation_bill_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_teacher_compensation_bill_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `staff_profile` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教师课酬账单表';

CREATE TABLE `teacher_compensation_item` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `bill_id` bigint(20) NOT NULL,
  `teacher_id` bigint(20) NOT NULL,
  `cohort_id` bigint(20) DEFAULT NULL,
  `session_id` bigint(20) DEFAULT NULL,
  `item_type` varchar(32) NOT NULL COMMENT '枚举：session_fee,bonus,deduction,adjustment',
  `unit_price` decimal(12,2) DEFAULT NULL,
  `item_amount` decimal(12,2) NOT NULL,
  `remark` text,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_teacher_compensation_item_session_fee` (`bill_id`,`session_id`),
  KEY `fk_teacher_compensation_item_institution` (`institution_id`),
  KEY `fk_teacher_compensation_item_teacher` (`teacher_id`),
  KEY `fk_teacher_compensation_item_cohort` (`cohort_id`),
  KEY `fk_teacher_compensation_item_session` (`session_id`),
  CONSTRAINT `fk_teacher_compensation_item_bill` FOREIGN KEY (`bill_id`) REFERENCES `teacher_compensation_bill` (`id`),
  CONSTRAINT `fk_teacher_compensation_item_cohort` FOREIGN KEY (`cohort_id`) REFERENCES `series_cohort` (`id`),
  CONSTRAINT `fk_teacher_compensation_item_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_teacher_compensation_item_session` FOREIGN KEY (`session_id`) REFERENCES `series_cohort_session` (`id`),
  CONSTRAINT `fk_teacher_compensation_item_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `staff_profile` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='教师课酬明细表';

CREATE TABLE `ugc_moderation_task` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `institution_id` bigint(20) NOT NULL,
  `task_no` varchar(64) NOT NULL,
  `content_type` varchar(32) NOT NULL COMMENT '枚举：topic,post,review',
  `topic_id` bigint(20) DEFAULT NULL,
  `post_id` bigint(20) DEFAULT NULL,
  `review_id` bigint(20) DEFAULT NULL,
  `submit_user_id` bigint(20) NOT NULL,
  `moderator_user_id` bigint(20) DEFAULT NULL,
  `moderation_status` varchar(32) NOT NULL COMMENT '枚举：pending,approved,rejected',
  `risk_level` varchar(32) NOT NULL COMMENT '枚举：low,medium,high',
  `reject_reason` text,
  `yn` tinyint(4) NOT NULL DEFAULT '1',
  `submitted_at` datetime NOT NULL,
  `moderated_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ugc_moderation_task_no` (`institution_id`,`task_no`),
  KEY `fk_ugc_moderation_task_topic` (`topic_id`),
  KEY `fk_ugc_moderation_task_post` (`post_id`),
  KEY `fk_ugc_moderation_task_review` (`review_id`),
  KEY `fk_ugc_moderation_task_submit_user` (`submit_user_id`),
  KEY `fk_ugc_moderation_task_moderator` (`moderator_user_id`),
  CONSTRAINT `fk_ugc_moderation_task_institution` FOREIGN KEY (`institution_id`) REFERENCES `org_institution` (`id`),
  CONSTRAINT `fk_ugc_moderation_task_moderator` FOREIGN KEY (`moderator_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_ugc_moderation_task_post` FOREIGN KEY (`post_id`) REFERENCES `cohort_discussion_post` (`id`),
  CONSTRAINT `fk_ugc_moderation_task_review` FOREIGN KEY (`review_id`) REFERENCES `cohort_review` (`id`),
  CONSTRAINT `fk_ugc_moderation_task_submit_user` FOREIGN KEY (`submit_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_ugc_moderation_task_topic` FOREIGN KEY (`topic_id`) REFERENCES `cohort_discussion_topic` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='内容审核任务表';

CREATE TABLE `user_badge` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) unsigned NOT NULL,
  `badge_code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `unlocked_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `source_note` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '触发描述',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_badge` (`user_id`,`badge_code`),
  KEY `idx_badge` (`badge_code`,`unlocked_at` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P6 用户徽章';

CREATE TABLE `user_kp_mastery` (
  `user_id` bigint(20) unsigned NOT NULL,
  `course_id` bigint(20) NOT NULL,
  `knowledge_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `confidence` decimal(7,6) NOT NULL DEFAULT '0.000000',
  `weighted_accuracy` decimal(7,6) DEFAULT NULL,
  `scored_evidence_count` int(11) NOT NULL DEFAULT '0',
  `unique_question_count` int(11) NOT NULL DEFAULT '0',
  `reason_json` json NOT NULL,
  `evidence_ids_json` json NOT NULL,
  `next_review_at` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`course_id`,`knowledge_code`),
  KEY `idx_user_kp_mastery_due` (`user_id`,`next_review_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `user_memory` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '自增主键（内部用）',
  `user_id` bigint(20) NOT NULL COMMENT '所属用户 ID，对应 sys_user.id（记忆按用户隔离）',
  `memory_type` varchar(32) NOT NULL DEFAULT 'preference' COMMENT '类型: preference/goal/profile/correction/fact',
  `topic` varchar(64) NOT NULL DEFAULT 'general' COMMENT 'topic 分组（learning-goals/debugging 等，用于 MEMORY.md 索引聚合）',
  `content` varchar(2000) NOT NULL COMMENT '记忆正文（用户偏好/目标/纠正/事实）',
  `importance` tinyint(3) unsigned NOT NULL DEFAULT '3' COMMENT '重要性 1-5（规则+LLM 双轨打分；≥4 才写长时记忆）',
  `score` double NOT NULL DEFAULT '0' COMMENT '综合分 = importance×exp(-0.01·Δt)+recency_bonus（遗忘排序用）',
  `access_count` int(11) NOT NULL DEFAULT '0' COMMENT '召回次数（近因/热度加权）',
  `deleted` tinyint(4) NOT NULL DEFAULT '0' COMMENT '软删标记 0=有效 1=被遗忘/淘汰（物理 DELETE 禁止）',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '写入时间（时间衰减基准）',
  `last_access_at` datetime(3) DEFAULT NULL COMMENT '最近一次被召回时间（recency_bonus 基准）',
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `idx_um_user_created` (`user_id`,`created_at`),
  KEY `idx_um_user_score` (`user_id`,`score`),
  KEY `idx_um_user_type` (`user_id`,`memory_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='P4.5 AI 助手长时记忆（三层记忆 Long-term 事实源 + 遗忘曲线）';

CREATE TABLE `user_memory_entity_seq` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `user_memory_event` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `event_type` varchar(32) NOT NULL,
  `entity_id` bigint(20) NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `memory_type` varchar(32) DEFAULT NULL,
  `topic` varchar(64) DEFAULT NULL,
  `content` text NOT NULL,
  `embedding` json DEFAULT NULL,
  `importance` int(11) DEFAULT NULL,
  `score` float DEFAULT NULL,
  `access_count` int(11) NOT NULL DEFAULT '0',
  `last_access_at` datetime DEFAULT NULL,
  `valid_from` datetime NOT NULL,
  `valid_to` datetime DEFAULT NULL,
  `trace_id` varchar(64) DEFAULT NULL,
  `operator` varchar(64) DEFAULT NULL,
  `supports` json DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_event_user` (`user_id`,`entity_id`,`valid_to`),
  KEY `idx_event_trace` (`trace_id`),
  KEY `idx_event_entity` (`entity_id`,`valid_to`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `user_point_log` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) unsigned NOT NULL,
  `biz_key` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '业务幂等键，如 quiz-correct-Q1-u2-t20260809',
  `point_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'LEARN_MIN/QUIZ_CORRECT/HW_SUBMIT/EXAM_PASS/LIKE_GAIN/BADGE_BONUS',
  `delta` int(11) NOT NULL,
  `balance_after` int(11) NOT NULL,
  `note` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_biz` (`user_id`,`biz_key`),
  KEY `idx_user_created` (`user_id`,`created_at` DESC),
  KEY `idx_type_created` (`point_type`,`created_at` DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P6 积分流水（当前等级可由总积分推导）';

CREATE TABLE `user_profile` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL COMMENT '关联 sys_user.id（一对一）',
  `nickname` varchar(64) DEFAULT NULL COMMENT '用户自定义昵称（可覆盖 sys_user.username）',
  `avatar_url` varchar(255) DEFAULT NULL COMMENT '头像 URL',
  `gender` varchar(16) DEFAULT NULL COMMENT '枚举：male/female/other/secret',
  `birthday` date DEFAULT NULL COMMENT '生日（计算推荐年龄范围用）',
  `grade_code` varchar(32) DEFAULT NULL COMMENT '学业层级代码，参考 dim_grade：小学/初中/高中/本科/硕士/社会',
  `school_name` varchar(128) DEFAULT NULL COMMENT '学校或单位',
  `region_code` varchar(32) DEFAULT NULL COMMENT '地区/省份代码',
  `weekly_available_hours` int(11) NOT NULL DEFAULT '5' COMMENT '每周可学习小时数（推荐时用来控制进度）',
  `study_style` varchar(32) DEFAULT NULL COMMENT '视觉型(visual)/听觉型(auditory)/动手型(kinesthetic)/混合型(mixed)',
  `target_qualification` varchar(128) DEFAULT NULL COMMENT '目标证书/考试：CET-4/雅思7分/考研/Python二级',
  `learning_goals` json DEFAULT NULL COMMENT '学习目标列表：["英语CET-4 500分","Python 二级证书"]',
  `subject_preferences` json DEFAULT NULL COMMENT '学科偏好：[{"subject_code":"english","preference_score":5},{"subject_code":"programming","preference_score":4}]',
  `level_assessments` json DEFAULT NULL COMMENT '水平自评：[{"subject_code":"english","level_code":"L2","assessed_at":"2026-08-01 12:00:00"}]',
  `interest_tags` json DEFAULT NULL COMMENT '兴趣标签：["背单词","英语口语","机器学习"]',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_profile_user_id` (`user_id`),
  CONSTRAINT `fk_user_profile_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户画像（个性化学习路径 P4 推荐的核心输入）';

CREATE TABLE `user_vocab_card` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) unsigned NOT NULL,
  `vocab_entry_id` bigint(20) unsigned NOT NULL,
  `ease_factor` decimal(5,3) NOT NULL DEFAULT '2.500' COMMENT 'EF ≥ 1.300，默认 2.5，答对难度低会上涨',
  `interval_days` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '下一次复习间隔天数（I=0 新词；I=1 再答；I=6 之后按 EF*I 推进）',
  `repetition` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '连续答对次数（quality≥3 就递增；失败归零）',
  `due_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '到期时间，<=now() 就是今天应复习',
  `last_quality` tinyint(3) unsigned DEFAULT NULL COMMENT '最近一次 SM-2 quality 0-5',
  `last_review_at` datetime DEFAULT NULL,
  `total_reviews` int(10) unsigned NOT NULL DEFAULT '0',
  `total_correct` int(10) unsigned NOT NULL DEFAULT '0',
  `mastery_status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'NEW' COMMENT 'NEW / LEARNING / REVIEW / MASTERED',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_vocab` (`user_id`,`vocab_entry_id`),
  KEY `idx_user_due` (`user_id`,`due_at`,`mastery_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P5 用户单词卡 SM-2 记忆曲线表';

CREATE TABLE `video_knowledge_task` (
  `id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_id` bigint(20) NOT NULL,
  `bvid` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `page` int(11) NOT NULL,
  `transcript_mode` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` bigint(20) NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'queued',
  `stage` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'acquiring',
  `attempt` int(11) NOT NULL DEFAULT '0',
  `data_json` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `error_code` varchar(80) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reviewed_by` bigint(20) DEFAULT NULL,
  `reviewed_at` datetime(6) DEFAULT NULL,
  `lease_token` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_expires_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `idx_video_task_queue` (`status`,`created_at`),
  KEY `idx_video_task_session` (`session_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `video_learning_exercise` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `video_id` bigint(20) NOT NULL,
  `session_id` bigint(20) NOT NULL,
  `generation` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `artifact_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bank_id` bigint(20) NOT NULL,
  `question_count` int(11) NOT NULL,
  `package_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `package_json` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_video_exercise_version` (`video_id`,`artifact_sha256`),
  UNIQUE KEY `uq_video_exercise_bank` (`bank_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `video_learning_publication` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `video_id` bigint(20) NOT NULL,
  `artifact_id` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `artifact_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `object_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bucket` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `object_key` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `size_bytes` bigint(20) NOT NULL,
  `published_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `rag_status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'ready',
  `previous_publication_id` bigint(20) unsigned DEFAULT NULL,
  `activated_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_video_artifact` (`video_id`,`artifact_sha256`),
  KEY `idx_video_publication` (`video_id`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `vocab_entry` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `word` varchar(96) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '单词（小写规范化）',
  `level_code` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'L1..L5 对应小学→专八',
  `subject_code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'english',
  `phonetic_us` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '美式音标',
  `phonetic_uk` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '英式音标',
  `pos_json` json DEFAULT NULL COMMENT '词性数组 ["n.","v."]',
  `meaning_cn` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `example_en` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '英文例句',
  `example_cn` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '例句翻译',
  `topic_tag` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '主题标签：日常/校园/旅行/...',
  `image_hint` varchar(256) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '看图选词占位 URL',
  `audio_us` varchar(256) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '美音文件占位',
  `yn` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_vocab_word_level` (`word`,`level_code`),
  KEY `idx_vocab_level_topic` (`level_code`,`topic_tag`,`yn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='P5 分级词库';

SET FOREIGN_KEY_CHECKS=1;
