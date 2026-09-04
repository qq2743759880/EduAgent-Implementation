# task43: /dashboard 学习仪表盘（15 处 MOCK 删除）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：L
> **前置**：task41, task14, task15, task23 ｜**后置（联调节点）**：消费契约⑤（task14 /me 聚合）+⑭（task23 缓存性能验收）
> **规范状态**：doc-frontend §二 P19（已有规范，适配重构）

## 1. 选型依据
- tech-source-audit.md §五（echarts：雷达图/趋势图能力）；§六（图表 8 色板：chart-palette.ts 改造）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 doc-frontend P19 规范 |
| 原型 | fe-implementer | dashboard.html（含 echarts 图表态） |
| 审核 | 【用户 gate】 | 循环至 APPROVED |
| 实现 | fe-implementer + fe-styler | React + echarts 色板注入 |
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
- 指标卡 4（学习时长/课次/积分/连续打卡）+ 学习时长 7 日折线 + 学科掌握度柱状 + 学习结构饼图 + 雷达 + 徽章墙 + 排行榜 Top5
- **删除 15 处 MOCK + 5 处 TODO**，数据源：/api/progress/dashboard + /api/gamification/me/badges + /me/points + /rankings
- chart-palette.ts 改造（§1.7 八色：indigo/emerald/amber/rose/sky(图表允许)/violet/slate/indigo-300）

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When React 实现，Then grep 零 MOCK（15 处清零）、数据全部来自真实 API；echarts 多系列按 §1.7 色板取色（饼图禁相邻色）
- Given 页面加载，When 请求聚合接口，Then 指标与 /me/learning-summary 一致（task14 契约）；排行来自 ZSET（task15）
- Given 缓存命中场景（task23），When 100 并发打开，Then P95 ≤800ms（性能验收）

## 6. 交接与记忆
- 完成 → 看板 task43=DONE → sync.ps1
- 交付物：dashboard.html + React 页面 + 测试 + MOCK 清零报告
