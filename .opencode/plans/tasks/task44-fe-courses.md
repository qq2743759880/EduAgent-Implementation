# task44: /courses 课程中心

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：L
> **前置**：task41, task11 ｜**后置（联调节点）**：消费契约②（task11 /api/series）；task46 依赖
> **规范状态**：doc-frontend §二 P7（已有规范）

## 1. 选型依据
- tech-source-audit.md §六（indigo 主色/断点 375~1440/HTML 审核流）
- doc-frontend-design-spec.md P7（FilterBar/CourseCard/Pagination 规范）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 doc-frontend P7 |
| 原型 | fe-implementer | courses.html |
| 审核 | 【用户 gate】 | 循环至 APPROVED |
| 实现 | fe-implementer + fe-styler | React（task46 复用 CourseCard） |
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
- FilterBar（学科/交付模式/价格区间 Select/排序）、SearchInput 防抖 400ms（use-debounced-value）、CourseCard（封面 16:9 rounded-3xl/系列名/元信息/价格 tabular-nums）、Pagination（page_meta）
- queryKey 含全部筛选参数；仅 sale_status=on_sale；空字段显示「-」

## 5. 验收标准（Given/When/Then 全文）
- Given HTML 产出，When 用户审核提出意见，Then 按意见修改至 AUDIT LOG=APPROVED 且用户签收（循环 §2.11.0）
- Given 页面就绪，When 切换任意筛选/排序/关键词，Then queryKey 变化即重查（含全部筛选参数）；仅展示 sale_status=on_sale；空字段显示「-」而非 fallback 假数据
- Given vitest + 截图矩阵，Then 375/768/1024/1280/1440 × 成功/空/错误三态通过、grep 无 MOCK fallback（fallbackPrice/fallbackRating 清零）

## 6. 交接与记忆
- 完成 → 看板 task44=DONE → sync.ps1
- 交付物：courses.html + React + 测试
