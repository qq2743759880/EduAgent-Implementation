-- ═══════════════════════════════════════════════════════════════════════════
-- 06_task123_clean_itest.sql — 清理接口验收残留测试种子（itest-*）
-- ═══════════════════════════════════════════════════════════════════════════
-- 用途：清偿 task123「流程收尾包」L17（测试种子残留）。删除以下测试数据：
--   1. itest-newuser 账号（sys_user id=100019 + sys_user_auth ）
--   2. itest-series / itest-sweep-*（off_sale）/ itest-del-check-* 系列
--      （series 9 行：2629~2635, 2648, 2653，series_code LIKE 'itest-%'）
--      ——含 series_cohort / series_cohort_course / series_cohort_session
--         / session_asset / session_video / session_video_chapter 依赖链
--
-- ║ 重要安全声明 ║
--   删除种子数据是一次不可逆操作。执行本脚本前【必须已备份】：
--     mysqldump -uroot -p123456 edu \
--       sys_user sys_user_auth user_profile student_profile staff_profile \
--       series series_cohort series_cohort_course series_cohort_session \
--       session_asset session_video session_video_chapter \
--       > backup_task123_itest_$(date +%Y%m%d_%H%M%S).sql
--   （MySQL 8 支持单次多表 dump；如拟全量兜底改 dump 全库 edu）
--
--   本脚本由编排者在备份后统一执行。任务执行者不越权执行（只产出留档）。
-- ═══════════════════════════════════════════════════════════════════════════

-- 开始事务（可在事务内回滚，配合备份更稳妥）
START TRANSACTION;

-- 临时关闭外键检查（按子→父顺序删除时本可不开，作为兜底防御，
-- 避免未穷尽的外键引用导致 DELETE 失败抛错中断）
SET FOREIGN_KEY_CHECKS = 0;

-- ─────────────────────────────────────────────────────────────────────────
-- 第 1 组：itest-newuser 账号（sys_user）
-- 依赖：sys_user_auth / user_profile / student_profile / staff_profile 外键指向 sys_user
--       （实测仅 sys_user_auth 有 1 行，其余 0 行）
-- ─────────────────────────────────────────────────────────────────────────
DELETE FROM sys_user_auth
WHERE user_id IN (SELECT id FROM sys_user WHERE account LIKE 'itest-%');

DELETE FROM user_profile
WHERE user_id IN (SELECT id FROM sys_user WHERE account LIKE 'itest-%');

DELETE FROM student_profile
WHERE user_id IN (SELECT id FROM sys_user WHERE account LIKE 'itest-%');

DELETE FROM staff_profile
WHERE user_id IN (SELECT id FROM sys_user WHERE account LIKE 'itest-%');

DELETE FROM sys_user
WHERE account LIKE 'itest-%';

-- ─────────────────────────────────────────────────────────────────────────
-- 第 2 组：itest 系列及依赖链（series / series_cohort / ... / session_video_chapter）
-- 实测依赖链为空（series_cohort=0、modules/sessions/assets/videos/chapters=0），
-- 下列子表删除为保证完整（子→父顺序），命中 0 行亦无副作用。
-- ─────────────────────────────────────────────────────────────────────────
-- 2.0 课次视频章节（依赖 video）
DELETE FROM session_video_chapter
WHERE video_id IN (
    SELECT id FROM session_video WHERE asset_id IN (
        SELECT id FROM session_asset WHERE session_id IN (
            SELECT id FROM series_cohort_session WHERE series_cohort_course_id IN (
                SELECT id FROM series_cohort_course WHERE cohort_id IN (
                    SELECT id FROM series_cohort WHERE series_id IN (
                        SELECT id FROM series WHERE series_code LIKE 'itest-%'))))));

-- 2.1 课次回放视频（依赖 session_asset）
DELETE FROM session_video
WHERE asset_id IN (
    SELECT id FROM session_asset WHERE session_id IN (
        SELECT id FROM series_cohort_session WHERE series_cohort_course_id IN (
            SELECT id FROM series_cohort_course WHERE cohort_id IN (
                SELECT id FROM series_cohort WHERE series_id IN (
                    SELECT id FROM series WHERE series_code LIKE 'itest-%')))));

-- 2.2 课次素材（依赖 series_cohort_session）
DELETE FROM session_asset
WHERE session_id IN (
    SELECT id FROM series_cohort_session WHERE series_cohort_course_id IN (
        SELECT id FROM series_cohort_course WHERE cohort_id IN (
            SELECT id FROM series_cohort WHERE series_id IN (
                SELECT id FROM series WHERE series_code LIKE 'itest-%'))));

-- 2.3 课次（依赖 series_cohort_course）
DELETE FROM series_cohort_session
WHERE series_cohort_course_id IN (
    SELECT id FROM series_cohort_course WHERE cohort_id IN (
        SELECT id FROM series_cohort WHERE series_id IN (
            SELECT id FROM series WHERE series_code LIKE 'itest-%')));

-- 2.4 模块/course（依赖 series_cohort）
DELETE FROM series_cohort_course
WHERE cohort_id IN (
    SELECT id FROM series_cohort WHERE series_id IN (
        SELECT id FROM series WHERE series_code LIKE 'itest-%'));

-- 2.5 班次（依赖 series）
DELETE FROM series_cohort
WHERE series_id IN (SELECT id FROM series WHERE series_code LIKE 'itest-%');

-- 2.6 系列本体（含 itest-series / itest-sweep-* off_sale / itest-del-check-*）
--     外部引用表实测均为 0：series_category_rel / coupon_series_rel /
--     series_exposure_log / series_search_log / series_favorite / series_visit_log
DELETE FROM series
WHERE series_code LIKE 'itest-%';

-- 恢复外键检查
SET FOREIGN_KEY_CHECKS = 1;

COMMIT;

-- 校验（执行后应全部返回 0，与 GWT 一致）
--   SELECT COUNT(*) FROM sys_user WHERE account LIKE 'itest-%';        -- => 0
--   SELECT COUNT(*) FROM series   WHERE series_code LIKE 'itest-%';    -- => 0