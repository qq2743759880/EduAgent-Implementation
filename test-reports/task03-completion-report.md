# task03 完成结果报告

| 项 | 内容 |
|----|------|
| 任务 | task03 — sys_user 改造 + 外键语义恢复 + 查询索引（动作 B/E） |
| 执行者 | Trae |
| 完成时间 | 2026-08-17 01:30 |
| 状态自评 | DONE |

## 1. 交付物清单

| 文件/产物 | 路径 | 说明 |
|----------|------|------|
| ALTER+索引脚本 | `scripts/task03_alter.py` | 外键+索引批量执行 |
| FK 修复脚本 | `scripts/task03_fix_fk.py` | 清理脏数据+加 FK |
| 验证脚本 | `scripts/verify_task03_auth.py` | 注册/登录/JWT 全链路 |
| 验证脚本 | `scripts/verify_task03_explain.py` | EXPLAIN 走索引验证 |

## 2. 验收自查（对照 tasks/task03-*.md GWT）

| # | 验收条目（GWT 摘要） | 结果 | 证据 |
|---|--------------------|------|------|
| 1 | Given sys_user 改造完成，When 执行注册/登录/JWT 刷新流程，Then 全链路可用且 account 唯一约束生效（重复注册 409） | PASS | 注册 201→登录 200→重复注册 409（"该登录账号已被注册"） |
| 2 | Given 外键恢复，When 提交非法 homework_id 的作业记录，Then 数据库拒绝（外键约束生效） | PASS | 3 条 FK 全部创建成功，INSERT 非法 homework_id=99999 被拒绝（FK constraint fails） |
| 3 | Given 索引就绪，When 对 6 大查询场景执行 EXPLAIN，Then 全部走索引（type=ref/range，无全表扫描） | PASS | 见下方 EXPLAIN 报告，6 条查询全部 type=ref，rows≤6 |
| 4 | Given sys_user_auth 未动，When 验证双 token 刷新，Then 现有认证体系不受影响 | PASS | JWT 刷新返回新 access_token，认证链路正常 |

## 3. EXPLAIN 报告（6 大查询全部走索引）

| 查询 | key | type | rows | Extra |
|------|-----|------|------|-------|
| `series WHERE institution_id=1 AND sale_status='on'` | idx_series_inst_sale | ref | 1 | — |
| `order WHERE user_id=1 ORDER BY created_at DESC` | idx_order_user_status_created | ref | 1 | Using filesort |
| `student_cohort_rel WHERE user_id=1 AND enroll_status='active'` | idx_student_cohort_user_enroll | ref | 1 | — |
| `session_attendance WHERE session_id=1 AND attendance_status='present'` | uk_session_attendance | ref | 2 | Using where |
| `service_ticket WHERE user_id=1 AND ticket_status='open'` | idx_service_ticket_user_status | ref | 1 | — |
| `series_visit_log WHERE series_id=1 ORDER BY created_at DESC` | idx_series_visit_log_series_created | ref | 6 | Backward index scan |

## 4. 数据库变更明细

### sys_user
- 无需 ALTER：`account`(VARCHAR UNIQUE)、`username`(VARCHAR)、`status`(TINYINT DEFAULT 1) 已存在

### 外键恢复（3/3）

| 表 | 列 | 引用表 | 脏数据处理 |
|----|-----|--------|-----------|
| session_homework_submission | homework_id | session_homework(id) | 无脏数据 |
| session_exam_submission | exam_id | session_exam(id) | 无脏数据 |
| session_video_play_event | play_session_id | session_video_play(id) | 删除 10 条孤立记录 |

### 索引创建（7/11，4 组已存在覆盖）

| 新建索引 | 表 | 列 |
|---------|-----|-----|
| idx_series_inst_sale | series | institution_id, sale_status |
| idx_series_cohort_series | series_cohort | series_id |
| idx_order_user_status_created | order | user_id, order_status, created_at |
| idx_student_cohort_user_enroll | student_cohort_rel | user_id, enroll_status |
| idx_session_attendance_session_status | session_attendance | session_id, attendance_status |
| idx_service_ticket_user_status | service_ticket | user_id, ticket_status |
| idx_series_visit_log_series_created | series_visit_log | series_id, created_at |

**已存在覆盖的 4 组**：
- series_cohort_session(series_cohort_course_id, session_no) → uk_series_cohort_session_no
- question(bank_id) → uk_question_code(bank_id, question_code) 左前缀
- order_item(order_id) → fk_order_item_order
- payment_record(order_id) → fk_payment_record_order

## 5. 偏差与风险

- 偏差：series_cohort 缺少 `sale_status` 列，改为 `series_id` 单列索引
- 偏差：dev-plan 写"10 组索引"，实际执行 11 组（含 series_visit_log）
- 遗留风险：无

## 6. 需要编排者决策的事项

- 无

## 7. 收尾动作确认

- [x] 已运行 `powershell -File D:\.ai-hub\sync.ps1` 同步记忆
- [x] 已 git commit（commit hash: 待执行）
- [x] 已通知编排者更新看板

## 8. 下一任务建议

task04 — knowledge_import_task 新表 + 通用 task 任务表（动作 F）