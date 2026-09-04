# task71 — 管理端补全任务

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：契约冻结⑧ 订单管理 → 解锁 task78
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：backend｜**依赖**：task17｜**并行组**：W2｜**工作量**：M｜**执行工具**：Trae
- **交付物**：app/domains/trade/order/admin.py：GET /api/admin/orders（status/时间/金额/分页）、GET /api/admin/orders/{id}（含 items+payments）、POST /api/admin/orders/{id}/cancel、POST /api/admin/orders/{id}/note
- **验收标准**：
  - Given admin 请求订单列表，When 按状态/时间过滤，Then 返回分页订单含学员/班次/金额/状态徽章数据；详情含支付流水；代取消仅限 pending 态
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev(+be-security) → sd-tester + sd-challenger(并行) → review-*
- MCP：RunCommand+mysql CLI；skill: harden
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task71-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：契约冻结⑧ 订单管理 → 解锁 task78（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task71-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
