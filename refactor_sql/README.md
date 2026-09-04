# task01: 66 表 DDL 重建脚本

## 文件说明

| 文件 | 用途 |
|------|------|
| `01_drop_create_all.sql` | DROP IF EXISTS + CREATE 全部 66 表（按依赖排序） |
| `02_rollback.sql` | 回滚到 task00 备份状态 |
| `03_self_built_keep.txt` | 30 张自建表清单（不受重构影响） |

## 执行顺序

```bash
# 1. 先执行 DDL 重建（在测试库验证）
mysql -uroot -p123456 < refactor_sql/01_drop_create_all.sql

# 2. 验证表数量
mysql -uroot -p123456 -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu'"
# 应返回: 66 + 30 = 96

# 3. 回滚（如需要）
# 按 02_rollback.sql 中的说明从 task00 备份恢复
```

## MySQL 保留字处理

以下表名使用反引号转义：
- `order` → \`order\`
- `question` → \`question\`

## 依赖顺序

1. dim_* (7 张维表，无外键依赖)
2. org_* (10 张组织表，依赖 dim_*)
3. sys_user / staff_profile / student_profile (3 张用户表)
4. 业务表 (46 张，依赖以上)
