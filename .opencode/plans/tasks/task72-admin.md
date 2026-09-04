# task72 — 管理端补全任务

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：契约冻结⑨ 退款审批 → 解锁 task79
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：backend｜**依赖**：task19, task28｜**并行组**：W2｜**工作量**：L｜**执行工具**：Trae
- **交付物**：GET /api/admin/refunds（status/原因/分页）、GET /api/admin/refunds/{id}、POST /api/admin/refunds/{id}/approve（执行退款+订单回滚+报名联动）、POST /api/admin/refunds/{id}/reject（含 remark）；对接 task28 LangGraph interrupt
- **验收标准**：
  - Given 退款单 pending，When admin 审批通过，Then 退款落库+order=refunded+student_cohort_rel=refunded 原子完成；拒绝时返回 remark 供 C 端展示；并发重复审批仅一次生效
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev(+be-architect) → sd-tester + sd-challenger(并行) → review-*
- MCP：context7(LangGraph HITL)；skill: harden
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task72-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：契约冻结⑨ 退款审批 → 解锁 task79（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task72-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
