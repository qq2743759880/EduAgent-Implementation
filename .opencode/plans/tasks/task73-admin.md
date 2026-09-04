# task73 — 管理端补全任务

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：契约冻结⑩ 学员画像 → 解锁 task80/81
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：backend｜**依赖**：task20, task21｜**并行组**：W2｜**工作量**：XL｜**执行工具**：Trae
- **交付物**：GET /api/admin/cohorts/{id}/students（学员列表+进度聚合）、GET /api/admin/students/{id}/profile（学习画像）、GET /api/admin/students/{id}/answers（作答详情：每题答案/判分/解析）、POST /api/admin/cohorts/{id}/students/{sid}/kick
- **验收标准**：
  - Given 班级学员列表，When 请求，Then 返回姓名/进度条/出勤/作业完成/考试分聚合；学员详情含作答明细（引用 question 表解析）；移出班级后 student_cohort_rel 状态联动
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev → sd-tester → review-*
- MCP：RunCommand+mysql CLI
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task73-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：契约冻结⑩ 学员画像 → 解锁 task80/81（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task73-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
