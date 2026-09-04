# task32: RAG：rag_evaluator top-20 指标 + 离线评估（+15% 目标）

> **类型**：rag+test ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W4 ｜**工作量**：M
> **前置**：task31 ｜**后置（联调节点）**：CP4.5 检查点

## 1. 选型依据
- tech-source-audit.md §三（Anthropic 实测：+rerank 降 67% 失败率；本项目目标 ≥+15% 命中）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | rag_evaluator 补 top-20 指标 |
| 验证 | sd-tester | 离线评估集回放 |
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
- rag_evaluator.py 补 top-20 命中率指标（对照 _rule_rerank 基线）
- 离线评估集：含既往规则重排低分样本
- 报告含差距分析与调参建议

## 5. 验收标准（Given/When/Then 全文）
- Given 离线评估集（含既往规则重排低分样本），When 跑评估，Then rerank 后 top-20 命中率较规则重排基线提升 ≥+15%，未达标输出差距分析与调参建议
- Given 评估报告生成，When 提交评审，Then 指标可复现（同数据同参数同结果）

## 6. 交接与记忆
- 完成 → 看板 task32=DONE → sync.ps1
- 交付物：rag_evaluator 改造 + 评估集 + 评估报告
