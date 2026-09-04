# task70 — 管理端补全任务

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：契约冻结⑦ 公告/站内信 → 解锁 task84/85
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：backend｜**依赖**：task03, task10｜**并行组**：W2｜**工作量**：L｜**执行工具**：Trae
- **交付物**：announcement/user_notification 2 张新表 DDL + 公告 CRUD（发布/下线/范围选择）+ 站内信（发送/未读列表/已读）+ C 端 GET /api/me/notifications
- **验收标准**：
  - Given 管理端发布公告，When 选范围(all/cohort/grade)并发布，Then 目标学员 GET /api/me/notifications 可见且未读角标+1；已读置位后不再出现
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev → sd-tester → review-*
- MCP：RunCommand+mysql CLI；skill: mermaid(表设计)
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task70-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：契约冻结⑦ 公告/站内信 → 解锁 task84/85（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task70-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
