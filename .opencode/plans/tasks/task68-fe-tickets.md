# task68: /tickets 售后工单 + 人工申诉

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task22 ｜**后置（联调节点）**：消费契约⑫（task22 tickets）
> **规范状态**：doc-frontend §二 P5（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P5（TicketCard/Timeline/appeal 类型）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P5 |
| 原型 | fe-implementer | tickets.html |
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
- Tabs（全部/处理中/已关闭，含申诉类型）；TicketCard（单号/类型/优先级徽章/班次/最后跟进）
- 展开 → Timeline（GET follows）；「+ 新建工单」Dialog（类型：售后/投诉/退款/**appeal 人工申诉** + 班次选择 + 标题/内容）
- 「回复工单」POST follows（reply_user）；关闭工单评满意度 1-5 星 + 评语

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 新建工单选类型=appeal，Then 文案「人工申诉」正确展示与提交；first_response_at 空显示「等待受理」
- Given 展开工单，When 加载跟进，Then Timeline 渲染正确；用户仅可见自己的工单（后端隔离联动验证）
- Given 优先级/状态枚举，When 渲染，Then urgent→destructive 紧急/high→warning 高/medium·low→muted；pending→warning 待受理/in_progress→primary 处理中/closed→muted 已关闭

## 6. 交接与记忆
- 完成 → 看板 task68=DONE → sync.ps1
- 交付物：tickets.html + React + 测试
