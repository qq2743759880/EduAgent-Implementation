# task01: 66 表 DDL 重建脚本（动作 A/D，按 edu.sql）

> **类型**：database ｜**执行工具**：Trae ｜**阶段**：P1 ｜**并行组**：W1 ｜**工作量**：XL
> **前置**：无（与 task00 并行）｜**后置（联调节点）**：task02/03/04/05

## 1. 选型依据
- tech-source-audit.md §一（asyncmy 原生 SQL + repository；`order`/`question` 保留字转义属本任务关键实现点）
- 数据权威：`E:\stu\project\stu\edu-data\sql\edu.sql`（66 表）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 解析 edu.sql → 重构 SQL（DROP+CREATE） |
| 建模 | mermaid skill | 66 表关系图（分组：dim/org/course/question/trade/learning） |
| 验证 | sd-tester + RunCommand+mysql CLI | 测试库执行 + 结构比对 |
| 审查 | review-screener-1 → review-moderator → review-judge | 唯一键/外键/注释一致性审查 |
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
- 动作 A：66 表 DROP+CREATE 按 edu.sql 原样（dim_*7 / org_*10 / staff/student_profile / series 系 8 / 题库系 5 / 交易系 9 / 报名/学习/售后/结算/风控等）
- 动作 D：27 张保留表清单（alembic_version/sys_user_auth/chat_*/community_*/gamification_*/quiz_*/vocab_*/mcp_*/user_profile 等，见 self-built-tables-audit.md）
- `order`/`question` 保留字：全部引用统一反引号，出转义规范文档
- 回滚脚本：恢复至 task00 备份状态
- 参照 self-built-tables-audit.md §四：不能直接全部删除重建，9 张旧表在 task02+task11~13 迁移

## 5. 验收标准（Given/When/Then 全文）
- Given edu.sql 已解析为重构 SQL，When 在测试库执行，Then 66 表列/类型/唯一键/外键/注释与 edu.sql 逐项 diff 为空（task05 脚本验证）
- Given 27 张平台扩展表存在，When 执行重构，Then 27 表结构与数据零影响
- Given 重建失败，When 执行回滚脚本，Then 恢复至 task00 备份状态
- Given `order`/`question` 保留字表，When 通过 asyncmy 参数化 SQL 读写，Then 转义一致无语法错误（单测覆盖）

## 6. 交接与记忆
- 完成 → 看板 task01=DONE → sync.ps1
- 交付物：`refactor_sql/` 目录 + 保留字转义规范 + 回滚脚本
