# task22: tickets 域新建（4 端点 + appeal 人工申诉类型）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P4 ｜**并行组**：W2 ｜**工作量**：M
> **前置**：task17, task20 ｜**后置（联调节点）**：**契约冻结⑫ → 前端 task68（/tickets）**
> **契约裁定（2026-08-22 用户硬性规则④）**：**以 api-request §7 + 前端 tickets.ts 为权威**（前端 task40 已封装，幂等前缀 `/api/trade/after_sales/ticket`）。task22 文档原型路由（/api/tickets + follows/survey + 5 type）与权威冲突，**按权威落地**：4 端点 + ticket_type `{consult, appeal, refund, other}` + 满意度 `POST /satisfaction`。

## 1. 选型依据
- tech-source-audit.md §一（edu.sql service_ticket×3；consultation 域不建接口——咨询改人工申诉）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 工单 CRUD + 跟进 + 满意度 |
| 测试 | sd-tester + RunCommand+mysql CLI | user 隔离测试 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
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
- **4 端点（对齐 api-request §7 + 前端 tickets.ts）**：
  - POST `/api/trade/after_sales/ticket`（创建，类型含 appeal 人工申诉）
  - GET `/api/trade/after_sales/tickets`（我的工单，status/type 过滤 + 分页）
  - GET `/api/trade/after_sales/ticket/{ticket_id}`（详情）
  - POST `/api/trade/after_sales/ticket/{ticket_id}/satisfaction`（满意度评价）
- ticket_no 唯一键；**user_id 隔离**（用户 A 不可见用户 B 工单）；first_response_at 语义
- **ticket_type ∈ {consult, appeal, refund, other}**（对齐前端 TicketType，非文档原型 5 type）
- 满意度：satisfaction_score（1-5 星）+ satisfaction_comment，不可重复评分
- 注：follows（跟进 Timeline）不在权威 4 端点内——若前端 task68 需要，走 api-request 上浮（不默认实现）

## 5. 验收标准（Given/When/Then 全文）
- Given 用户创建 ticket_type=appeal 工单，Then 落库成功且前端文案映射"人工申诉"；first_response_at 为空（等待受理态）
- Given 用户 A 请求用户 B 的工单详情，Then 404（隔离）；管理员可见全部
- Given 关闭工单后评满意度（POST /satisfaction），Then score 落库且不可重复评分
- Given 工单列表，When 按 status/type 过滤 + 分页，Then 返回 TicketPage（对齐前端类型）

## 6. 交接与记忆（契约冻结⑫）
- 完成 → 写 `handoffs/task22-contract.md`：5 端点 + ticket_type/ticket_status/priority 枚举
- 看板 task22=READY_FOR_FRONTEND（解锁 TraeWork task68）→ sync.ps1
- 交付物：domains/after_sales + pytest + 交接单
