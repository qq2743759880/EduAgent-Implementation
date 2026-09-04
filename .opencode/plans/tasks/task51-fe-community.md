# task51: /community 社区列表

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task15 ｜**后置（联调节点）**：消费契约⑬（task15 壳适配）；task52 依赖
> **规范状态**：⚠️ doc-frontend-design-spec.md 未覆盖本页 → fe-spec-writer 先行补充该页规范再出 HTML

## 1. 选型依据
- tech-source-audit.md §五（存量 community 模块壳适配）；§六（列表页断点矩阵）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | **先行补充本页规范** |
| 原型 | fe-implementer | community.html |
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
- 帖子列表（标题/摘要/作者/时间/评论数/点赞数）、筛选/分页、发布入口
- community_post 数据；响应壳解包（task40 客户端改造后）

## 5. 验收标准（Given/When/Then 全文）
- Given fe-spec-writer 补充本页规范，When 产出 HTML，Then 规范含列表/筛选/空态设计
- Given HTML APPROVED，When 加载列表，Then 数据来自 /api/community（壳解包正常）、分页可用、空态「暂无帖子」
- Given 点击帖子，When 跳转，Then 至 /community/[postId]（J 表内联动）

## 6. 交接与记忆
- 完成 → 看板 task51=DONE → sync.ps1
- 交付物：补写规范 + community.html + React + 测试
