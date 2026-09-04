# task30: RAG：contextualize 写入步骤（chunk 上下文前缀 + 降级）

> **类型**：rag ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W4 ｜**工作量**：L
> **前置**：无（写入链路独立，可与 AI 并行）｜**后置（联调节点）**：task31、task34（课程知识导入复用）

## 1. 选型依据
- tech-source-audit.md §三（Contextual Retrieval：Anthropic 实测 contextual embeddings 降 35% 失败率；50-100 token 前缀）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | contextualize.py + pipeline 改造 |
| 测试 | sd-tester | 降级路径/并发限速 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 工具 | context7 MCP | — |
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
- CONTEXT_PROMPT：<document>+<chunk> → 50-100 token 上下文；仅知识型内容生成（题库/代码跳过）；并发 8 限速
- pipeline：chunker→contextualize→embedder；chunk.content=前缀版、chunk.raw_content=原文（answer 展示用）
- 失败降级：无前缀原 chunk 照常入库 + degraded_reason
- Milvus 存储预算 +15%

## 5. 验收标准（Given/When/Then 全文）
- Given 一份讲义文档切片，When 入库，Then 知识型 chunk 均带上下文前缀且 raw_content 保留原文；检索返回的 content 为前缀版（提高召回）、展示用 raw_content
- Given LLM 调用失败，When contextualize 异常，Then 降级为无前缀原 chunk 照常入库（三级降级哲学一致），degraded_reason 记录
- Given 批量入库，When 并发控制，Then 并发 ≤8（不击穿 LLM 预算）

## 6. 交接与记忆
- 完成 → 看板 task30=DONE → sync.ps1
- 交付物：contextualize.py + pipeline 改造 + 单测
