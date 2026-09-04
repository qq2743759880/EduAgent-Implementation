# task31 完工报告 — RAG reranker 接入（bge-reranker-v2-m3 CUDA）+ course_public 分区

- 分支：`feature/task44-courses`
- 角色：后端 + 数据库开发者
- 时间：2026-08-25
- 前置：task30 contextualize（content=前缀版 / raw_content）
- 状态：**待编排者验收**

## 一、任务目标（精简 GWT）

| # | GWT | 结论 |
|---|-----|------|
| ① | reranker.py：懒加载单例、失败返回 None → `_rule_rerank` 兜底、`RERANKER_BATCH_SIZE=16` | ✅ |
| ② | retriever：top_k 12→150（RRF 后）→ rerank top-20 → `_cliff_cutoff` 断崖 → 5；按 rerank 分数排序 | ✅ |
| ③ | course_public 分区：课程知识隔离用户上传；过滤 `series_code/module_codes/content_type/tenant_id` | ✅ |
| ④ | sparse 基于 contextual 文本生成（BM25 双路增益） | ✅ |

## 二、关键架构决策（修复一个真实阻断问题）

**FlagReranker 在 transformers 5.15.0 下永久不可用**。实证首跑：`FlagReranker.compute_score` 内部调用
`tokenizer.prepare_for_model(...)`（site-packages/FlagEmbedding/inference/reranker/encoder_only/base.py:147），
该 API 在 transformers 5.x 已移除，导致**每次推理必抛 `AttributeError: XLMRobertaTokenizer has no attribute prepare_for_model`**
→ reranker 永远降级到规则兜底，GWT①②名存实亡。

**修复**：不改环境依赖（避免脆弱的 site-packages 补丁），在 [`reranker.py`](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/knowledge/reranker.py)
直接用同款模型 `AutoTokenizer + AutoModelForSequenceClassification` 重写打分（batch 多对编码，与 FlagReranker 语义等价），
保留完全一致的外部契约（懒加载单例 / 返回 None / 降级）。

## 三、代码改动（本次 task31 专属）

1. **[reranker.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/knowledge/reranker.py)**（新增，核心）：
   - 线程安全懒加载单例 `Reranker.get()`（OLP lock），进程内只加载一次模型 → 多 worker 不重复占用显存（薄弱点 W3 OOM 缓解）。
   - `_load_error` 记录后**不再重试**（避免每请求 OOM 重试拖垮进程）；`rerank` 失败返回 `None` → 调用方 `_rule_rerank` 兜底 + `degraded_reason="reranker_unavailable"`（GWT①）。
   - `compute_score` 按 `batch_size=RERANKER_BATCH_SIZE(16)` 分批，控制峰值显存（transformers 5.x 兼容的 batch 多对编码）。
   - fp16（`cuda`）+ `model.eval()`，CUDA 推理。

2. **[config.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/config.py)**：`RETRIEVER_RECALL_TOPK=150`、`RETRIEVER_RERANK_TOPK=20`、`COURSE_PUBLIC_PARTITION="course_public"`、`RETRIEVER_EXCLUDE_CONTENT_TYPES=(promotion/schedule/announcement/marketing)`；`RERANKER_PATH/DEVICE/BATCH_SIZE=16`。

3. **[retriever.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/chat/retriever.py)**：
   - `_search_tenant_ids`：非 admin 搜索分区扩为 `["_default", course_public, user_{id}]`（GWT③ 课程知识进保留分区）。
   - `_milvus_hybrid_search_safe`：召回 `top_k` 统一抬到 `RETRIEVER_RECALL_TOPK=150`（GWT② 12→150）；`filter_expr = content_type not in [...]` 排除促销/班次/公告混入（GWT③）。
   - `_rerank_docs`（新增）：BGE-rerank 打分 → L1 归一化到 0-1 → 按分数降序 → 截断 `RETRIEVER_RERANK_TOPK=20`；不可用 → `_rule_rerank` + `degraded_reason="reranker_unavailable"`（GWT②）。
   - 端到端 `retrieve_three_channel`：150 → rerank top20 → `_cliff_cutoff` 断崖 → 5，按 rerank 分数排序。

4. **[loader.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/knowledge/importer/loader.py)**（唯一 Milvus 入口，不旁路 pymilvus）：
   - `COURSE_PUBLIC` 保留分区：`_get_partition_name` 支持 `course_public`（不混用户上传）。
   - `hybrid_search` 新增 `filter_expr` 参数（AnnSearchRequest 的 `expr`，稠密+稀疏双路传参）。
   - 修复 `chunk_id`：返回真实 chunk ID（原误用 CRC32 主键致身份错乱）。

5. **[service.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/admin/rag_admin/service.py)** + **[knowledge/retriever/retriever.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/knowledge/retriever/retriever.py)**：管理端分区校验与 `_determine_search_partitions` 纳入 `course_public`（GWT③）。

6. **[tests/test_contract_task31.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/tests/test_contract_task31.py)**（新增）：11 用例。**[tests/test_perf_guard.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/tests/test_perf_guard.py)**：隔离 rerank 阶段（stub `_rerank_docs`）防性能单测触发真实 reranker。

7. **[scripts/verify_task31.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/scripts/verify_task31.py)**（新增）+ `scripts/task31_results.json`：真实 CUDA 实证，不烧 DeepSeek（`use_hyde=False / enable_graph=False`）；`NO_RERANK=1` 可观察降级。

## 四、GWT 验收证据

### ① reranker 懒加载单例 + 降级 + batch
- `test_reranker_singleton` PASS：单例复用（实证 `singleton_same=True`）。
- `test_reranker_unavailable_returns_none` PASS：模型缺失/失效返回 None 不抛 500。
- `test_rerank_fallback_on_unavailable` / `test_rerank_sorts_by_score_and_truncates_to_20` PASS。
- 实证 warm 推理 150 对 = **0.372s**（远低于 P95≤8s），`batch_size=16` 生效；GPU util 峰值 **91%**、显存约 4.0GB（FP16）。

### ② 召回 150 → rerank 20 → 断崖 5，按 rerank 分数排序
- 实证 retrieve：`raw_retrieved_count=150` → `final_count=5`，`sorted_desc=true`，`degraded_reason=null`（**真实 rerank 生效，未降级**）。
- 排序语义正确：候选含促销文案时，促销排末位；语义相关排前。
- `test_cliff_cutoff_to_5` PASS，`test_normalize_rerank_scores_monotonic` PASS。

### ③ course_public 隔离 + filter_expr
- `test_course_public_partition_and_filter_isolate` PASS（真实 Milvus 读写）：课程 chunk 进 `course_public`、促销 chunk 检出不到（`filter_expr` 排除 promotion）。
- `test_search_tenant_includes_course_public` / `test_get_partition_name_course_public_literal` / `test_admin_partition_validation_allows_course_public` PASS。

### ④ sparse 基于 contextual 文本（BM25 双路增益）
- `test_sparse_built_from_query_text` PASS；实证 `build_sparse_vector` 基于（HyDE 后）contextual 文本生成，配合作战建议：入库端与检索端 BM25 同源，双路互补召回。

## 五、降级纪律（薄弱点 W3 / 生产安全）

- reranker 加载或推理任何失败 → 返回 `None` → `_rule_rerank` 兜底 + `degraded_reason="reranker_unavailable"`，质量不劣于现状，**不 500**。
- Milvus 检索超时 → 空 docs + `degraded_reason`，不阻塞 event loop（实测 8s 超时正确降级）。
- 多 worker 显存 OOM：懒加载单例 + fp16 + batch128→16 分批，进程内只持一份模型。

## 六、测试与回归

- `tests/test_contract_task31.py`：**11/11 PASS**（含真实 Milvus 集成读写）。
- `tests/test_perf_guard.py`：**15/15 PASS**（task31 契约 + P1-4 性能，rerank 阶段已隔离）。
- 实证 `verify_task31.py`：真实路径 recall=150/final=5/referrank 生效/degraded=null/GPU 91%；降级路径（`NO_RERANK=1`）degraded=reranker_unavailable/不 500；Milvus 超时路径空 docs+降级。产物写入 `task31_results.json`。

## 七、交付物

- `app/knowledge/reranker.py`（新）+ config 参数 + retriever/loader/service 改造
- `tests/test_contract_task31.py`（新）+ `tests/test_perf_guard.py`（rerank 隔离）
- `scripts/verify_task31.py` + `scripts/task31_results.json`

## 八、待办

- 无阻碍项。真实启用无需额外配置（RERANKER_PATH 已指向本地模型）。
- 未开始 task32（等编排者验收）。

## 九、同步

- `sync.ps1` 已执行，AI-Hub 资产同步完成。
- `git commit` task31 专属文件，其他任务文件未纳入。

**停下，等待编排者验收。**