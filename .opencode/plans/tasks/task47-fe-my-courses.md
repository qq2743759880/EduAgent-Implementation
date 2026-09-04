# task47: /my-courses 我的班次（enrollments 语义）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：L
> **前置**：task41, task20, task21 ｜**后置（联调节点）**：消费契约⑪（task20/21 合并发布）；task48 学习页跳转来源
> **规范状态**：doc-frontend §二 P10（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P10（CohortCard enrollments 语义）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P10 |
| 原型 | fe-implementer | my-cohorts.html |
| 审核 | 【用户 gate】 | 循环至 APPROVED |
| 实现 | fe-implementer + fe-styler | React |
| 审查 | fe-server-infra → fe-perf/fe-a11y-auditor/fe-visual-auditor | ≤3 轮 |
| 测试 | fe-tester | Vitest + Playwright |
| 工具 | playwright MCP + context7 MCP | — |
| 提交 | commit skill | — |

## 3. 执行方式（Trae 手动调度，无 Workflow API）

Trae Code 无 opencode 专属的 `Workflow()` API，按 `D:\.ai-hub\workflows\dev-standard.mjs` 的 8 阶段**手动调度**（效果等价）：
```
1. 开发阶段   -> 调 sd-dev + be-architect + be-validator（读任务文档 + tech-source-audit）
2. 测试阶段   -> 调 sd-tester（+ sd-challenger 对抗）；数据库校验用 RunCommand 跑 mysql CLI / Python 脚本（无 mysql MCP）
3. 修正阶段   -> 据测试报告回 sd-dev 修复
4. 审查阶段   -> 调 review-screener-1/2/3 -> review-moderator -> review-judge（SARIF）
5. 提交阶段   -> git commit（message 含 task 编号）
```

mysql MCP 未在 Trae 环境注册（当前 MCP 仅 integrated_code_mode / integrated_goal）：
- 数据库校验改用 **RunCommand + mysql CLI / Python 脚本**（先例：scripts/verify_schema.py、scripts/verify_task07_counts.py）
- 或手动在 设置->MCP 按 `D:\.ai-hub\mcp\index.json` 模板添加 mysql


## 4. 实现规划要点
- Tabs（学习中/已完成/已退款，enroll_status ∈ {active,completed,cancelled,refunded} 驱动）
- CohortCard：进度条（模块 X/6 · 课次 Y/24 聚合）、下次课时间
- 「继续学习」→ 最近未完成课次 /learning/[seriesId]/[sessionId]（J14）；「课程详情」?cohort_id= 高亮（J15）；「售后」→ /tickets?order_item_id=（J16）
- 已退款态灰色 + 「查看退款」

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 页面加载，Then GET /api/enrollments/me/cohorts?status= 数据驱动三 tab；进度聚合为四级真实数据（无 MOCK）
- Given active 报名，When 点继续学习，Then 跳转最近未完成课次；空态「还没有报名班次」+ 去选课 CTA
- Given enroll_status 枚举，When 渲染，Then 徽章映射正确（active→success 学习中/completed→muted 已完成/refunded→destructive 已退款）

## 6. 交接与记忆
- 完成 → 看板 task47=DONE → sync.ps1
- 交付物：my-cohorts.html + React + 测试
