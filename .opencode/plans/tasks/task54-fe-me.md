# task54: /me 个人中心（student-profile/learning-summary 新接口）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task14, task15 ｜**后置（联调节点）**：消费契约⑤（/me 新接口）
> **规范状态**：doc-frontend §二 P12（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P12（avatar 渐变/StatCard/NavListItem/档案表单）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P12 |
| 原型 | fe-implementer | me.html |
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
- 头像渐变 + 数据概览 4 StatCard（学习时长/完成课次/积分/等级，真实数据）
- NavListItem 功能入口 7 行（J20 跳转表：/orders /coupons /favorites /refunds /tickets /my-courses /practice/wrong-book）
- 学员档案表单（GET /api/users/me/student-profile + PUT /api/users/me/profile；identity/goal/education/grade/school/industry/position/years）

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 页面加载，Then GET /api/users/me + /me/student-profile + /api/progress/dashboard 真实数据（无 MOCK）
- Given 编辑档案，When 保存，Then PUT 成功 + toast；StatCard 数据与 /me/learning-summary 一致
- Given 入口行，When 点击，Then 跳转目标正确（7 个入口 J20 表全覆盖）

## 6. 交接与记忆
- 完成 → 看板 task54=DONE → sync.ps1
- 交付物：me.html + React + 测试
