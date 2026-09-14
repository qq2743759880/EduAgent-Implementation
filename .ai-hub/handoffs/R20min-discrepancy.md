# R20-min 执行期越界发现上浮（discrepancy，2026-09-14）

> 执行 agent：R20-min 评估基线冻结 · 以下发现均**不在本任务范围内自行修复**（守则 4），如实上浮交编排者裁定。

## D-1（正产缺陷，中优先级）：Neo4j 图通道对 QuestionTag 实体类型 ValidationError
- **现象**：eval 32 条中 3 例（idx 1/12/24）图扩展降级，日志报 pydantic `literal_error: Input should be 'Series', 'Module', 'Keyword' or 'Prerequisite' [input_value='QuestionTag']`，导致 `_graph_expand` 整体跳过（retriever.py:352-355 兜底捕获），GraphEntity 丢失。
- **定位**：`app/chat/retriever.py:321-325` `type_map` 与 `app/chat/schemas.py` `GraphEntity.entity_type` Literal 枚举不一致——DB 侧存在 `QuestionTag` 标签（task35 图谱重建 2100 节点），schemas 的 Literal 未收录该值。
- **影响**：标签类问题检索时图谱扩展静默丢失（有降级留痕不 500），检索主链不受影响（本基线 3 例降级样本指标无异常）。
- **建议落点**：R10（状态通道/图相关）或独立小修——schemas Literal 增补 `QuestionTag` 或 type_map 归一为 `Keyword`。

## D-2（环境漂移，低优先级）：BGE 模型路径 .env 指向不存在的盘符
- **现象**：`edu-agent/.env:38,40` 写 `BGE_M3_PATH=C:/ai-models/bge-m3`、`RERANKER_PATH=C:/ai-models/bge-reranker-v2-m3`，两目录均不存在；真实模型在 `E:/stu/ai-models/`。本次执行以进程级 env 覆盖（`RERANKER_PATH`/`BGE_M3_PATH`）解决，**未改动 .env**（gitignore 凭据文件 + 守则）。
- **影响**：任何未带覆盖的新进程（sidecar/后端）会静默走 API 回退或报"模型目录不存在"（sidecar 日志已见此 WARNING），embedding 云端回退使查询向量与库内 BGE-M3 向量不同源——**教训 7 的向量同源红线在当前环境实际处于漂移态**。
- **建议**：编排者/用户裁定后更新 .env 两行（一行改动），或建立模型路径 env 模板。

## D-3（技术债，低优先级）：dense nprobe=10 硬编码使灵敏度实验无法走正产链
- **现象**：`app/knowledge/importer/loader.py:318` dense_req param `nprobe: 10` 为字面量（同函数 RRF k=60 亦然），无 settings 透出口。
- **影响**：本次灵敏度反证须以"独立同参重放通道"（r20min_run.py `_run_sensitivity`，与 loader.py:315-348 逐字段对照）实现，绕过 rerank/断崖层只出召回层布尔口径；无法直接验证"正产链在坏参数下指标下降"。
- **建议**：R03 迁移批次顺带把 nprobe/rrf_k 提为 settings（`MILVUS_NPROBE`/`MILVUS_RRF_K`），届时灵敏度实验可走全链。

## D-4（测量口径备注，无修复需求）：断崖截断在部分 query 上激进
- **现象**：trace 显示部分 query final_layer=2（如 idx#0，rerank 后分数断崖 >0.4 即截断，CLIFF_MIN_KEEP=3 的配置仅约束 CLIFF 相关旧参数、retriever._cliff_cutoff 无最小保留数）。
- **影响**：final docs 数波动（2~5），top5 口径实际是"≤5"；不影响基线有效性（判定就是"GT 是否在最终 docs"），但 R02/R03 对照时须知悉该波动是正产行为。
