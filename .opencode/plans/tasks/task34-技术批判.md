# task34 验收批判（强制技术批判）

> 对象：task34 Milvus/Neo4j 清除 + 知识切片重建（Trae，commit 2b1b282→e0e95bc）
> 结论：**验收通过**（GWT①~⑤ 全绿、Milvus 数据实测确认）。

## 实证结果
- commit 链完整（HEAD=e0e95bc）；kb_rebuild_task34.py（五子命令）交付。
- **Milvus 数据实测**：edu_knowledge **2628 行**（219+657+1752）、pf_bagu_kb 5724、user_memory 9——与报告一致。
- **verify 实跑 EXIT=0**：行数/_default 分区/IVF_FLAT+COSINE/SPARSE_INVERTED_INDEX+IP/Loaded/Neo4j 0/三类内容抽样全 PASS。
- GWT① drop+rebuild + Neo4j 全清；② 切片（876+1752）；③ 断点续跑；④ _default 分区 + pf_bagu_kb 保留；⑤ 快照落盘。
- task30 批判①：raw 双份消除（4983→2628）。
- 向量化披露：云端 API max10 回退 BGE-M3 CUDA 本地（1024 维精确）。

## 批判 1（P2）：FR-KB-03 图谱重建（Series/Module/Question 节点）未做
- **问题**：Neo4j 仅全清（1330 节点→0），未重建知识图谱（报告披露）。
- **方案**：派发 task35（kb-graph-rebuild）重建图谱。

## 批判 2（P2）：云端 embedding 单次上限 10 条触发回退，批 32 未用云端
- **问题**：火山/DashScope API 单次 max10，批 32 报 400 → 回退本地 BGE-M3。
- **方案**：后续可调小批到 ≤10 走云端，或接受本地（报告披露在线链路配置未改）。

## 批判 3（P3）：Neo4j 全清后图谱能力缺失（检索 graph_entities 通道降级）
- **问题**：Neo4j 清空后 RAG 图谱扩展通道无数据（依赖 task35 重建）。
- **方案**：task35 尽快重建；当前检索降级规则（degraded_reason 标注）。

**结论**：批判①③为 task35 承接（图谱重建），②为配置调优；task34 本体验收通过。