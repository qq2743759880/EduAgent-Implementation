-- EduAgent MySQL 初始化脚本（Phase 2 读写分离 + Phase 4 运维）
-- 在 MySQL 容器首次启动时自动执行，创建只读账号和基础权限

-- 创建只读账号（用于读写分离）
CREATE USER IF NOT EXISTS 'edu_ro'@'%' IDENTIFIED BY 'edu_ro_pwd_2026';
GRANT SELECT ON edu.* TO 'edu_ro'@'%';
FLUSH PRIVILEGES;

-- 慢查询日志开关（生产环境建议开启）
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 0.2;
SET GLOBAL log_queries_not_using_indexes = 'ON';