# task30 验收批判（强制技术批判）

> 对象：task30 RAG contextualize 写入步骤（Trae，commit ba57533）
> 结论：**验收通过**。

## 实证结果
- commit `ba57533`（9 文件 +764/-10）；contextualize.py/pipeline.py/loader.py/models.py/config.py 交付 + verify_task30.py + task30_results.json。
- 契测 **21 passed（task30 10 + task25 11）** 实跑确认，无回归。
- 实证：CONTEXT_PROMPT 含 <document>/<chunk>；题库/代码跳过；并发 N=25→max 8；降级 content_unchanged+degraded_reason+no_500；Milvus 字段落库 content_is_prefixed/raw_content_persisted=true。
- P2 修复：CONTEXTUALIZE_ENABLED 默认 False（不烧额度，显式开启才走真实 LLM）。

## 批判 1（P2）：raw_content 双份存储近一倍原文，存储预算披露但未测容量上限
- **问题**：前缀版 content + raw_content 原文 = 近双倍存储；报告披露了增长但未实证接近 Milvus VARCHAR(8000) 上限的边界 case。
- **方案**：task34 全量入库时统计真实存储增长，验证上限。

## 批判 2（P2）：CONTEXTUALIZE_ENABLED=False 默认下功能实际不可用，真实启用未端到端验证
- **问题**：默认关闭避免烧额度，但真实 LLM 启用的端到端（真实前缀质量/成本）未实测（RUN_REAL_LLM=1 未跑）。
- **方案**：task32 评估或后续充值后用真实 LLM 跑一遍确认前缀质量与成本。

**结论**：两条为后续验证项，不阻塞 task30。