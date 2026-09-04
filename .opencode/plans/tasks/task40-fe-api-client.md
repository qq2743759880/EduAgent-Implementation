# task40: 前端接口层：api-client 解包 + 8 新客户端 + 10 改造

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P5 ｜**并行组**：W7 ｜**工作量**：L
> **前置**：task10 ｜**后置（联调节点）**：task41（组件）；全部页面任务消费

## 1. 选型依据
- tech-source-audit.md §五（Next.js 16.3 + React 19 + Tailwind v4 + shadcn 存量；axios+React Query 不动）
- tech-source-audit.md §一（响应壳 {code,message,data} 消费侧解包）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 客户端契约（对齐 handoffs/task10-contract.md + schemas.py） |
| 实现 | fe-implementer | 解包 + 18 个客户端 |
| 测试 | fe-tester | tsc + vitest |
| 工具 | context7 MCP | Next.js 16 文档（AGENTS.md 要求先读 node_modules/next/dist/docs） |
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
- api-client.ts 拦截器：code===0 → 返回 data；非 0 → reject ApiError(message)；code 放宽 string|number
- 新建 8：enrollments.ts、study.ts、coupons.ts、favorites.ts、orders.ts、payments.ts、tickets.ts、admin/rag.ts 增 uploadKnowledgeFiles/listKnowledgeTasks/getKnowledgeTaskStatus/listKnowledgePartitions/deleteKnowledgePartition
- 改造 10：curriculum.ts、learning.ts、admin/courses.ts、admin/questions.ts、dashboard.ts、admin/users.ts、chat.ts、community.ts、mcp.ts、rag.ts（snake_case 类型定义）
- 开工前读 handoffs/task10-contract.md；类型与后端 schemas.py 一一对应；跑 contract-diff.py

## 5. 验收标准（Given/When/Then 全文）
- Given 后端返回 `{code:0,message:"ok",data:{...}}`，When 调用任意客户端方法，Then 直接拿到 data 对象（调用方无 .data 解包代码）；非 0 时 reject ApiError 且 message 可 toast 展示
- Given 后端错误码为字符串（如 "AUTH_EXPIRED"），When 拦截器处理，Then code 类型 string|number 兼容、旧数字码调用点不破坏
- Given 全量客户端就绪，When 运行 tsc + vitest + contract-diff.py，Then 零类型错误、单测全绿、契约字段集零差异；grep 确认无别名兜底（series_title/seriesName 三轨清零）与 MOCK fallback 残留

## 6. 交接与记忆
- 完成 → 看板 task40=DONE → sync.ps1（TraeWork 分区记忆：trae-global-memory.md）
- 交付物：api-client.ts 改造 + 8 新/10 改造客户端 + 单测 + 契约 diff 报告
