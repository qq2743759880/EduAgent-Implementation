# task83 — 管理端补全任务

> 执行工具：**TraeWork** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：消费契约⑪
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：frontend｜**依赖**：task41, task75｜**并行组**：W7｜**工作量**：L｜**执行工具**：TraeWork
- **交付物**：工单列表（类型含 appeal/优先级/状态）+ 详情时间线（多轮回复）+ 回复框+分配+关闭+满意度统计卡
- **验收标准**：
  - Given 工单详情，When 客服回复，Then 时间线追加+状态更新；申诉类型专属流程；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：同上完整流水线(时间线组件)
- MCP：context7(Next16)；playwright
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task83-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：消费契约⑪（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task83-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
