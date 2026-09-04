# task78 — 管理端补全任务

> 执行工具：**TraeWork** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：消费契约⑧
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：frontend｜**依赖**：task41, task71｜**并行组**：W7｜**工作量**：L｜**执行工具**：TraeWork
- **交付物**：订单列表（状态 Tab+筛选+分页）+ 详情抽屉（items+支付流水+退款入口）+ 代取消（ConfirmDialog）+ 备注
- **验收标准**：
  - Given 订单列表，When 切换状态 Tab/筛选，Then 重查分页；详情展示支付流水；代取消 pending 单成功并 toast；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：fe-spec-writer → fe-implementer(HTML)→审核gate → fe-architect → fe-implementer(React) → fe-styler → fe-perf/a11y/visual → fe-tester
- MCP：context7(Next16)；playwright
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task78-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：消费契约⑧（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task78-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
