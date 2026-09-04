# task45: /courses/search 课程搜索

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task11 ｜**后置（联调节点）**：消费契约②（task11 /api/series keyword 参数）；可与 task44 并行
> **规范状态**：doc-frontend §二 P7 附（搜索态；复用 P7 规范 + 搜索参数节）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P7（搜索防抖 400ms）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 搜索页规范（对齐 P7） |
| 原型 | fe-implementer | course-search.html |
| 审核 | 【用户 gate】 | 循环至 APPROVED |
| 实现 | fe-implementer + fe-styler | React（复用 task44 CourseCard） |
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
- 关键词 + 筛选参数（学科/交付/价格）联动 GET /api/series?keyword=&…
- 结果 Grid 复用 CourseCard；空态「未找到相关课程」+ 建议词；分页

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 搜索关键词输入，Then 防抖 400ms 后带 keyword 重查；筛选参数与关键词叠加生效（queryKey 全参数）
- Given 空结果，When 渲染，Then EmptyState「未找到相关课程」+ 清除筛选 CTA
- Given 点击结果卡片，When 跳转，Then 至 /courses/[seriesId]（J1）

## 6. 交接与记忆
- 完成 → 看板 task45=DONE → sync.ps1
- 交付物：course-search.html + React + 测试
