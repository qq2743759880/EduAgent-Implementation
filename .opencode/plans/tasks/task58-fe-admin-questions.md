# task58: /admin/questions 管理端题库（两级 + 批量导入）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：L
> **前置**：task41, task13 ｜**后置（联调节点）**：消费契约④；task59 依赖
> **规范状态**：doc-frontend §二 P15（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P15（Uploader/ImportPreviewDialog/标签废除改全文检索）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P15 |
| 原型 | fe-implementer | admin-questions.html |
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
- Tabs（题库/题目）；题库 DataTable（bank_code 唯一校验提示）；「+ 新建题库」
- 题目列表（选中题库后：题号/题型/题干截断/客观题标记/状态/编辑/解析）
- 批量导入 Dialog：Uploader 拖拽 .xlsx/.csv → 校验 → 预览 N 行 → 导入进度轮询 → 结果报告（失败行明细）
- 删除题库 ConfirmDialog（题量确认）；知识点全文检索替代 tag 筛选

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 批量导入 1752 题，Then 预览→确认→进度→结果报告全链路可用，失败行可定位；删除题库二次确认
- Given 两级导航，When 选题库切题目 Tab，Then GET /api/admin/questions?bank_id= 联动；「编辑/解析」跳 task59（J24）
- Given 检索，When 输入知识点关键词，Then stem+analysis_text 全文检索（无标签筛选控件残留）

## 6. 交接与记忆
- 完成 → 看板 task58=DONE → sync.ps1
- 交付物：admin-questions.html + React + 测试
