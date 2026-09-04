# task-VEC 完工报告 — 虚拟机向量库 + CUDA GPU 加速

- 分支：`feature/task44-courses`
- 角色：后端 + 数据库开发者
- 时间：2026-08-25
- 状态：**待编排者验收**

## 一、任务背景与目标（精简 GWT）

用户诉求：检索要正常使用虚拟机向量库（Milvus）+ CUDA GPU 加速，让记忆召回从「哈希伪语义」升级为「真实语义向量」。

| # | GWT | 结论 |
|---|-----|------|
| ① | `vector.py MemoryVectorStore` 复用 `encode_dense_batch`（真实 BGE-M3 CUDA 1024 维），替换 `DeterministicEmbedder` 哈希 | ✅ |
| ② | 对接已连通 Milvus `user_memory`（维度校验 1024），upsert/search 真实语义向量 | ✅ |
| ③ | 降级链保留：BGE-M3 不可用 → 哈希 + `degraded_reason`，不 500 | ✅ |
| ④ | 实测：写入 user_memory → 语义 query 召回提升（对比哈希）+ nvidia-smi CUDA 占用 | ✅ |

## 二、现状实证（任务文档要求）

- Milvus `user_memory` 集合可连通，**vector 字段维度为 1024**（`_verify_collection_dim` 校验通过），无需重建。
- BGE-M3 本地模型 `C:/ai-models/bge-m3`，`EMBED_DEVICE=cuda`，torch.cuda.is_available()=True。
- `python -m pytest tests/test_contract_task_vec.py -q` → **6 passed**（含排除 skipped 的集成用例）。

## 三、代码改动（本次 task-VEC 专属，一次一 commit）

1. **[vector.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/ai/memory/vector.py)**（核心，唯一被改的既有源码）
   - 新增 `SemanticEmbedder`：优先复用 `app.knowledge.importer.embedder.encode_dense_batch`（BGE-M3 CUDA，1024 维）；失败降级 `DeterministicEmbedder` 哈希并置 `degraded_reason`（GWT①③）。
   - 维度统一 1024（= `EMBEDDING_DIM` / Milvus `user_memory` schema），废弃旧 `MEMORY_VECTOR_DIM=512` —— 修复历史上 user_memory 写不进的维度不匹配根因。
   - **Milvus 唯一入口**：经 `app.knowledge.importer.loader.get_milvus_client()` 全局单例（复用 + 3s 超时兜底），**不旁路 pymilvus**（纪律）。
   - 新增 `_verify_collection_dim`：现有 schema 维度不符则如实抛错 → 上层降级内存，不静默失败。
   - 新建集合后显式 `load_collection`（R-独立审查 P2：否则 search 报 collection not loaded）。

2. **[store.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/ai/memory/store.py)**：无改动（已默认注入 `MemoryVectorStore()` → SemanticEmbedder）。

3. **[tests/test_contract_task_vec.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/tests/test_contract_task_vec.py)**（新增）：维度/语义/降级/确定性/in-memory/Milvus 集成 6 用例。

4. **[scripts/verify_task_vec.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/scripts/verify_task_vec.py)** + `scripts/task_vec_results.json`（实证产物）。

## 四、GWT 验收证据

### ① 真实语义向量（替换哈希）
`test_semantic_embedder_dim_1024`：BGE-M3 输出 1024 维 python float，`degraded_reason is None`。

### ② Milvus user_memory 对接（dim=1024）
`test_milvus_upsert_semantic_recall_integration`：写入真实 Milvus user_memory，语义查询 "图像识别用深度学习模型怎么做" 返回 top1 = memory_id 10（"用户偏好深度学习和神经网络…图像分类"）。实证 `task_vec_results.json.milvus`：backend=milvus, dim=1024, degraded=null，top1 score=0.6908。

### ③ 降级链（不 500）
`test_degrade_when_bge_unavailable`：注入 `raise RuntimeError` 的 encode_fn → 返回 1024 维哈希，`degraded_reason` 含 "BGE-M3 不可用"，向量有限（finite）。实证 `degrade.is_hash=true, finite=true`。
关键修复（R-独立审查 P1）：在调用 `encode_dense_batch` 前主动探测 `_get_bge_model()`；因 encode 内部吞异常永不 raise，若不探测则真实 BGE 不可用时降级分支形同虚设且可能误烧付费 Embedding API。

### ④ 实测召回提升 + CUDA 占用
**召回对比（5 query @ rank1，纯内存同源比较）**，见 `task_vec_results.json.rank1`：
- BGE-M3：5/5 = **1.0**
- 哈希：4/5 = **0.8**（"下周旅行计划"误判 id3≠id2）
- bge_beats_hash = **true**

**CUDA 观测（nvidia-smi）**：BGE-M3 推理期间 GPU 显存占用约 1.07GB、util 约 22%，确认向量编码走 GPU（CUDA），非 CPU 回退。

## 五、独立子代理红线审查结论（复现于汇总再验）

writable替代审查命中 5 项红线并落地修复：
- 数据真实 ✅：BGE-M3 真实编码，无 MOCK/伪造向量。
- 维度对齐 ✅：真实/降级统一 1024 = Milvus schema；2ggg6/补测确认 MemoryVectorStore.dim == settings.EMBEDDING_DIM == 1024。
- 唯一 Milvus 入口 ✅：只用 `loader.get_milvus_client()`，无 pymilvus 旁路。
- 降级不 500 ✅：BGE/Milvus 任一不可用 → 内存降级 + degraded_reason，不抛到调用方。
- 无 DeepSeek 热路径 ✅：BGE 本地 GPU 编码，记忆/查询向量化不走付费 LLM API。

## 六、测试与回归

- `pytest tests/test_contract_task_vec.py`：**6 passed**（34.4s）。
- 既有记忆契约 `tests/test_contract_task25.py`：**11 passed**，无回归。
- Milvus 测试数据已清理（clear_user），`user_memory` 恢复干净状态。

## 七、待办与风险

- 无阻碍项。BGE-M3 本地 GPU 加载约 2.2GB 显存（RTX 4060 Laptop 8G 富余）。首次调用加载权重较慢，二次调用全局缓存复用。
- 未开始 task30/后续（等编排者验收后才继续）。

## 八、同步与收尾

- `powershell -File D:\.ai-hub\sync.ps1` 已执行，AI-Hub 资产同步完成。
- 已 `git commit` task-VEC 专属文件（源码头 + 报告 + 实证），工作树其他任务文件未纳入。

**停下，等待编排者验收。**