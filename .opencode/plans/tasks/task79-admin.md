# task79 — 管理端补全任务

> 执行工具：**TraeWork** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：消费契约⑨
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：frontend｜**依赖**：task41, task72｜**并行组**：W7｜**工作量**：L｜**执行工具**：TraeWork
- **交付物**：退款单列表（状态/原因筛选）+ 详情+审批弹窗（通过/拒绝填理由）+ 拒绝理由展示
- **验收标准**：
  - Given 退款单，When admin 审批，Then 通过后状态流转+报名联动提示；拒绝填理由；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：同上完整流水线
- MCP：context7(Next16)；playwright
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task79-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：消费契约⑨（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task79-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
