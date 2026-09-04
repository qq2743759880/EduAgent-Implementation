# task49: /practice/[mode] 复习中心（错题本出题源切 question 表）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task13, task14 ｜**后置（联调节点）**：消费契约④（question 出题源）+⑤（progress）
> **规范状态**：doc-frontend §二 P11（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P11（QuizPanel 出题源切换 + analysis_text 展示）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P11 |
| 原型 | fe-implementer | practice.html |
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
- 入口卡 3（错题本/单词本/专项练习）+ StatCard 待复习数
- 错题本 GET /api/interactive/quiz/wrong-book（改造后出题源 question）
- 复习会话：作答→即时判分→**展示 analysis_text 解析**（重构核心）；SM-2 词卡复用不动；专项练习按 dim_question_type 过滤

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 复习作答，Then 判分即时展示 + analysis_text 解析渲染（Markdown 预览与 task59 管理端一致）
- Given 错题本加载，When 请求，Then 数据来源 question 表（题干含解析字段），无旧 admin_question 引用
- Given 词卡回忆，When 进入单词本，Then SM-2 行为不变（范围外不动）

## 6. 交接与记忆
- 完成 → 看板 task49=DONE → sync.ps1
- 交付物：practice.html + React + 测试
