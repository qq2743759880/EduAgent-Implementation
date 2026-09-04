# task18: trade/payment 域新建（8 端点 + mock 回调 + 报名联动）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P4 ｜**并行组**：W2 ｜**工作量**：XL
> **前置**：task17 ｜**后置（联调节点）**：**契约冻结⑨ → 前端 task65（支付页）**；task19/20 依赖

## 1. 选型依据
- tech-source-audit.md §四（支付回调幂等：payment_no 唯一 + WHERE payment_status='pending' 条件更新；支付行业标准）
- edu-data-refactor-plan.md FR-API-04（8 端点 + mock 回调，不真实对接渠道）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev + be-security + be-architect | 支付创建/回调/对账 |
| 测试 | sd-tester + sd-challenger | 100 并发同 payment_no 回调攻防 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 加固 | harden skill | 资金安全红线 |
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
- 8 端点：POST /api/payments、GET /api/payments/{payment_no}、POST /payment-notifications/mock + 回调处理 + 查询/取消/重试/对账
- 渠道枚举：wechat_pay/alipay/bank_card/offline_transfer/public_account/campus_cashier；线下转账"到账审核中"
- 回调成功单事务：payment paid + order paid + student_cohort_rel active + 券 used（报名联动，薄弱点 W2 攻防场景）

## 5. 验收标准（Given/When/Then 全文）
- Given 同一 payment_no 的 mock 回调 100 并发重试，When 全部到达，Then 仅一次生效（其余命中条件更新 0 行或唯一键幂等），order 只 paid 一次、报名只 active 一次、券只核销一次
- Given 支付成功，When 查询订单与班次，Then order=paid、enroll_status=active、payment_status=paid 三者原子一致（单事务落库）
- Given 线下转账渠道，When 用户选择，Then 状态停留 pending + 前端提示"到账审核中"，无即时回调；mock 回调仅限模拟渠道
- Given 对账任务运行，When 比对 payment_record 与订单，Then 无重复入账记录（对账报告）

## 6. 交接与记忆（契约冻结⑨）
- 完成 → 写 `handoffs/task18-contract.md`：8 端点 + 渠道枚举 + 轮询语义（2s ≤15s）+ mock 回调用法
- 看板 task18=READY_FOR_FRONTEND（解锁 TraeWork task65）→ sync.ps1
- 交付物：domains/trade/payment + pytest（并发回调）+ 交接单
