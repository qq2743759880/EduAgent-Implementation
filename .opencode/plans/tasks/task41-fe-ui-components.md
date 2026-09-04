# task41: UI 组件基础 C1~C14 + 全局枚举映射表（StatusBadge）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P5 ｜**并行组**：W7 ｜**工作量**：L
> **前置**：task40 ｜**后置（联调节点）**：全部 27 页面任务依赖

## 1. 选型依据
- tech-source-audit.md §六（indigo #4F46E5 主色 + 单主色红线 + 状态色 emerald/amber/rose；tokens 单源 `.claude/specs/frontend/tokens/design-tokens.json`）
- doc-frontend-design-spec.md §三（C1~C14 契约 + 全局映射表 11 组枚举）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 逐组件契约（对齐 doc-frontend §3.2 Props 初版） |
| 实现 | fe-implementer + fe-styler | C1~C14（shadcn 风格 cva+useRender+cn） |
| 选型 | pick-ui-library skill + frontend-design skill | 组件选型（Base UI 系） |
| 测试 | fe-tester | Vitest + a11y 快照 |
| 工具 | context7 MCP | Next.js 16 / Tailwind v4 文档 |
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
- C1 DataTable（排序/骨架/空态内建）、C2 Pagination、C3 StatusBadge（11 组枚举映射：订单/支付/退款/券/报名/课次/转码/审核/工单/优先级/系列/交付）、C4 Stepper、C5 Uploader、C6 Timeline、C7 EmptyState、C8 ErrorState（不吞错）、C9 FilterBar、C10 ConfirmDialog、C11 DropdownMenu、C12 Select、C13 Accordion、C14 PriceText
- 每组件 vitest（render+交互+a11y 快照）；徽章颜色+文字双通道

## 5. 验收标准（Given/When/Then 全文）
- Given C1~C14 全部实现，When 运行 vitest 套件，Then 全绿且每组件含 a11y 断言（role/aria）；StatusBadge 徽章必须 颜色+文字 双通道（无纯色块）
- Given 组件使用 tokens，When grep 全站，Then 无 `bg-[#...]`、`text-[13px]`、sky/violet/cyan/teal/fuchsia 业务组件色（图表色板例外白名单）、无内联 style 色值

## 6. 交接与记忆
- 完成 → 看板 task41=DONE → sync.ps1
- 交付物：C1~C14 + 映射表 + 单测 + grep 审计报告
