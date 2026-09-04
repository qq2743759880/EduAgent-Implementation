# task65: /orders/[orderId]/pay 支付页

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：L
> **前置**：task64, task18 ｜**后置（联调节点）**：消费契约⑧+⑨（order + payment）
> **规范状态**：doc-frontend §二 P3（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P3（Stepper/RadioGroup 渠道/轮询 ≤15s/防双击/5s 倒计时）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P3 |
| 原型 | fe-implementer + prototype skill | order-pay.html（三结果态演示） |
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
- Stepper（确认订单→支付→完成）；订单摘要（PriceText + 券抵扣明细）
- 支付方式 RadioGroup（默认模拟支付；线下转账「到账审核中」提示）；「立即支付」POST /api/payments → 轮询 GET /api/payments/{payment_no}（2s refetchInterval ≤15s 或终态停）
- 成功 → 5s 倒计时跳 /orders（J7）+「报名成功，前往学习」→ /my-courses（J8）；失败 Alert + 重试（保留原单）；防双击（loading+disabled）；「取消订单」ConfirmDialog

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 进入页面，Then GET /api/orders/{id} 校验状态：非 pending 提示并跳订单列表；金额展示与订单一致
- Given 点立即支付，When 轮询期间，Then payment_status pending→paid/failed 状态切换正确；按钮 loading 防双击（无重复支付记录）
- Given 模拟支付回调完成，Then 支付成功页 5s 倒计时 + 报名联动 CTA 可用；payment_status 徽章 6 态映射正确

## 6. 交接与记忆
- 完成 → 看板 task65=DONE → sync.ps1
- 交付物：order-pay.html + React + 测试
