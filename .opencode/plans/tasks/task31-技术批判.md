# task31 验收批判（强制技术批判）

> 对象：task31 RAG reranker + course_public 分区（Trae，commit a274629）
> 结论：**验收通过**。

## 实证结果
- commit `a274629`（11 文件 +729/-21）；reranker.py/retriever.py/loader.py/config.py/service.py 交付。
- 契测 **21 passed（task31 11 + perf_guard 相关 + task30 回归）** 实跑，无回归。
- 实证 JSON：reranker mode=real、degraded=null、语义 5.18 排前 vs 促销 -9.67 排末、recall 150→final 5、sorted_desc=true、GPU 91%/4.3GB、warm 0.372s。
- **真实阻断问题修复**：FlagReranker 在 transformers 5.15.0 因 prepare_for_model 被移除必抛 AttributeError → AutoModelForSequenceClassification 重写打分，保留外部契约。

## 批判 1（P2）：AutoModelForSequenceClassification 重写打分与 FlagReranker 原始输出语义等价性未量化
- **问题**：重写后打分逻辑与 FlagReranker 语义等价，但无基准对拍（原始实现不可用，无法直接对比），排序质量依赖单次实证。
- **方案**：task32 rag-evaluator 用评估集量化 rerank 增益（vs 规则兜底），固化质量基线。

## 批判 2（P2）：reranker 首载 infer_sec=10.893s（含模型加载）超 P95 目标，仅 warm 0.372s
- **问题**：task31_results.json `latency_ok=false`（infer_sec=10.893s 首载含 load）；warm 150 对 0.372s 达标，但冷启动首个请求可能拖慢链路。
- **方案**：生产预热（同 task-VEC 批判②），启动预加载 Reranker 单例；task39 压测覆盖。

**结论**：两条为后续优化项，不阻塞 task31。