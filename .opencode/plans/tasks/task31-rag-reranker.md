# task31: RAG：reranker 接入（top-150→rerank→top-20→断崖→5）+ course_public 分区

> **类型**：rag ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W4 ｜**工作量**：L
> **前置**：task30 ｜**后置（联调节点）**：task32（评估）

## 1. 选型依据
- tech-source-audit.md §三（bge-reranker-v2-m3：MTEB 中文榜单 + 本地化零 API 成本；top-150→rerank→top-20 对齐 Anthropic 实测；course_public 分区防污染）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | reranker.py + retriever 改造 |
| 测试 | sd-tester | 降级攻防（GPU 不可用） |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
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
- reranker.py：FlagReranker 懒加载单例、失败返回 None → _rule_rerank 兜底、RERANKER_BATCH_SIZE=16
- retriever：top_k 12→150（RRF 融合后）→ rerank top-20 → _cliff_cutoff 断崖 → 5
- course_public 分区：交易域课程知识与用户上传隔离；过滤表达式 series_code/module_codes/content_type/tenant_id
- sparse 向量基于 contextual 文本生成（BM25 双路增益）

## 5. 验收标准（Given/When/Then 全文）
- Given reranker 模型可用，When 检索执行，Then 链路为 top-150→rerank→top-20→断崖→5；返回文档按 rerank 分数排序
- Given GPU/模型加载失败，When 检索执行，Then 自动降级规则重排（质量不劣于现状），degraded_reason="reranker_unavailable"
- Given 课程知识入库，When 写入，Then 进入 course_public 分区；学科问答检索不混入促销/班次文案（分区过滤验证）

## 6. 交接与记忆
- 完成 → 看板 task31=DONE → sync.ps1
- 交付物：reranker.py + retriever 改造 + 分区定义 + 单测
- 风险（薄弱点 W3）：多 worker 显存 OOM。缓解：懒加载+单例+降级；必要时独立 reranker 服务
