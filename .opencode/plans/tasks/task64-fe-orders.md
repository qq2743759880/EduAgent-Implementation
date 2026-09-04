# task64: /orders 我的订单

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task17 ｜**后置（联调节点）**：消费契约⑧（task17 order）；task65 依赖
> **规范状态**：doc-frontend §二 P2（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P2（OrderCard/状态机 6 态徽章映射）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P2 |
| 原型 | fe-implementer | orders.html |
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
- Tabs（全部/待付款/已支付/已完成/已退款 + 计数）；OrderCard（订单号/封面/班次名/实付 tabular-nums/状态徽章）
- 「去支付」→ /orders/[orderId]/pay（J6）；「详情」展开 order_items + 支付记录 + 退款入口（J9）；「申请退款」→ /refunds?order_item_id=
- 取消 ConfirmDialog（仅 pending）；Pagination；空态「暂无订单」+ 去选课

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 切换 tab，Then 按 order_status 重查；订单状态机徽章映射 6 态正确（pending→warning 待付款/paid→success 已支付/completed→muted 已完成/cancelled→muted 已取消/partial_refunded→warning 部分退款/refunded→destructive 已退款）
- Given pending 单，When 点取消，Then ConfirmDialog → POST cancel → 列表刷新

## 6. 交接与记忆
- 完成 → 看板 task64=DONE → sync.ps1
- 交付物：orders.html + React + 测试
