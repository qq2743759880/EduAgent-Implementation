-- ============================================================
-- task01 回滚脚本: 恢复到 task00 备份状态
-- 使用方法: mysql -uroot -p123456 < 02_rollback.sql
-- ============================================================

-- 方案: 从 task00 的 edu_full_dump.sql 恢复 edu 库
-- 注意: 此操作会覆盖 edu 库中所有数据, 包括自建表

-- 手动执行:
--   1. mysql -uroot -p123456 -e "DROP DATABASE IF EXISTS edu"
--   2. mysql -uroot -p123456 -e "CREATE DATABASE edu CHARACTER SET utf8mb4"
--   3. mysql -uroot -p123456 edu < deploy/backups/20260816_task00/edu_full_dump.sql
--   4. mysql -uroot -p123456 -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu'"
--     -- 应返回 106

-- 或一键恢复:
--   mysql -uroot -p123456 -e "DROP DATABASE IF EXISTS edu; CREATE DATABASE edu CHARACTER SET utf8mb4"
--   mysql -uroot -p123456 edu < deploy/backups/20260816_task00/edu_full_dump.sql
