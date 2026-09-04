# task38: 文档交付（接口文档/数据字典/运维手册/回滚手册）

> **类型**：ops ｜**执行工具**：Trae ｜**阶段**：P9 ｜**并行组**：W8 ｜**工作量**：M
> **前置**：全部前置任务 ｜**后置（联调节点）**：CP9 检查点

## 1. 选型依据
- edu-data-refactor-plan.md §8（交付物清单：接口文档/数据字典）
- tech-source-audit.md 全文（选型审计并入文档）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 四份文档 |
| 制图 | mermaid skill + summarize skill | 架构图/ER 图/时序图 |
| 审查 | review-screener-3 | 手册可操作性审查 |
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
- 接口文档：OpenAPI 全端点 + 错误码分段表（4xx2x/4xx3x/4xx4x）
- 数据字典：66 表字段说明 + 状态机枚举 8 组（订单/支付/退款/券/报名/课次/转码/工单）
- 运维手册：备份/回滚/分夜跑批/Redis 大 key 巡检/熔断指标看板
- 回滚手册：P0 恢复步骤 + degraded_reason 全清单

## 5. 验收标准（Given/When/Then 全文）
- Given 四份文档交付，When 由未参与开发的运维人员按手册演练（回滚+重启+降级排查），Then 可独立完成操作
- Given 错误码清单，When 前端对照，Then 每个业务错误码有文案映射（与 StatusBadge 映射表一致）
- Given 数据字典，When 对照 edu.sql，Then 66 表字段/枚举零偏差

## 6. 交接与记忆
- 完成 → 看板 task38=DONE → sync.ps1
- 交付物：四份文档 + degraded_reason 清单
