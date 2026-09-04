# task69: E2E 回归（Playwright 全链路 + 状态机 + 视觉验收）

> **类型**：test ｜**执行工具**：TraeWork ｜**阶段**：P9 ｜**并行组**：W8 ｜**工作量**：XL
> **前置**：task42~68（全部页面）+ 后端全部上线 ｜**后置（联调节点）**：task39（压测）依赖；CP9 依据

## 1. 选型依据
- tech-source-audit.md §六（断点截图矩阵 375/768/1024/1280/1440；视觉验收标准）
- collaboration-protocol.md §四（E2E 为最终裁决依据）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 测试 | fe-tester + sd-tester | Playwright 套件编写与执行 |
| 技能 | frontend-browser-testing skill + frontend-visual-validation skill | 测试策略/视觉验收闭环 |
| 工具 | playwright MCP | 全链路驱动 |
| 审查 | review-screener-3 | 用例覆盖审查 |
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
- 主业务链路：课程浏览→详情→班次→领券→下单→支付 mock→报名→学习→作业/考试→工单
- 25 条跳转（J1~J25 全量断言）+ 8 组状态机回归（订单/支付/退款/券/报名/课次/转码/工单）
- 全页面截图矩阵（27 页 × 5 viewport × 成功/空/错误三态）；RBAC 越权（student 访问管理端 403）；响应壳断言（全部 XHR 结构统一）
- 页面完成即补用例（早启动，不等到全部页面完成）

## 5. 验收标准（Given/When/Then 全文）
- Given 全套 E2E 运行，When 执行，Then 全链路通过；25 跳转全部可达；状态机非法迁移均被后端拒绝且前端提示正确
- Given 截图矩阵，When 视觉验收，Then 各 viewport 无溢出/遮挡/断行；200% 缩放（等效 1440→720）无水平溢出
- Given RBAC 用例，When student token 请求管理端端点，Then 403 + 统一错误壳
- Given 响应壳断言，When 遍历全部 XHR 响应，Then 100% 为 {code,message,data} 结构（SSE 例外）

## 6. 交接与记忆
- 完成 → 看板 task69=DONE → sync.ps1
- 交付物：E2E 套件 + 截图矩阵 + 回归报告（CP9 依据）
