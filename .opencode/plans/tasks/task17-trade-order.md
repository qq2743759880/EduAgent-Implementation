# task17: trade/order 域新建（5 端点 + 状态机 + 三层幂等纵深）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P4 ｜**并行组**：W2 ｜**工作量**：L
> **前置**：task16 ｜**后置（联调节点）**：**契约冻结⑧ → 前端 task64（/orders）**；task18/22 依赖

## 1. 选型依据
- tech-source-audit.md §一（edu.sql `order`/order_item；保留字转义规范 task01 产物）
- tech-source-audit.md §四（幂等三层纵深：中间件 + order_no 唯一键 + 状态机条件更新；金额服务端重算）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev + be-security + be-architect | 下单/取消/状态机 |
| 测试 | sd-tester + sd-challenger | 100 并发同 order_no 攻防 + 篡改价格 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 加固 | harden skill | 资金安全红线审查 |
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
- 5 端点：POST /api/orders（cohort_id + coupon_receive_record_id）、GET /api/orders（状态过滤分页）、GET /api/orders/{id}（items+payments 嵌套）、POST /api/orders/{id}/cancel（仅 pending）、GET /api/orders?refundable=true
- 状态机：pending→paid→completed / cancelled / partial_refunded→refunded
- 下单单事务 order+order_item；金额 DECIMAL(12,2) 服务端重算；order_no（institution_id,order_no）唯一键

## 5. 验收标准（Given/When/Then 全文）
- Given 用户选班次+券下单，When POST /api/orders，Then 单事务创建 order+order_item、券核销为 used、金额为服务端计算值（篡改请求价格无效）、返回 order_no
- Given 并发 100 请求同 order_no 下单，Then 仅 1 条记录（唯一键冲突回查返回原单，语义幂等）；非法状态迁移（paid 单取消）返回 40920
- Given 下单成功后取消，When POST cancel，Then order_status=pending→cancelled 且券回滚为 unused、班次余位释放
- Given 下单事务失败，When 任一子语句报错，Then 整体回滚（事务边界 1s 内，无 LLM/Redis 调用）

## 6. 交接与记忆（契约冻结⑧）
- 完成 → 写 `handoffs/task17-contract.md`：5 端点 + 状态机枚举 + 幂等说明
- 看板 task17=READY_FOR_FRONTEND（解锁 TraeWork task64）→ sync.ps1
- 交付物：domains/trade/order + pytest（含并发）+ 交接单
