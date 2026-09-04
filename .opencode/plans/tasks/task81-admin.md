# task81 — 管理端补全任务

> 执行工具：**TraeWork** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：消费契约⑩
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：frontend｜**依赖**：task41, task73｜**并行组**：W7｜**工作量**：XL｜**执行工具**：TraeWork
- **交付物**：学员画像（课次进度/出勤/作业/成绩统计卡）+ 作答明细（每题题干/答案/判分/解析，analysis_text 展示）
- **验收标准**：
  - Given 学员详情，When 请求，Then 画像统计真实聚合；作答明细按题展示解析；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

## 2. agent / mcp / tool / skill 调度链

- agent 链：同上完整流水线(作答解析 Markdown 渲染)
- MCP：context7(Next16)；playwright
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task81-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：消费契约⑩（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task81-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
