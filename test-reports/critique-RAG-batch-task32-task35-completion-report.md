# critique-RAG-batch task32+task35 完工报告（后端 RAG 批判批独立实证）

- 日期：2026-09-05
- 角色：tt 工作流 · 后端 RAG 批判批落地区（task32 遗留 4 项 + task35 Neo4j 图谱重建）
- 范围：`edu-agent`（memory recall 对拍 / rerank 增益 / contextualize 前缀质量与成本 / 缓存命中与成本落地 / Neo4j 重构 + retriever 图谱通道）
- 纪律：独立实证（真实 HTTP / 真实向量库 / Neo4j / 持久化真实结果复算）；**不 commit**（等验收后统一 commit）

---

## 一、达成 / 跳过状态（5 项）

| 项 | 归属 | 状态 | 关键量化 |
|---|---|---|---|
| task32-VEC③ 记忆召回评估集扩充+对拍 | 遗留① | ✅ 达成 | BGE-M3 rank@1=1.0，recall@3=1.0，MRR=1.0（30 queries，≥0.9 达标） |
| task31批判① rerank 增益评估 | 遗留② | ✅ 达成（条件性） | top-1: rule0.06→rerank0.38（+533%）；top-20 已饱和 1.0（相对目标未达） |
| task30批判② 真实 LLM 前缀质量/成本 | 遗留③ | ✅ 达成（离线核算） | 前缀质量 2/2（0 降级）；经常性 content 膨胀 +193.8%；实时接口现 402 |
| task29批判③ 缓存命中和成本落地 | 遗留④ | ✅ 达成（复算一致） | 缓存命中率 96.11%；月度成本 ¥529.64 超预算 ¥300（1.77×） |
| task35 Neo4j 图谱重建 + retriever 通道 | 遗留 task35 | ✅ 达成 | 图 2100 节点 / 13132 关系；retriever 图谱通道实查 7~12 实体 |

---

## 二、各分项：做了什么（做）+ 证据（证据）

### 1. task32-VEC③ 记忆召回评估集扩充 + 对拍 ✅

**做**：沿用 `scripts/eval/eval_task32_memory_recall.py`，将原 5 条金标扩充到 12 条 memory、30 条自然改写 query（跨 PREF/进度/错误/目标语义类别），走真实 BGE-M3(CUDA,1024-d) via `MemoryVectorStore.search`，metric=rank@1 / recall@3 / MRR。

**证据**（`scripts/eval/data/task32_memory_recall_result.json`）：`n=30, rank@1=1.0, recall@3=1.0, mrr=1.0, rank1_abs=30/30, degraded_reason=null` → 满足 target `rank@1≥0.9`。

### 2. task31批判① rerank 增益评估 ✅(条件性)

**做**：`scripts/eval/verify_task32.py` 在 100 样本离线 A/B（recall_topk=300，启用 BGE-Reranker cuda），对比 rule 重排 vs rerank 重排。

**证据**（`scripts/eval/data/task32_result.json` summary.multi_k）：
- hit@1：rule 0.06 / rerank 0.38 → **+533.33%**
- hit@3：0.96 / 0.98 → +2.08%；hit@5/10/20：均 1.0/1.0（rule 已饱和，+0.0%）
- mrr@20：0.5117 → 0.6823
- 判定：**目标口径 hit@20 相对提升≥15% 未达成**，根因不是 rerank 无效，而是规则检索在 top-k=300 下 top-20 已 100% 命中（饱和上界）；rerank 的真实价值集中在 top-1~3（首答更准、MRR 提升明显），故记为「条件性达成：收益显著但对应口径是证明规则上界而非退步」。

### 3. task30批判② 真实 LLM 前缀 质量/成本 端到端 ✅(离线核算)

**做**：复用 `scripts/task30_results.json`（此前 `RUN_REAL_LLM=1` 真实 DeepSeek 生成前缀的被纳入证据），新增 `scripts/verify_task30_cost.py` 做质量+一次性/经常性成本端到端核算。**重要约束**：本次会话实时 LLM 接口返回 `HTTP 402 Insufficient Balance`，故不发起实时计费调用，一律离线核算并在字段标注。

**证据**（`scripts/task30_results.json` + `scripts/task30_cost_results.json`）：
- 质量：mode=real-LLM，contextualized=2，degraded=0，skipped=2（题库 q1 / 代码 code1 正确跳过 → filter `should_contextualize` 生效）；c1/c2 `raw_content_preserved=true`；Milvus 探针落库 `content`=前缀版、`raw_content`=原文、`content_is_prefixed=true`；降级路径 `content_unchanged=true` 且 `no_500=true`。
- 一次性成本（估算，reference 价 in¥2/1M / out¥8/1M）：每 chunk 输入 ≈247 token、输出前缀 ≈95 token，≈¥0.00125/chunk（量级）。
- 经常性成本：真实前缀 c1=63 / c2=125 字符，`content_growth_pct=193.8%`，含 `raw_content` 落库总存储 ≈+293.8%；前缀会**逐次放大每次检索 prompt 的 doc content**（经常性成本）。
- **批判承接关键点**：`CONTEXTUALIZE_ENABLED=False`（默认关闭），即该特性已实证可用但未在默认配置落地收益，需显式开启并接受 ~2-3× 存储 + 前缀生成成本。

### 4. task29批判③ 缓存命中和成本落地评估 ✅(复算一致)

**做**：因实时 LLM 现 402，采用「对既有真实结果做独立复算 + 官方计量接口复核」，新增 `scripts/eval/verify_task29_cache_cost.py`，不改、不伪造数据。

**证据**（`scripts/eval/task29_results.json` → `verify_task29_cache_cost.py` 输出）：
- 缓存命中：`independent_recalc hit=12288 miss=498 total=12786 hit_rate=0.9611(matches_persisted=true)`；`evaluate_hit_rate` 官方计量同值 0.9611，`evaluate_cache_sev` = OK（threshold 0.5）。**口径警示**：该 96% 是对 **>1600 token 生产规模大前缀**成立；task27 真实短请求前缀约 300 token < DeepSeek 缓存门槛 1024，**落地的短对话前缀缓存收益有限**（批判承接项）。
- 成本：逐档复算与持久化全一致；月度合计 ¥529.64 vs 预算 ¥300 → **超支 1.77×**（price in¥1/1M/out¥6/1M，daily 2000 queries 假设）。L1 是成本大头（¥370/月）。

### 5. task35 Neo4j 图谱重建 + retriever 图谱通道启用 ✅

**做（承接前会话完成项，本次独立实证确认）**：`scripts/kb_graph_rebuild_task35.py` 用原生 Cypher MERGE（规避 APOC 依赖）重建图谱；`app/chat/retriever.py` 图谱通道关键词改为「jieba 真实分词 + 词频」后直查 Neo4j。

**证据**（本次直接 probe `bolt://192.168.85.101:7687`）：
- 图规模：**NODES=2100，RELS=13132**；labels=`KnowledgePoint/CourseSeries/CourseModule/QuestionTag`；关系分布 `RELATED_TO=8357 / CONTAINS=4687 / TESTS=88`。
- retriever 通道端到端：`_graph_expand` 对真实 query（`数据结构/语法基础与开发环境/数据分析`）返回 7~12 个 GraphEntity + 1 跳 related，`degraded=None`（无熔断、无降级），证图谱通道连通且有效。

---

## 三、批判承接核对（把遗留批判逐条对号）

1. **VEC③ 需 ≥30 条跨语义类别评估集** → ✅ 已扩到 30 query/12 memory，rank@1=1.0。
2. **rerank 相对 15% 增益** → ✅ 已重测并解释：top-1 +533% 显著，top-20 饱和致目标口径不适用于当前召回上界；结论为「保留 rerank，价值在前排」。
3. **contextualize 真实 LLM 前缀质量/成本端到端** → ✅ 质量 0 降级、存储 +193.8% 量化；并新暴露「开关默认关」这一落地缺口。
4. **prompt cache 命中率 ≥80% 落地评估** → ✅ 96.11% 复算一致，但**标注了真实短前缀未过 1024 门槛的落地折损**，属批判发现项。
5. **Neo4j 断连熔断 + 图谱通道可用** → ✅ 图重建完成 + 通道实查无降级。

---

## 四、改动文件清单（后端源码 / 脚本）

- **后端源码（本批批判承接，前会话已改，本次实证验证）**：`edu-agent/app/chat/retriever.py`（图谱关键词 jieba 真实分词修复）。
- **本次新增脚本**（评估用，非业务代码）：
  - `edu-agent/scripts/verify_task30_cost.py`
  - `edu-agent/scripts/eval/verify_task29_cache_cost.py`
- **未改任何其它业务源码**；不顺手改无关代码。

---

## 五、资产消费证据

**实际读取的核心资产/代码**：
- `edu-agent/app/chat/retriever.py`（_graph_expand，第 265~355 行）、`edu-agent/app/knowledge/importer/contextualize.py`（Contextualizer/_default_llm_caller）、`edu-agent/app/config.py`（settings 开关与阈值）、`edu-agent/app/ai/compaction.py`（estimate_tokens）、`edu-agent/app/chat/generator.py`（_ChatClient.call_chat，确认非 200 不抛错）、`scripts/eval/{llm_client,run_task29,cache_meter}.py`。

**自检发现并修复的问题**：
1. `verify_task30_cost.py` 初次运行报缺 `content_type`（code1 chunk pydantic 校验）→ 补 `ContentType.DOC_CHUNK`。
2. `task30_results.json` 只持久化长度（content_len/raw_len）而非前缀正文 → 改为「长度差还原前缀字符数」核算，避免错误取空。
3. 实时 LLM 期间出现 `HTTP 402 Insufficient Balance` → 果断切换离线核算并在输出标注 `live_api_status`，不伪造 usage。
4. `verify_task29_cache_cost.py` 三处按持久化实际字段形状修正：`data/` 路径不存在→`eval/` 根；cache 对象无 `sev`/`prefix_tokens` 键→去掉；`eval/` cwd 下 .env 未加载→改从 project root 运行。
5. `call_chat` 非 200 不抛错 → 避免把「降级空回」误当「真实命中」，改为以持久化 real-LLM 结果为准。

**仍受环境约束项（诚实标注）**：实时 LLM 现 402，task30 前缀生成与 task29 压测/缓存计量的「本次实时调用」均不可行；本批采用「持久化真实结果 + 独立复算 + 官方计量复核」完成独立实证，未烧额度、未编造数字。待 API 余额恢复后可补一次实时端到端复跑。

- 报告路径：`test-reports/critique-RAG-batch-task32-task35-completion-report.md`
- 不 commit（等验收）。