# task62: /admin/mcp MCP 控制台

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task15, task33 ｜**后置（联调节点）**：消费契约⑬ + task33 联调（描述体检按钮）
> **规范状态**：⚠️ doc-frontend-design-spec.md 未覆盖本页 → fe-spec-writer 先行补充该页规范再出 HTML

## 1. 选型依据
- tech-source-audit.md §三（MCP 描述审查——前端消费体检按钮与审计展示）；§六

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | **先行补充本页规范**（server/tool 列表/体检/日志） |
| 原型 | fe-implementer | admin-mcp.html |
| 审核 | 【用户 gate】 | 循环至 APPROVED |
| 实现 | fe-implementer + fe-styler | React（AdminGuard） |
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
- MCP server 列表（注册状态/工具数）、tool 列表（description vs description_rewritten 对照展示）
- 「描述体检」按钮（触发 task33 review_and_rewrite）+ 审计结果展示
- 调用日志表（mcp_tool_call_log：错误率/schema 版本告警）

## 5. 验收标准（Given/When/Then 全文）
- Given fe-spec-writer 补充本页规范，When 产出 HTML，Then 规范含列表/体检/日志设计
- Given HTML APPROVED，When 点「描述体检」，Then 触发后端审查、重写结果回显（原描述 vs rewritten 对照）
- Given 调用日志，When 加载，Then 错误率/schema_version 告警可见（task33 指标）

## 6. 交接与记忆
- 完成 → 看板 task62=DONE → sync.ps1
- 交付物：补写规范 + admin-mcp.html + React + 测试
