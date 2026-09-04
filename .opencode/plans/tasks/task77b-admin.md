# task77b — 管理端补全任务

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：契约冻结⑫ 报表 → 解锁 task86
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：backend｜**依赖**：task71, task73｜**并行组**：W2｜**工作量**：M｜**执行工具**：Trae
- **交付物**：GET /api/admin/reports/revenue（营收趋势/渠道/课程维度）、GET /api/admin/reports/funnel（曝光→咨询→领券→下单→支付→报名 漏斗）、GET /api/admin/reports/attendance（出勤率/完课率）
- **验收标准**：
  - Given 报表接口，When 请求，Then 返回按日/周/月聚合数据（Redis 缓存 60s）；漏斗各环节计数与 C 端真实事件一致
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev → sd-tester → review-*
- MCP：Redis 缓存 60s；skill: summarize
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task77b-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：契约冻结⑫ 报表 → 解锁 task86（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task77b-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
