# task39: 性能压测（Locust P95 ≤800ms）+ 容灾演练（六存储宕机）

> **类型**：test+ops ｜**执行工具**：Trae ｜**阶段**：P9 ｜**并行组**：W8 ｜**工作量**：L
> **前置**：task69, task23 ｜**后置（联调节点）**：CP9 检查点

## 1. 选型依据
- tech-source-audit.md §四（缓存三防验证目标 P95 ≤800ms 命中缓存）
- tech-source-audit.md §七（VM 网络/系统级配置的容灾验证）
- doc-architect-tech-arch.md §6.4（优雅降级矩阵）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 执行 | sd-dev | Locust 脚本改造 + 故障注入 |
| 验证 | sd-tester + harden skill | 压测报告 + 降级对照 |
| 审查 | review-screener-1/3 | — |
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
- Locust：课程浏览链路 + 下单链路 + chat 链路
- 容灾演练：Milvus/Mongo/Redis/Neo4j/MinIO/LLM 逐一 kill，对照 §6.4 降级矩阵（degraded_reason 齐全、无 500；MySQL 快速失败 503）

## 5. 验收标准（Given/When/Then 全文）
- Given Locust 压测课程浏览/下单链路（命中缓存），When 执行，Then P95 ≤800ms；chat 链路 P95 ≤8s、首包 ≤3s；Redis 命中率达标记录
- Given 故障注入（六存储逐一 kill），When 验证核心链路，Then 无 500：Milvus→空 docs+降级答案、Redis→缓存直通+限流放行、Mongo→chat_message MySQL 兜底、Neo4j→跳图谱扩展、MinIO→明确 503、LLM→规则兜底答案、MySQL→快速失败 503（熔断防池耗尽）
- Given 演练完成，When 输出报告，Then 每项降级行为与 §6.4 矩阵逐条对照记录 + edu_degraded_total{component} 指标可见

## 6. 交接与记忆
- 完成 → 看板 task39=DONE → sync.ps1
- 交付物：压测报告 + 容灾演练报告（CP9 依据）
