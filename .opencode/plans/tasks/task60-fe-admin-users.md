# task60: /admin/users 管理端用户

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task14, task15 ｜**后置（联调节点）**：消费契约⑤+⑬
> **规范状态**：doc-frontend §二 P17（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P17（学习详情 6 指标/最后 admin 保护红线）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P17 |
| 原型 | fe-implementer | admin-users.html |
| 审核 | 【用户 gate】 | 循环至 APPROVED |
| 实现 | fe-implementer + fe-styler | React（AdminGuard） |
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
- DataTable（昵称/手机/账号搜索防抖 400ms + 角色/状态筛选）
- 「查看」学习详情 Dialog：6 StatCard（报名班次/进度/最近学习/作业正确率/考试/收藏）+ 最近动态
- 「编辑」角色切换（student/teacher/manager/admin）+ 状态切换；**最后 1 个可用 admin 禁用操作**（前端禁用+提示+后端兜底）

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 搜索/筛选，Then 防抖 400ms + 组合查询生效；分页可用
- Given 学习详情，When 打开 Dialog，Then GET /api/admin/users/{id}/learning 聚合 6 指标真实数据
- Given 最后 admin 操作，When 尝试禁用/降级，Then 前端禁用 + 后端拒绝 + 提示

## 6. 交接与记忆
- 完成 → 看板 task60=DONE → sync.ps1
- 交付物：admin-users.html + React + 测试
