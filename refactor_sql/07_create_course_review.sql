-- ═══════════════════════════════════════════════════════════════════════════
-- 07_create_course_review.sql — 课程系列评价表（Season-2 需求 B）
-- ═══════════════════════════════════════════════════════════════════════════
-- 用途：为课程/系列新增评价。同一 user + series 唯一（DB 级防刷）。
-- 删除语义：软删（yn=0），遵循 C-C 删除语义（不物理删除，可恢复/允许重新评价）。
--
-- 字段与需求对齐：
--   id          自增主键
--   series_id   课程系列 ID（评价对象）
--   user_id     评价用户 ID（sys_user.id）
--   rating      评分 1~5（必填）
--   content     评价内容（可选）
--   yn          有效标记：1=有效 0=软删
--   created_at / updated_at
--
-- 唯一键 uk_course_review_series_user(series_id, user_id)：防同用户重复评价。
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS course_review (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    series_id   BIGINT NOT NULL COMMENT '课程系列 ID',
    user_id     BIGINT NOT NULL COMMENT '评价用户 ID',
    rating      TINYINT NOT NULL COMMENT '评分 1~5',
    content     VARCHAR(2000) NULL COMMENT '评价内容',
    yn          TINYINT NOT NULL DEFAULT 1 COMMENT '有效标记：1=有效 0=软删',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_course_review_series_user (series_id, user_id),
    KEY idx_course_review_series (series_id, yn)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='课程系列评价表';