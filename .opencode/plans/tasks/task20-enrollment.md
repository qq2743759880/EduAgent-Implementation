# task20: enrollment 域新建（/me/cohorts 4 端点 + 满班并发验证在下单路径）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P4 ｜**并行组**：W2 ｜**工作量**：M
> **前置**：task18, task11 ｜**后置（联调节点）**：**契约冻结⑪（与 task21 合并发布）→ 前端 task47（/my-courses）、task48（/learning）**；task21/22 依赖
> **范围裁定（2026-08-21 用户确认）**：**只做 4 个读端点**；不新增 POST /api/enrollments——因 `student_cohort_rel.order_item_id` NOT NULL+UNIQUE+FK→order_item，手动报名无法独立创建 enrollment；满班并发控制已由 task17 下单路径 `occupy_seat`（条件更新）承担，GWT① 改为在 service 层补并发验证脚本证明（不新增写端点）。

## 1. 选型依据
- tech-source-audit.md §四（满班条件更新 `current_student_count < max_student_count` 并发控制）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 报名查询/状态/进度聚合 |
| 测试 | sd-tester + sd-challenger | 余位 1 双并发攻防 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
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
- GET /api/enrollments/me/cohorts?status=（enroll_status 过滤 + 进度聚合 series_cohort_session + 提交表）、报名详情、进度快照、状态查询（**4 个读端点，不新增写端点**）
- 满班并发验证：**在 task17 order service 的 occupy_seat 上补 Service 级并发脚本**（模拟余位 1 + 2 并发下单，证明条件更新 0 行→409），不新增 POST /api/enrollments
- enroll_status ∈ {active,completed,cancelled,refunded}
- student_cohort_rel.order_item_id 由 task17/18 下单+支付回调写入（order_item NOT NULL 约束）

## 5. 验收标准（Given/When/Then 全文）
- Given 班次余位 1，When 2 个并发下单请求（走 task17 occupy_seat），Then 仅 1 成功、另一返回 409"班次已满"——**Service 级并发验证脚本证明**（不新增 enrollment 写端点）
- Given 报名 active 用户，When 请求 /me/cohorts?status=active，Then 返回班次 + 模块/课次完成率聚合（供前端进度条），退款后 enroll_status=refunded 自动移入"已退款"tab
- Given 支付回调（task18）触发报名，When 成功，Then student_cohort_rel 记录正确且余位递减

## 6. 交接与记忆（契约冻结⑪）
- 完成 → 与 task21 合并写 `handoffs/task20-21-contract.md`（/me/cohorts + study 10 端点）
- 看板 task20=READY_FOR_FRONTEND（task21 完成后一并解锁 TraeWork task47/48）→ sync.ps1
- 交付物：domains/enrollment + pytest（并发）+ 交接单
