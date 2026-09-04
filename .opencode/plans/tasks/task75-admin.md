# task75 — 管理端补全任务

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：契约冻结⑪ 工单管理 → 解锁 task83
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：backend｜**依赖**：task22｜**并行组**：W2｜**工作量**：M｜**执行工具**：Trae
- **交付物**：GET /api/admin/tickets（type/status/priority/分页）、GET /api/admin/tickets/{id}、POST /api/admin/tickets/{id}/reply（客服回复→follow_record）、POST /api/admin/tickets/{id}/assign、POST /api/admin/tickets/{id}/close、GET /api/admin/tickets/satisfaction-stats
- **验收标准**：
  - Given 工单列表，When 按类型/优先级过滤，Then 返回含 first_response_at 的工单；详情含多轮时间线；客服回复写入 follow_record；满意度统计聚合 score 分布
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev → sd-tester → review-*
- MCP：RunCommand+mysql CLI
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task75-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：契约冻结⑪ 工单管理 → 解锁 task83（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task75-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
