# task28: AI 助手：HITL 退款审批（LangGraph interrupt + 超时升级工单）

> **类型**：agent+backend ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W3 ｜**工作量**：L
> **前置**：task19, task24 ｜**后置（联调节点）**：task29（评估，可选）

## 1. 选型依据
- tech-source-audit.md §二（HITL 用 LangGraph interrupt/Command(resume)，官方原生能力；context7 已验证 API）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev + be-architect | 审批图 + resume 落库 |
| 测试 | sd-tester | interrupt 持久化/重启恢复测试 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 工具 | context7 MCP | LangGraph HumanInterrupt 文档 |
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
- 退款审批图：interrupt() 挂起 → 管理端审批（approved/rejected + remark）→ Command(resume=...) 执行退款落库
- resume 内原子：refund=refunded + order=refunded + student_cohort_rel=refunded（薄弱点 W2 关闭）
- 72h 超时任务：自动创建 service_ticket priority=high
- 替换 task19 的审批 stub

## 5. 验收标准（Given/When/Then 全文）
- Given 退款申请进入审批，When 图在审批节点 interrupt 挂起，Then 状态持久化（Redis checkpoint），进程重启后仍可 resume
- Given 审批通过，When resume，Then 退款落库 + order=refunded + student_cohort_rel=refunded 原子完成
- Given 审批 72h 无动作，When 超时任务运行，Then 自动创建 priority=high 工单并通知

## 6. 交接与记忆
- 完成 → 看板 task28=DONE → sync.ps1
- 交付物：审批图 + 管理端审批端点 + 超时任务 + pytest
