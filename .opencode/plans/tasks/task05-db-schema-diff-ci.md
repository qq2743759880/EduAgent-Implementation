# task05: 库表结构 diff 校验脚本 + CI 集成

> **类型**：test ｜**执行工具**：Trae ｜**阶段**：P1 ｜**并行组**：W1 ｜**工作量**：M
> **前置**：task01~03 ｜**后置（联调节点）**：CI 常驻卡口（CP1 检查点依据）

## 1. 选型依据
- tech-source-audit.md §一（edu.sql 权威的机制化保障）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | verify_schema.py |
| 验证 | sd-tester + RunCommand+mysql CLI | 逐表逐列逐索引逐外键对比 |
| 审查 | review-screener-3 | CI 配置审查 |
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
- 解析 edu.sql → information_schema 对比：列/类型/默认值/唯一键/外键/注释
- 不一致输出红色清单 + 非零退出码
- CI workflow 集成（DDL 变更即触发）

## 5. 验收标准（Given/When/Then 全文）
- Given 重构库已执行 task01~04 全部 DDL，When 运行校验脚本，Then 输出"0 差异"且退出码 0；任何列类型/默认值/注释偏差以红色清单列出
- Given CI 集成完成，When 提交任意 DDL 变更，Then 校验自动运行，差异即构建失败
- Given 保留表清单变更，When 校验运行，Then 27 保留表范围被显式声明（不在 66 表清单即报游离表）

## 6. 交接与记忆
- 完成 → 看板 task05=DONE → sync.ps1
- 交付物：scripts/verify_schema.py + CI workflow + 校验报告（CP1 依据）
