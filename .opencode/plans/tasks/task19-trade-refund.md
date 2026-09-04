# task19: trade/refund 域新建（退款申请/撤销 + HITL 预留）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P4 ｜**并行组**：W2 ｜**工作量**：M
> **前置**：task18 ｜**后置（联调节点）**：**契约冻结⑩ → 前端 task66（/refunds）**；task28（HITL）依赖

## 1. 选型依据
- tech-source-audit.md §四（refund_no 唯一键幂等；金额校验服务端强制）
- tech-source-audit.md §二（HITL 挂载点预留：LangGraph interrupt 由 task28 接续）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 退款申请/撤销/列表 |
| 测试 | sd-tester + RunCommand+mysql CLI | 金额校验/状态机 |
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
- POST /api/refunds（订单/班次选择 + refund_type 四枚举 + 金额 ≤ 已付校验）、GET /api/refunds（倒序）、POST /api/refunds/{id}/cancel（仅 pending）
- refund_status：pending→approved/rejected→refunded；approver remark 字段
- HITL 挂载点预留（审批接口 stub，task28 替换为 LangGraph interrupt）

## 5. 验收标准（Given/When/Then 全文）
- Given 用户申请退款金额 > 实付金额，When POST /api/refunds，Then 拒绝并返回业务错误码（金额校验服务端强制执行）
- Given pending 退款单，When 撤销，Then 状态不再 pending 且不可再次撤销；approved/rejected 由管理端审批动作驱动（HITL 未上线前用管理端点过渡）
- Given 退款被拒绝，Then 返回 approver remark 供前端展示拒绝理由
- Given refund_type 枚举，When 提交，Then personal_reason/course_unsatisfied/schedule_conflict/duplicate_purchase 校验通过

## 6. 交接与记忆（契约冻结⑩）
- 完成 → 写 `handoffs/task19-contract.md`：3 端点 + refund_status/refund_type 枚举
- 看板 task19=READY_FOR_FRONTEND（解锁 TraeWork task66）→ sync.ps1
- 交付物：domains/trade/refund + pytest + 交接单
