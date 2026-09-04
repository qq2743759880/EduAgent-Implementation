# task34: Milvus/Neo4j 清除 + 课程/题目知识切片生成与批量入库

> **类型**：ops+rag ｜**执行工具**：Trae ｜**阶段**：P8 ｜**并行组**：W6 ｜**工作量**：XL
> **前置**：task07, task30 ｜**后置（联调节点）**：task35；CP8 检查点

## 1. 选型依据
- tech-source-audit.md §三（Milvus 保留：sparse 向量 BM25 通道是 Contextual Retrieval 双路关键；drop+rebuild 复用 loader.py ensure_collection_exists）
- edu-data-refactor-plan.md FR-KB-01/02（清除重建 + pf_bagu_kb 保留）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 切片生成 + 批量入库脚本（断点续跑） |
| 验证 | sd-tester + RunCommand+mysql CLI + milvus | 行数/分区/索引校验 |
| 汇总 | summarize skill | 进度日报 |
| 审查 | review-screener-1 | 清除前快照复核 |
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
- drop+rebuild edu_knowledge（schema：id/chunk_id/content/content_type/source_file/dense_vec 1024/sparse_vec/tenant_id/visibility）；Neo4j 全清
- courses.json（219 系列 + 657 模块）+ questions.json（1752 题干+解析）
- 200/批 dense+sparse 双向量入库（EMBED_BATCH_SIZE 32）；chunk_id upsert 断点续跑；先课程后题目
- 公共知识进 `_default` + 机构 visibility 分区；pf_bagu_kb 原样保留

## 5. 验收标准（Given/When/Then 全文）
- Given 重建脚本执行，When 中途中断后重跑，Then 从断点续跑（已入库 chunk upsert 跳过），不重复、不丢失
- Given 入库完成，When 校验，Then 行数 = courses+questions 切片数、`_default`/机构分区分布正确、索引加载状态正常、pf_bagu_kb 集合原样保留（行数不变）
- Given 清除前快照，When 执行 drop，Then 先落 schema 定义与计数快照（回滚依据）

## 6. 交接与记忆
- 完成 → 看板 task34=DONE → sync.ps1
- 交付物：重建脚本 + 切片 JSON + 入库报告（行数/分区/索引）
- 风险：向量化耗时跨夜。缓解：批大小 32 + 断点 + 分夜执行 + 日报
