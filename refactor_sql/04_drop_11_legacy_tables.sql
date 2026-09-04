-- task02: 删除 11 张平行旧表（动作 C）
-- 执行时间: 2026-08-16
-- 替代表映射:
--   curriculum_* → series 系
--   admin_question_bank/admin_question → question_bank/question
--   admin_exam_paper/admin_exam_paper_item → session_exam/session_exam_question_rel
--   admin_question_tag/admin_question_to_tag → 全文检索（删除后重构）
--   admin_course_video_asset → session_asset/session_video/session_video_chapter

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS admin_question_to_tag;
DROP TABLE IF EXISTS admin_question_tag;
DROP TABLE IF EXISTS admin_exam_paper_item;
DROP TABLE IF EXISTS admin_exam_paper;
DROP TABLE IF EXISTS admin_question;
DROP TABLE IF EXISTS admin_question_bank;
DROP TABLE IF EXISTS admin_course_video_asset;
DROP TABLE IF EXISTS curriculum_session;
DROP TABLE IF EXISTS curriculum_module;
DROP TABLE IF EXISTS curriculum_cohort;
DROP TABLE IF EXISTS curriculum_series;

SET FOREIGN_KEY_CHECKS = 1;

-- 验证: SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu';
-- 应返回 95 (106 - 11)