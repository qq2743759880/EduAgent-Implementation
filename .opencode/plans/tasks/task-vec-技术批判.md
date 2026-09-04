# task-VEC 验收批判（强制技术批判）

> 对象：task-VEC 向量检索 CUDA/Milvus 启用专项（Trae，commit 63a2555）
> 结论：**验收通过**。

## 实证结果
- commit `63a2555`（6 文件 +592/-31）；vector.py SemanticEmbedder / verify_task_vec.py / task_vec_results.json / test_contract_task_vec.py 交付。
- 契测 **17 passed（task_vec 6 + task25 11）** 实跑确认，无回归。
- 实证 JSON：dim=1024、backend=milvus、degraded=null、top1 score=0.6908。
- 报告证据：BGE rank@1 5/5(1.0) vs 哈希 4/5(0.8)；nvidia-smi GPU 1.07GB；Milvus 唯一入口（loader.get_milvus_client 不旁路 pymilvus）。

## 批判 1（P2）：维度修复采用「废弃 MEMORY_VECTOR_DIM=512 统一 1024」，历史 512 维数据不可兼容
- **问题**：旧降级用 512 维，现统一 1024。若历史存在 512 维哈希向量数据，读取时维度不匹配会触发降级。
- **方案**：task37 清理或后续重建时确认 user_memory 无历史 512 维残留（当前 0 行，实际无影响）。

## 批判 2（P2）：BGE-M3 首次加载 17~34s 的冷启动延迟未缓存预热
- **问题**：首次 embedding 调用加载模型慢（影响首个记忆查询），全局缓存仅进程内复用。
- **方案**：生产环境启动预热（task39 压测或后续），预加载 _get_bge_model() 避免首个请求高延迟。

## 批判 3（P2）：召回对比样本 5 query 有限
- **问题**：BGE vs 哈希 rank@1 对比仅 5 条，统计力有限。
- **方案**：task32（rag-evaluator）用更大评估集固化记忆召回指标。

**结论**：三条为后续优化项，不阻塞 task-VEC。