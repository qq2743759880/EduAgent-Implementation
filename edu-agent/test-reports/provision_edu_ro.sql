-- ============================================================
-- write-read 根因修复：补建只读账号 edu_ro（GRANT SELECT 仅读）
-- 作用：让 init_mysql_ro() 成功初始化 autocommit=True 的只读连接池，
--       读请求回到设计的只读池，不再因账号缺失降级到主池(autocommit=False)，
--       从而消除「写已 commit 但读读不到刚提交行」的根因。
-- 可重跑：IF NOT EXISTS 幂等；重复执行无副作用。
-- 用法：mysql -u root -p < test-reports/provision_edu_ro.sql
--       （或在本项目根连接上直接执行本文件）
-- ============================================================

CREATE USER IF NOT EXISTS 'edu_ro'@'localhost' IDENTIFIED BY 'edu_ro_pwd_2026';
CREATE USER IF NOT EXISTS 'edu_ro'@'127.0.0.1' IDENTIFIED BY 'edu_ro_pwd_2026';
CREATE USER IF NOT EXISTS 'edu_ro'@'%' IDENTIFIED BY 'edu_ro_pwd_2026';

-- 仅为安全兜底按需调整：生产环境应进一步收紧到最小表集合。
GRANT SELECT ON edu.* TO 'edu_ro'@'localhost';
GRANT SELECT ON edu.* TO 'edu_ro'@'127.0.0.1';
GRANT SELECT ON edu.* TO 'edu_ro'@'%';

FLUSH PRIVILEGES;