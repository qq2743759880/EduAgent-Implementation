# task-VEC: 向量检索 CUDA/Milvus 启用专项（三层记忆真实向量化）

> **类型**：rag+ai ｜**执行工具**：Trae ｜**工作量**：M
> **触发**：用户诉求"task29 前检索都没用虚拟机向量库检索，要保证正常使用 Milvus/MongoDB/neo4j/MinIO + CUDA GPU 加速"
> **前置**：task25（三层记忆）、task29（评估）、task34（kb-rebuild-milvus）

## 1. 背景与现状（2026-08-22 实证）
- **VM 192.168.85.101 现已全可达**（此前会话记录"不可达"已过时）：
  - Milvus :19530 ✅（collections: edu_knowledge 4981 行 / user_memory 0 行 / pf_bagu_kb 5724 行）
  - MinIO :9000 ✅、MongoDB :27017 ✅
- **CUDA 可用**：RTX 4060 Laptop，torch 2.11.0+cu128；BGE-M3 本地模型存在（C:/ai-models/bge-m3，2.27GB）
- **BGE-M3 实测**：加载 17.39s（CUDA 分配 1.15GB）、编码 2 条 1.72s、1024 维
- **知识库/chat 检索链路已真实走 Milvus+BGE-M3 CUDA**（embedder.py encode_dense_batch → loader.hybrid_search → Neo4j → rerank），降级链完整
- **唯一缺口**：三层记忆 `app/ai/memory/vector.py` 的 `MemoryVectorStore` 硬编码 `DeterministicEmbedder`（char 2-gram 哈希向量），未用真实 BGE-M3；user_memory 集合 0 行，记忆召回无真实语义

## 2. 改造点
1. `app/ai/memory/vector.py`：`MemoryVectorStore` 的 embedder 改为**复用 `app.knowledge.importer.embedder.encode_dense_batch`**（真实 BGE-M3，EMBED_DEVICE=cuda）
   - upsert/search 的向量生成走真实 embedding（1024 维对齐 Milvus EMBEDDING_DIM）
   - 保留降级：BGE-M3 不可用/encode 失败 → 回落 DeterministicEmbedder（512 维需对齐问题：Milvus schema 是 1024，降级维度须=1024 或标注）
2. `app/ai/memory/store.py`：`MemoryVectorStore()` 默认实例化时注入真实 embedder
3. 实测：写入 user_memory（真实向量）→ 同 query 检索返回语义相关记忆；对比哈希 vs BGE-M3 召回质量
4. Milvus user_memory collection 若维度不匹配（当前 schema 用 MEMORY_VECTOR_DIM=512）需重建为 1024

## 3. 验收标准（Given/When/Then）
- Given 三层记忆启用，When upsert 一条记忆，Then user_memory 集合行数+1 且向量为 BGE-M3 真实 1024 维（非哈希）
- Given 语义查询，When search，Then 返回与查询语义相关的记忆（对比哈希降级召回显著提升）
- Given BGE-M3 不可用，When upsert/search，Then 自动降级哈希并标注 degraded_reason，不 500
- Given 全链路，When 实测，Then 检索走 CUDA GPU（nvidia-smi 观测显存占用）+ Milvus 真实集合，非 in-memory

## 4. 纪律
- 一次一个任务一个 commit；不伪造数据；降级如实标注
- 复用 loader.py 唯一 Milvus 入口（不旁路 pymilvus）
- 完工写 test-reports\task-vec-completion-report.md → sync.ps1 → 停下等验收

## 5. 交接
- 看板 task-VEC=DONE；记忆同步