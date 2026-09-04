# task42: /login + /register 认证页（含 / 根路由重定向附项）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task15 ｜**后置（联调节点）**：消费契约⑬（task15 存量壳适配）；E2E task69 前置
> **规范状态**：⚠️ doc-frontend-design-spec.md 未覆盖本页 → fe-spec-writer 先行补充该页规范再出 HTML

## 1. 选型依据
- tech-source-audit.md §五（Next.js App Router 路由组）
- tech-source-audit.md §六（HTML 原型审核流；indigo 主色/断点矩阵）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | **先行补充本页规范**（布局草图/组件/交互/状态机/数据依赖，格式对齐 doc-frontend §二） |
| 原型 | fe-implementer | 产出 test-reports/fe-html/login-register.html |
| 审核 | 【用户 gate】 | 用户讲解修改点/给设计图 → 返工循环至签收 APPROVED |
| 实现 | fe-architect（简单页可省）→ fe-implementer + fe-styler | React 实现（tokens 语义 class） |
| 审查 | fe-server-infra → fe-perf/fe-a11y-auditor/fe-visual-auditor 并行 | 修正 ≤3 轮 |
| 测试 | fe-tester | Vitest + Playwright |
| 工具 | playwright MCP + context7 MCP | 截图/文档 |
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
- /login：表单（账号/密码）、错误态 ErrorState + toast、登录成功 redirect 回跳（/login?redirect= 原路）
- /register：注册表单（account 唯一校验冲突提示 409）、注册成功跳登录
- 附项（/ 根路由）：登录态 → redirect /dashboard；未登录 → redirect /login
- 响应壳错误码消费：AUTH_EXPIRED 等字符串码 toast 展示

## 5. 验收标准（Given/When/Then 全文）
- Given fe-spec-writer 补充本页规范，When 产出 HTML，Then 规范含布局草图+组件清单+交互+状态机+数据依赖（格式对齐 doc-frontend §二）
- Given HTML 提交审核，When 用户给出修改点/设计图，Then 按图返工至 AUDIT LOG=APPROVED 且用户签收
- Given 未登录访问受保护页，When 触发跳转，Then 至 /login?redirect={原路}；登录成功回跳原路（J25）
- Given 注册重复 account，When 提交，Then 409 错误 toast 展示（后端 message）
- Given 根路由访问，When 登录态不同，Then 已登录→/dashboard、未登录→/login

## 6. 交接与记忆
- 完成 → 看板 task42=DONE → sync.ps1
- 交付物：补写规范 + login-register.html（APPROVED）+ React 页面 + 测试
