# task35: Neo4j 图谱重建（5 节点 + 3 边）+ 重建校验报告

> **类型**：ops+rag ｜**执行工具**：Trae ｜**阶段**：P8 ｜**并行组**：W6 ｜**工作量**：M
> **前置**：task34 ｜**后置（联调节点）**：CP8 检查点

## 1. 选型依据
- edu-data-refactor-plan.md FR-KB-03/04（Series/Module/Session/Question/KnowledgePoint 节点 + CONTAINS/BELONGS_TO/RELATED 边）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 图谱构建脚本 |
| 建模 | mermaid skill | 图谱拓扑图 |
| 验证 | sd-tester | 计数/孤立节点/检索冒烟 |
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
- 节点：Series/Module/Session/Question/KnowledgePoint（题目 analysis_text 提取）；边：CONTAINS/BELONGS_TO/RELATED
- 校验报告：节点/关系计数 vs 基线（4981 条/1330 节点 6194 关系）

## 5. 验收标准（Given/When/Then 全文）
- Given 图谱构建完成，When 查询校验，Then 系列→模块→课次→题目层级关系计数正确、KnowledgePoint 提取非空、孤立节点数 ≈0
- Given 重建完成，When 执行检索 + 图谱查询冒烟（知识问答走三通道、图谱扩展可用），Then 结果正常且 RAG 全链路（Milvus→Neo4j→rerank→回答）可用
- Given 校验报告生成，When 提交，Then CP8 检查点达成

## 6. 交接与记忆
- 完成 → 看板 task35=DONE → sync.ps1
- 交付物：图谱构建脚本 + 校验报告
