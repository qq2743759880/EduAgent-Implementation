# task32 · RAG 召回评估集扩充 完工报告（VEC批判③ 落地）

- 任务：`task32（RAG 召回评估集扩充）` ｜ 优先级 P1 ｜ 状态：等验收（不 commit）
- 执行日期：2026-09-04
- 报告路径：`test-reports/task32-rag-eval-completion-report.md`

---

## 1. 资产消费证据段 + agent×skill×workflow 矩阵 + 逐批判记录

### 1.1 资产消费证据段（worker）

| 必调资产 | 路径 | 消费方式与产出 |
|---|---|---|
| ponytail | `C:\Users\Administrator\.agents\skills\ponytail` | 强制最简：复用既有 `MemoryVectorStore.search` + `SemanticEmbedder`（BGE-M3 封装），未新造检索框架；仅新增 1 个数据文件 + 1 个评测脚本；未引任何新依赖。遍历置顶"复用项目已有封装/不走底层 pymilvus"，全部命中第一档封装。 |
| tt §5.2 回传机制 | `C:\Users\Administrator\.agents\skills\tt\SKILL.md`（§5.2 回传机制 + §5.4 可验证边界 + §7 critique） | 完工报告只传文件路径引用、不复制内容（本报告引用 `scripts/eval/...` 文件路径）；独立实证不采信报告（真跑 BGE-M3 + Milvus，`degraded=None` 佐证未降级）；资产调用硬约束落账。 |
| review（critique 内核） | `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` | 交付前按 critique 交互态/边界/错误反馈三视角自检，见 §1.3；不假报外部评审内核（pr-agent/continue 均未接入，走内置自检）。 |

资产消费结论：三份必调资产均已消费；本任务未加载 tt 派单模板 `completion-report.md`、未调用任何 workflow/MCP。
assetConsumed=true（锚点：ponytail 封装复用 + tt 独立实证 + review 自检三内核词齐备）。

### 1.2 agent×skill×workflow 矩阵

| agent | skill | workflow | 作用 |
|---|---|---|---|
| task32 执行 agent（本进程） | `ponytail`（最简实现） | 复用项目既有 `MemoryVectorStore` 语义召回链 | 决定不新造检索/评测框架，只做"数据 + 一个评测脚本" |
| 同上 | `tt`（§5.2 回传 / §5.4 边界 / §7 批判，编排方法论） | 独立实证 → 完工报告 → 等验收 | 提供"真实契约为准、不 mock、如实报数"的验收纪律 |
| 同上 | `tt/vendor/review`（critique 自检） | critique 三视角自检 | 交付前自查并按发现修正 |
| workflow | 无（N=1 单平台退化模式：换子 agent/视角复验） | — | 无独立 workflow 文件被调用 |

### 1.3 逐批判记录（review critique 三视角自检）

1. **交互态（交互正确性）**：评测度量取 `rank@1 / recall@3 / MRR` 多档排序指标，query→expected_memory_id 一对一金标，杜绝"只报 hit@5 饱和自匹配"。发现并已修：初稿曾只算 rank@1，无法体现排序质量 → 补 recall@3+MRR。
2. **边界（鲁棒性/降级）**：真实 BGE-M3 可能降级；评测显式捕获 `store.degraded_reason`，`degraded=None` 证明确实走了真实 BGE-M3（CUDA 1024 维），未降级冒充。测试 user 结束后 `clear_user` 清理，不污染生产 `user_memory`。
3. **错误反馈（诚实性）**：未把"达标 0.9"当默认——先真跑出 `rank@1=1.0` 再下结论；哈希对比如实保留 1 条 rank@1 未命中（GOAL-06），不做抹平。

---

## 2. 现有评估集定位结果 → 扩充 → 产物

### 2.1 现有评估集定位（探索性结论，非凭空发明）

项目里其实存在**两套**召回相关评估基建，初看与"5 条"吻合点是第二套：

- **① 记忆召回评估（5 条金标 —— VEC③ 指控的"样本不足"）**
  - 出处：`edu-agent/scripts/task_vec_results.json`（5 条记忆 query：计算机视觉识别方法 / 出差交通安排 / 英语能力提升 / 机器学习模型 / 下周旅行计划；BGE rank@1=1.0）。
  - 配套契约测试：`edu-agent/tests/test_contract_task_vec.py`（内联约 5 条，`MemoryVectorStore` + `SemanticEmbedder` 真 BGE-M3 + Milvus 集成）。
  - VEC③（`.opencode/plans/critique-backlog-tracker.md`）："记忆召回指标样本不足（仅 5 条）→ 在 `scripts/eval/eval_dataset.py` 扩充记忆召回评估集至 ≥30 条（偏好/进度/错误/目标），复用 `MemoryVectorStore.search` 跑 BGE-M3 vs 哈希，rank@1≥0.9"。

- **② RAG 知识库离线评估（100 条，task32 既有产物，属"另一起源的旧评估集"）**
  - `edu-agent/scripts/eval/data/task32_eval_set.json`（100 条，由 `build_eval_set32.py` 构造），`verify_task32.py` 跑 hit@k/MRR 与 BGE-rerank A/B。
  - 解释：其 GT 为"抽取题干所在的出题 chunk 自身"（自匹配去重口径），原始 RRF hit@1 仅 0.06，需重排后 hit@1=0.38——**不是** VEC③ 所指的"记忆召回评估集"，二者口径不同。

**结论**：任务正文"RAG 真实召回 / 复用 retriever 或 loader"与 tracker 的"记忆召回评估集 5→≥30"所指一致——因为三层记忆召回与 RAG 知识库召回共用同一条 **Milvus + BGE-M3 语义检索栈**（`MemoryVectorStore.search` 内部经 `loader.get_milvus_client()` 唯一入口）。故本任务按 VEC③ 权威口径（记忆召回评估集）扩充与实证，同时保留对既有 RAG 离线评估集（100 条）的定位说明。

### 2.2 扩充结果

- 从 **5 条** → **30 条**金标 query（`__init__` 无；纯数据文件）。
- 语义类别覆盖：偏好(preference)=8、进度(progress)=7、错误(error)=7、目标(goal)=8。
- 记忆池 12 条（`memory_id` 900001–900012，跨四类别）；query 为对对应记忆的**自然改写**（问句/同义转述），非原文复制，故测语义召回而非字面命中。
- 产物：
  - 数据：`edu-agent/scripts/eval/data/task32_memory_recall_set.json`
  - 评测：`edu-agent/scripts/eval/eval_task32_memory_recall.py`
  - 结果：`edu-agent/scripts/eval/data/task32_memory_recall_result.json`

---

## 3. 独立实证（真实 BGE-M3 + Milvus，不 mock）

执行：`edu-agent/.venv\Scripts\python.exe scripts\eval\eval_task32_memory_recall.py`
环境实证：`torch.cuda.is_available=True`（RTX 4060），BGE-M3 本地 `C:/ai-models/bge-m3` 已加载，`EMBEDDING_DIM=1024`；Milvus `http://192.168.85.101:19530` collection `user_memory` 可达，`edu_knowledge` 也真实可达（2647 行）。

### 3.1 真实 BGE-M3（Milvus 后端，MemoryVectorStore 默认）

| 指标 | 数值 | 0.9 目标 |
|---|---|---|
| **rank@1（hit@1）** | **1.0**（30/30） | ✅ ≥0.9 |
| recall@3 | 1.0（30/30） | — |
| MRR | 1.0 | — |
| 降级标注 `degraded_reason` | None（确认真实 BGE，未降级冒充） | — |
| 逐条明细 | 30/30 全部 top1 == expected_memory_id（结果 JSON `bge_milvus.detail`，零 miss） | — |

### 3.2 对比：确定性哈希 embedder（in-memory 后端）

| 指标 | HASH | BGE-M3 | 差（BGE−HASH） |
|---|---|---|---|
| rank@1 | 0.9667（29/30） | 1.0 | **+0.0333** |
| recall@3 | 1.0 | 1.0 | 0.0 |
| MRR | 0.9833 | 1.0 | +0.0167 |

哈希唯一 miss：`GOAL-06`（"独立做前端项目是我多久内的目标" → expected 900012；top1 误为 900010），2-gram 字面近似混淆"目标"表述。真实 BGE-M3 该条命中 → 语义召回确优于字面召回，VEC③"对比报告含两种 embedder 的 recall 差"已产出。

### 3.3 达标结论

**评分集已 ≥30 条、真实 BGE-M3 rank@1 = 1.0（≥0.9），彻底达标，无需改进产品召回。** 记忆中既有 5 条评估集可通过本 30 条集完全接管。

---

## 4. 若 <0.9 的改进建议（本任务达标，仅存档备查）

达标，故不强行改产品。若未来评估集覆盖到更高混淆度（同目标多语义前缀、近义记忆成对），如需保持 rank@1≥0.9，建议按优先级（当前**不触发**）：
1. 稀疏/稠密融合阈值（`hybrid_search` RRF k）校准；
2. 候选重排 `_rerank_docs`（BGE-reranker）在记忆召回链的复用；
3. 记忆侧 `context_prefix` 前缀扩写（与知识库同款 task30 contextualize 手法）。
结论：以上均标"暂不改产品"，避免过度工程化。

---

## 5. 环境 gap（如实登记）

- 无阻断性 gap。Milvus、BGE-M3(CUDA) 均真实可达。
- 本地 Redis 未初始化 → `MemoryVectorStore` 哈希对比走 in-memory 后端（`redis_unreachable` 仅出现在哈希 pass，非 BGE 主链路；BGE 主链为 Milvus 后端，`degraded=None`）。对评测结论无影响。
- 评测使用独立 user（66661/66662），结束后 `clear_user`，未污染生产 `user_memory`。

---

## 6. 边界核对

- 未新建独立评估域、未引新评估框架/依赖（复用 `MemoryVectorStore` + `SemanticEmbedder`）。
- 未直接 `pymilvus`：全部经 `MemoryVectorStore.search/upsert` → `loader.get_milvus_client()` 唯一入口。
- 未调 LLM（BGE-M3 本地 GPU，零 DeepSeek 费用）。
- 不 commit（等待验收）。