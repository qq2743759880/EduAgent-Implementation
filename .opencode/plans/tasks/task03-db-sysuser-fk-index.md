# task03: sys_user 改造 + 外键语义恢复 + 查询索引（动作 B/E）

> **类型**：database ｜**执行工具**：Trae ｜**阶段**：P1 ｜**并行组**：W1 ｜**工作量**：M
> **前置**：task01 ｜**后置（联调节点）**：task11（course 域 user 关联）、task14（users bug 修复依赖 sys_user）

## 1. 选型依据
- tech-source-audit.md §一（edu.sql 权威 + 唯一键/外键严格按 edu.sql）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | ALTER + 外键 + 索引脚本 |
| 验证 | sd-tester + RunCommand+mysql CLI | EXPLAIN 6 大查询场景 |
| 审查 | review-screener-1 | 外键恢复顺序（先数据后约束） |
| 提交 | commit skill | — |

## 3. 执行方式（Trae 手动调度，无 Workflow API）

Trae Code 无 opencode 专属的 `Workflow()` API，按 `D:\.ai-hub\workflows\dev-standard.mjs` 的 8 阶段**手动调度**（效果等价）：
```
1. 开发阶段   -> 调 sd-dev + be-architect + be-validator（读任务文档 + tech-source-audit）
2. 测试阶段   -> 调 sd-tester（+ sd-challenger 对抗）；数据库校验用 RunCommand 跑 mysql CLI / Python 脚本（无 mysql MCP）
3. 修正阶段   -> 据测试报告回 sd-dev 修复
4. 审查阶段   -> 调 review-screener-1/2/3 -> review-moderator -> review-judge（SARIF）
5. 提交阶段   -> git commit（message 含 task 编号）
```

mysql MCP 未在 Trae 环境注册（当前 MCP 仅 integrated_code_mode / integrated_goal）：
- 数据库校验改用 **RunCommand + mysql CLI / Python 脚本**（先例：scripts/verify_schema.py、scripts/verify_task07_counts.py）
- 或手动在 设置->MCP 按 `D:\.ai-hub\mcp\index.json` 模板添加 mysql


## 4. 实现规划要点
- sys_user：edu.sql 原列 + account（唯一）/username/status 扩展列合并
- 外键恢复：session_homework_submission.homework_id→session_homework、session_exam_submission.exam_id→session_exam、session_video_play_event.play_session_id→session_video_play
- 索引清单（10 组）：series(institution_id,sale_status)、series_cohort(series_id,sale_status)、series_cohort_session(series_cohort_course_id,session_no)、question(bank_id)、`order`(user_id,order_status,created_at)、order_item(order_id)、payment_record(order_id)、student_cohort_rel(user_id,enroll_status)、session_attendance(session_id,attendance_status)、service_ticket(user_id,ticket_status)、series_visit_log(series_id,created_at)
- 外键恢复需先清理/补全脏数据再建约束

## 5. 验收标准（Given/When/Then 全文）
- Given sys_user 改造完成，When 执行注册/登录/JWT 刷新流程，Then 全链路可用且 account 唯一约束生效（重复注册 409）
- Given 外键恢复，When 提交非法 homework_id 的作业记录，Then 数据库拒绝（外键约束生效），后端将该错误映射为业务错误码而非 500
- Given 索引就绪，When 对 6 大查询场景执行 EXPLAIN，Then 全部走索引（type=ref/range，无全表扫描）
- Given sys_user_auth 未动，When 验证双 token 刷新，Then 现有认证体系不受影响

## 6. 交接与记忆
- 完成 → 看板 task03=DONE → sync.ps1
- 交付物：ALTER 脚本 + 外键恢复脚本 + 索引清单 + EXPLAIN 报告
