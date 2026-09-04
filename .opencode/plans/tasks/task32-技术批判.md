# task32 验收批判（强制技术批判）

> 对象：task32 RAG 离线评估（Trae，commit 60671a2）
> 结论：**验收通过**（评估诚实、A/B 真实运行、批判承接逐条核对）。

## 实证结果
- commit `60671a2`（5 文件 +929/-2）；rag_evaluator.py/build_eval_set32.py/verify_task32.py/test_contract_task32.py 交付。
- 契测 **10 passed** 实跑确认（无 Milvus/GPU，fake strategies）。
- A/B 真实运行：top-20 饱和 100/100（评估集口径）、hit@1 6→38（+533%）、MRR@20 0.51→0.68（+33%）、degraded=0。
- 批判承接核对：task-VEC③ 100条≥30 ✅、task31① 增益量化 ✅、task30② 真实 LLM 前缀未复验如实标注（刻意不烧 LLM，窗口内可补）。

## 批判 1（P2）：GWT③ top-20 命中率指标因"冻结召回+GT 自匹配"饱和，无法区分重排增益
- **问题**：评估集用"GT 自身 chunk 自匹配"，GT 恒被召回恒在 top-20，双方 100% 饱和，二值指标无区分度；+15% 目标无法达成。
- **竞品对标**：Anthropic Contextual Retrieval / Cohere rerank 评估均用**真实用户问句 + 手工标注 answer→doc 映射**（非自匹配），或 LLM 改写 paraphrase 制造非子串 GT，避免饱和（参考 tech-source-audit §三）。
- **方案**：后续补"非自匹配硬样本"评估集（真实问句 + 手工映射），重跑 A/B 量化 top-20 真实增益；或用 hit@1/MRR 作为主指标（已显著佐证）。

## 批判 2（P2）：云端 rerank 未接入，评估与生产口径不一致
- **问题**：离线评估用本地 bge-reranker，生产配置 RERANK_BACKEND=cloud（若后续接 VikingDB doubao-rerank），口径漂移风险。
- **方案**：云端 rerank 接入后（需 VikingDB AK/SK）重跑本 A/B 对齐；报告已披露该风险。

## 批判 3（P2）：task30② 真实 LLM 前缀验证仍挂起
- **问题**：contextualize 真实 LLM 前缀质量/成本未端到端验证（CONTEXTUALIZE_ENABLED=False 默认）。
- **方案**：窗口内（12:00-14:00/18:00-9:00）单独安排 RUN_REAL_LLM=1 复验，或并入后续 RAG 任务。

**结论**：三条为后续改进项，不阻塞 task32。