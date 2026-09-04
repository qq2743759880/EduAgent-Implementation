# task15: 存量模块响应壳适配（auth/chat/community/gamification/mcp/rag_admin）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P3 ｜**并行组**：W2 ｜**工作量**：M
> **前置**：task10 ｜**后置（联调节点）**：**契约冻结⑬ → 前端 task42（login/register）、task50（chat）、task51/52（community）、task53（achievements）、task55（admin/dashboard）、task60（admin/users）、task62（admin/mcp）**

## 1. 选型依据
- tech-source-audit.md §一（响应壳统一；JWT 认证体系不动）
- tech-source-audit.md §四（gamification 排行榜 ZSET）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 逐点 return ok(...) 改造 + ZSET |
| 测试 | sd-tester | 契约测试 + 排行验证 |
| 审查 | review-screener-1 | — |
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
- auth/chat/community/gamification/mcp/rag_admin 逐点 ok() 改造
- gamification 排行榜 Redis ZSET（周榜快照 + 实时增量）
- chat SSE done/error 事件内嵌壳
- 本任务只适配壳不改业务逻辑（范围外红线）

## 5. 验收标准（Given/When/Then 全文）
- Given 契约测试运行，When 断言上述模块全部端点，Then 100% 统一壳；SSE 流 done 事件含 `{code:0,message:"ok",data}` 内嵌结构
- Given 排行榜查询，When 请求 /rankings，Then 数据来自 ZSET（写入侧同步更新），积分变更 1s 内可查
- Given auth 登录/注册/refresh，When 全流程，Then 响应壳统一但 JWT 语义不变（业务逻辑未改）

## 6. 交接与记忆（契约冻结⑬）
- 完成 → 写 `handoffs/task15-contract.md`：存量模块端点清单 + SSE 壳示例 + 排行结构
- 看板 task15=READY_FOR_FRONTEND（解锁 TraeWork task42/50/51/52/53/55/60/62）→ sync.ps1
- 交付物：6 模块壳适配 + 契约测试 + 交接单
