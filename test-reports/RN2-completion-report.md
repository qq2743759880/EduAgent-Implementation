# R-N2 完成报告（KG-3 GraphRAG 第四通道 graph_expand）

- 任务：C-01 派单 R-N2（`feature/opt-waves`，planId=reshape-r-kg §KG-3；前置 R-N1 已验收：kg_sync 子图 4292 节点/7900 关系在线、50301 降级范式就绪）
- 完成日期：2026-09-19 凌晨
- 最终 commit：**`4c19a3f`**（feat(kg)/R-N2，主体实现单 commit；双跑对账实测基点 = 工作树（父 commit `8f5b527`）+ 本批全部改动，其后 tip 前移的 `41f2c6d`/`3320b46`（W-NEXT-R-MEM-001，app/ai/memory 域）不触碰检索路径，对账数字对最终 commit 仍有效）

## 1. 交付物（文件归属对齐派单红线）

| 文件 | 类型 | 内容 |
|---|---|---|
| `edu-agent/app/ai/kg_bridge.py` | **新增**（207 行） | Neo4j 查询桥：两段纯 MATCH Cypher（①种子实体面：chunk MENTIONS 的 KP ∪ 所属 Chapter MENTIONS 的 KP；②实体图 RELATED\|PREREQUISITE 1..HOPS 跳 → 反向 MENTIONS 邻居 DocChunk）；全部 `source='kg_sync'` 作用域（免疫 P1 遗留数据）；只读红线（无 MERGE/CREATE/SET/DELETE，测试断言自证）；恒不抛异常，降级原因枚举：`empty_seeds` / `neo4j_not_connected` / `timeout(≤800ms)` / `neo4j_breaker_open` / `{异常名}`；`rrf_channel_score = weight/(k+rank)`（与 Milvus RRFRanker(k=60) 同范式，weight 配置化） |
| `edu-agent/app/chat/retriever.py` | 修改（+83/−3） | 最小 diff：① `_milvus_fetch_contents`（邻居 chunk 的 Milvus 正文回填，失败回退 bridge preview 兜底，12 行）；② 融合去重后插入 4b 段——`KG_EXPAND_ENABLED` 开启且候选非空时取前 `KG_EXPAND_SEED_TOPK` 个 doc_id 为种子 → bridge 查邻居 → RRF 分（(raw+1)/2 与 Milvus 通道同款归一）并入候选池一起 rerank 公平竞争；已在候选中的邻居跳过不重复不计 rank；③ profile 行加 `kg_expand` 段；④ degrade 组件表加 `("kg_expand", kg_degrade)`。**契约零变更**：`RetrievedDoc.source_channel` Literal 冻结不动，新邻居复用 `"graph"` 溯源标签（通道3=实体渲染、通道4=chunk 扩展共用 graph 语义） |
| `edu-agent/app/config.py` | 修改（+17） | `KG_EXPAND_ENABLED=False`（灰度位，默认关）+ `SEED_TOPK=10` / `HOPS=2` / `TIMEOUT_MS=800` / `MAX_NEIGHBORS=30` / `RRF_K=60` / `RRF_WEIGHT=0.5`，注释含通道语义与降级承诺 |
| `edu-agent/tests/test_rn2_kg_expand.py` | **新增**（22 用例） | 见 §4 |
| `edu-agent/scripts/eval/rn2_dualrun_probe.py` | **新增** | 双跑对账探针（复用 R20-min 测量仪口径 + `_match_golden` golden 双键解析） |
| `edu-agent/scripts/eval/rn2_degrade_probe.py` | **新增** | Neo4j 黑洞降级实测探针 |
| `edu-agent/scripts/eval/data/rn2_runs/rn2-dualrun-{summary,results}.json` | 产物 | 双跑逐条明细 + 汇总指标（对账证据） |
| `test-reports/RN2-completion-report.md` | 报告 | 本文件 |

**graph.py hook 申报：无**——`app/domains/kg/graph.py` 零 diff（diff ≤3 行豁免通道未动用）。**禁碰清单核对**：app/domains/kg/**（只 import 零改动）、embedding 相关配置（未碰，EMBED_BACKEND=cuda 全程未动）、langgraph_agent.py（未碰）。通道经 `retrieve_three_channel` 内 config 开关生效，所有调用方（旧编排 flows / 六节点图 fan_out）自动继承，无新增用户端点。

## 2. 通道语义（为何当前「零增益」是正确结果）

```
top-k 融合候选 chunk ──MENTIONS──▶ KnowledgePoint（实体面）
        └─BELONGS_TO─▶ Chapter ──MENTIONS──▶ KnowledgePoint（所属章节实体面）
                                        │
              RELATED | PREREQUISITE（无向 1..2 跳，实体图邻域）
                                        ▼
              邻居 KP ◀──MENTIONS── 邻居 DocChunk（排除种子）→ RRF 并入候选池
```

当前真实库（2026-09-19 实测）：kg_sync 子图 `rel:MENTIONS=0`、`rel:RELATED=0`（R-N1 报告与 contracts/reshape-r-kg.json draft 的 known_data_limits 已披露）→ 实体面为空 → 扩展查询结构性返回 0 邻居 → **通道产出 0 增益，双跑「零分歧零增益」＝预期正确结果，如实登记（禁造假增益）**。通道真正的价值在数据增强（LLM 批量抽取 MENTIONS/RELATED 落库）后灰度开启：届时邻居经 rerank 与既有候选公平竞争，hit_rate 只会因候选池扩容而受益或持平（A/B 断言门在双跑探针里）。

## 3. 双跑对账（硬门，R20-b 双跑探针范式）

- 口径：冻结评估集 `rag_eval_set32.json` 全量 32 条（不重 build）；每 query 走 `retrieve_three_channel` 实时端到端全链（Milvus hybrid 召回 150 → sidecar rerank 20 → 断崖截断 → final top5）；golden 双键解析复用 R20-min `_match_golden`（chunk_id → id_map → doc_sha256）；同进程先 off 后 on，跑前 GPU/sidecar warmup 循环至无 Milvus 超时（首跑冒烟实测教训：冷 BGE-M3 encode ~13s > Milvus 8s 预算会造 off 轮假性空 docs——已在探针内置 warmup 修复）。
- 参数：`use_hyde=False, top_k=5, final_max_k=5, cutoff_drop_ratio=0.40, enable_graph=True`（=R20-min 基线 PARAMS）；on 轮 `KG_EXPAND_ENABLED=True`。

| 指标 | off（基线） | on（第四通道） | 门 |
|---|---|---|---|
| **intent 分歧率** | — | **0/32 = 0.0%** | 通道在决策后、重排前，intent 结构性不受影响 ✓ |
| **docs 分歧率**（final top5 逐条不一致占比） | — | **0/32 = 0.0%** | MENTIONS/RELATED=0 → 0 邻居并入 → off==on 逐位一致 ✓ |
| **hit_rate@5** | **0.9688**（31/32） | **0.9688**（31/32） | **对 R20 冻结基线 0.9688 delta=0.0，零退化** ✓ |
| **mrr@5** | 0.9688 | 0.9688 | delta=0.0 ✓ |
| 结论 | — | **「零分歧零增益」** | 如实登记 ✓ |

- 证据文件：`scripts/eval/data/rn2_runs/rn2-dualrun-summary.json`（git_rev=8f5b527、32 对 pairs、双跑各 32 条 per-query 明细）、`rn2-dualrun-results.json`（44KB）。
- 复跑：`cd edu-agent && .venv/Scripts/python.exe scripts/eval/rn2_dualrun_probe.py`（需 Milvus 192.168.85.101:19530 + Neo4j 192.168.85.101:7687 + rerank sidecar 8601 在线；本轮 sidecar 由本 agent 拉起，GPU 布局=BGE-M3 探针进程 2.3G + sidecar 1.1G，R03 验收同款）。

## 4. 测试（22/22 全绿 + 爆炸半径 142 全绿）

`tests/test_rn2_kg_expand.py`（对齐派单验收 4 类）：
- **通道单元（mock kg 返回邻居→融合排序正确）**：邻居 RRF 并入（rank1 分数 > rank2、与 RRFRanker 范式逐位对齐 `0.5/(60+rank)`→`(x+1)/2`）、重复邻居去重不计 rank、Milvus 正文回填优先/preview 兜底/双缺为空、`raw_retrieved_count` 计入、`degraded_reason=None`
- **kg 超时→跳过**：通道超时降级时主链 docs 与开关关闭**逐位一致** + degraded_reason 留痕 `kg_expand:timeout`；通道开启但 0 邻居 → off==on 逐位一致（零分歧的结构保证）
- **开关 off→零开销**：默认 False 下 kg_bridge/Milvus 回填零触达（断言注入即炸）；候选为空时即使开启也不触达
- **bridge 封装**：stub driver 确定性排序 `(hops, chunk_id)`、跳数字面量/LIMIT 插值、空实体短路不跑扩展查询、800ms 预算硬顶（含**同步 driver 懒初始化挂起也在预算内放弃**的回归防线——P1-4 同类教训，driver init 已置于线程内）、熔断快速失败、异常全吞、preview 映射
- **配置默认值**：灰度位 False + 6 参数
- **真集成（skipif 隔离，只读红线）**：真实 Neo4j 取 5 个 DocChunk 种子 → `fetch_neighbor_chunks` 返回 0 邻居（=零增益预期）；两段 Cypher 无写子句断言

回归：
- 本批 22 用例：**22 passed**（`pytest tests/test_rn2_kg_expand.py`）
- 爆炸半径套件（retriever 三通道消费方/影子模式/R02 profile/Neo4j 熔断/R-N1 KG/agent loop/P1L/perf guard）：**142 passed**（`pytest tests/test_rn2_kg_expand.py tests/test_contract_task_e1.py tests/test_contract_task_r02.py tests/test_contract_task_r02tail.py tests/test_breaker_db_resilience.py tests/test_kg_rn1.py tests/test_agent_loop.py tests/test_contract_taskP1L.py tests/test_perf_guard.py`）
- 全量套件：1564 passed / 71 failed / 75 skipped。**71 失败非本批引入（A/B 实证）**：全部为打共享活体后端（127.0.0.1:8000）的 HTTP 契约用例（task15/16/20/21/22/113/middleware/mcp_health/all_routers/review/rm1_analytics），失败形态 `assert 429 == 200/401`＝task39 真 Redis 限流器被全量套件数百请求打热后的**窗口状态残留**；同刻 A/B——`git stash`（本批改动出栈）复跑同批文件仍 5 failed 同形态（rate limit/middleware），恢复改动后同批文件重跑 task15 单文件 20/20 passed、middleware 限流用例仍受窗口残留影响。爆炸半径（无 HTTP 依赖）142 全绿为本批无回归的直接证据。

## 5. 降级实测（黑洞探针，对齐 50301 范式＝检索路径降级跳过而非报错）

`NEO4J_URI_BLACKHOLE=1 scripts/eval/rn2_degrade_probe.py`（NEO4J_URI 注入 TEST-NET-1 黑洞 10.255.255.1:7687，SYN 无响应，KG_EXPAND_ENABLED=True）：

```
on q0: total=2368.0ms docs=5 kg_reason=kg_expand:timeout(0.8s)   ← 黑洞连接挂起被 800ms 预算硬顶
on q1: total=1939.7ms docs=5 kg_reason=kg_expand:timeout(0.8s)
on q2: total=1788.7ms docs=5 kg_reason=kg_expand:timeout(0.8s)
on q3: total=1032.6ms docs=5 kg_reason=kg_expand:neo4j_not_connected ← driver init_failed 自愈→毫秒级
on q4: total=1236.8ms docs=5 kg_reason=kg_expand:neo4j_not_connected
off q0: total=1287.1ms docs=5 kg_reason=None
off q1: total=1175.5ms docs=5 kg_reason=None
断言: 主链有docs=True 通道留痕=True 降级原因受控=True 通道开销(on最大-off最大)=1080.9ms ≤1200ms=True
PASS — Neo4j 断连下通道静默跳过，主链无感
```

要点：①主链全程 docs=5 正常返回（Milvus/rerank 无感）；②降级阶梯符合设计——3×超时预算封顶 → driver 懒初始化失败自愈标记 → 毫秒级 not_connected 快断；③最坏单查开销 1080.9ms（≈800ms 预算+调度抖动），稳态≈0；④degraded_reason 全程留痕并进 `metrics.record_degraded("kg_expand", ...)` 埋点。

## 6. 资产消费证据（具名路径）

| 资产 | 消费方式 |
|---|---|
| `.ai-hub/plans/neo4j-mongo-activation-plan.md` §KG-3 | 通道定义（top-k chunk→MENTIONS 实体→2-hop 邻居 chunk）、开关+双跑对账范式、hit_rate 不降为门——逐条落地于 §2/§3 |
| `app/domains/kg/sync_core.py`（R-N1） | 建模消费方：`source='kg_sync'` 作用域、DocChunk{chunk_id,preview}、MENTIONS/BELONGS_TO/RELATED/PREREQUISITE 语义——bridge Cypher 按其写入模式查询 |
| `app/core/db_resilience.py`（task-P1C） | `neo4j_run` 熔断 + `DependencyUnavailableError` 直接复用（bridge 不另造轮子） |
| `app/knowledge/importer/loader.py` RRFRanker(k=60) | RRF 范式同源：`weight/(k+rank)` + (x+1)/2 归一，k=60 配置默认对齐 |
| `scripts/eval/r20min_run.py` | 测量仪口径复用：`PARAMS`/`EVAL_SET_PATH`/`TOP_K_EVAL`/`_match_golden` 直接 import（零复制漂移） |
| `scripts/eval/r20b_dualrun_probe.py` | 双跑探针范式（同批对照/逐条 pairs/汇总门槛）复刻到开关维度 |
| AGENTS.md 关键教训 #2（禁 Playwright/独立实证）、#8（契约以实测为准） | 双跑+黑洞探针均为真实 HTTP-等价全链实测；两处冒烟实测纠偏已回写探针（warmup 修复、source_channel Literal 契约冻结） |

## 7. P0 自批判（≥3，诚实登记）

1. **【P0】「800ms 预算」在初版实现有两处漏判，均由测试/探针实测暴露后修复**——①Cypher 模板 `.format()` 撞上 Cypher map 字面量 `{source: $src}` → KeyError，且真实 Neo4j 只读集成用例捕获（首版所有真查询全部降级为 `kg_expand:KeyError`，若只看单测 mock 会全绿漏过——「mock 全绿 ≠ 真链可用」的又一次实证）；②`get_neo4j_driver()` 懒初始化是同步阻塞调用且初版留在协程内，死 Neo4j 场景下首查会阻塞事件循环 ~3s（NEO4J_CONNECT_TIMEOUT）**在 wait_for 预算之外**——黑洞探针第一版实测后重构为 driver init 进线程 + 外层单点 wait_for 硬顶，并加回归用例。残余风险：被 wait_for 放弃的后台线程仍在等 TCP（Windows 最长 ~21s），并发风暴下可能积压线程，但 breaker（5 次连续失败开路）会收敛；未做线程池上限隔离（工程上量级可忽略，灰度开启前建议编排者复审）。
2. **【P0】双跑对账的 warmup 依赖是范式级隐患**：首跑冒烟 off 轮 2/3 query 假性「Milvus 检索超时(8.0s)」（冷 BGE-M3 encode 13s>8s 预算）→ 差点把「预热伪影」登记成「第四通道分歧」（假分歧/假增益双向都可能）。已在探针内置 warmup-循环至热修复；但这说明**共享 GPU/共享后端上的对账数字必须先证明环境同温**，R20-b 范式复用时若不带 warmup，off/on 顺序先后本身就能造出分歧。另：本轮对账 off==on 逐位一致部分依赖「0 邻居不进池」的结构保证，当 MENTIONS 数据落库后该保证失效，届时 on 轮 rerank 候选池变大（150→180）会引入 rerank 批次形状变化——**真实增益/分歧要求数据增强后重跑双跑，本报告数字不外推**。
3. **【P0】全量 pytest 71 failed 的归因依赖 A/B 而非全量基线**：本批改动下全量套件 1564P/71F；`git stash` A/B 证明失败文件在同刻无本批改动下同样失败（429 限流窗口残留，共享活体后端 + 真 Redis 限流器），且爆炸半径 142 全绿——但**未做全量 stash 基线重跑**（6 分钟/次 + 会再次打热限流窗口，A/B 单文件证据更干净），严格说「71 失败全部非本批引入」是强证据推断而非穷举证明。建议编排者窗口：套件前清限流键或 `TEST_BASE` 指向独立实例。
4. **【P1】`_milvus_fetch_contents` 的 Milvus filter 是 `chunk_id in [...]` 逐条 JSON 拼串**，`KG_EXPAND_MAX_NEIGHBORS=30` 上限内安全；若未来把上限调到千级，filter 长度和查询延迟需要重新评估（当前有 30 上限护栏 + 失败全吞降级，不构成主链风险）。
5. **【P1】`source_channel="graph"` 复用是 Literal 冻结下的务实选择，但牺牲了通道 3/4 的溯源区分度**（graph_entities 渲染 vs chunk 扩展无法从 doc 上直接区分，只能靠分数公式/comments）。契约变更单开新 Literal 值才是长期正解——本批按「无契约变更」红线执行，留此存照。

## 8. 批判承接核对

**无承接项**——kickoff 明确「批判承接核对（无承接项）」；本批为 R-N 系列首批执行批，未继承任何前任未闭环项。R-N1 报告中的 known_data_limits（mentions=0/related=0）已作为本批对账预期消费并闭环（§2/§3）；其「Neo4j 写仅限 scripts/kg_sync.py」红线在本批延续（bridge 纯只读 + 测试断言）。

## 9. 环境副作用声明（验后清理）

- rerank sidecar（uvicorn 8601，本 agent 为双跑拉起）：报告归档后停止，环境恢复原状（验后已停）
- `scripts/eval/rn2.lock`：commit 前删除（红线）
- Neo4j/Milvus/MySQL 全程只读；未写任何图谱数据

## 10. 复跑命令汇总

```bash
cd edu-agent
# 单元 + 真集成（Neo4j 在线时自动含只读用例）
.venv/Scripts/python.exe -m pytest tests/test_rn2_kg_expand.py -v
# 双跑对账（需 Milvus/Neo4j/sidecar 8601；--limit 3 冒烟）
.venv/Scripts/python.exe scripts/eval/rn2_dualrun_probe.py
# 黑洞降级实测
NEO4J_URI_BLACKHOLE=1 .venv/Scripts/python.exe scripts/eval/rn2_degrade_probe.py
```
