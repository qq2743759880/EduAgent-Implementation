# task59: /admin/questions/[id] 管理端题目（解析编辑）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task58, task13 ｜**后置（联调节点）**：消费契约④
> **规范状态**：doc-frontend §二 P16（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P16（analysis_text 必修 + MarkdownPreview + 题型联动）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P16 |
| 原型 | fe-implementer | admin-question-detail.html |
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
- 题目编辑表单：题库/题号只读、题型 Select（dim_question_type）、题干 Textarea（Markdown）、选项编辑器按题型联动（RadioGroup/Checkbox 等 options_json schema）、答案、**analysis_text 必填 + MarkdownPreview**、objective_flag、保存/保存并继续/返回列表、预览 tab 与用户端 QuizPanel 一致

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 编辑解析并保存，Then PATCH /api/admin/questions/{id} 持久化；analysis_text 为空时前端拦截提示 + 后端兜底校验
- Given 题型切换，When 改变题型，Then 选项控件联动且已填数据不丢；预览渲染题干+解析与用户端一致

## 6. 交接与记忆
- 完成 → 看板 task59=DONE → sync.ps1
- 交付物：admin-question-detail.html + React + 测试
