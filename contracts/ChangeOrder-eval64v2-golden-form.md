# 变更单：eval64 golden 形态重铸（V1 路由卡 → V2 内容块）

- **编号**：CO-EVAL64V2-001
- **状态**：已批准（用户 2026-09-19，见 kickoff-EVAL64V2-golden-reform.md；本文为其正文落档）
- **执行**：W-NEXT-EVAL64V2-001（yy 串行流水线）
- **依据实测**：R24（commits 82d046d / 5594b96 / 0f42b4e，探针产物 `edu-agent/scripts/eval/data/r24_runs/`）

---

## 1. 动机（R24 三证据）

### 证据一：golden 形态错配——89% 的 golden 是路由卡，不是内容

现行 eval64（`data/r22_eval_set64.json`，64 条）的 golden 分布实测（2026-09-19 Milvus 直查）：

| V1 golden content_type | 条数 | 占比 |
|---|---|---|
| course_module（模块路由卡） | 57 | 89.06% |
| doc_chunk（内容块，仅 manual 一条） | 1 | 1.56% |

course_module 块的形态是「课程模块：标题 / 模块编码 / 关键词行」元数据卡（约 5 行），不含任何题面或答案内容。而查询面 63/64 为题库 question 题干——**检索目标（路由卡）与用户意图（找到含答案的内容）错位**，测的是"路由能力"而非"内容寻回能力"。

### 证据二：worst-10 全部 recall miss，且 rerank top1 = 语料中逐字原题块（score=1.0，含答案）

`r24_worst10_probe64.json`：V1 尺最差 10 条全部 miss。本次执行逐条复核（2026-09-19）：

- 10/10 的 rerank **top1**（score=1.0）是语料中**逐字含问句的 question 块**（含选项/答案/解析），且该块 chunk_id 与该样本在 V1 集中的 `source_chunk_id`（题干提取来源）**逐一相同**；
- 该逐字原题块正是"用户问这个问题时应被找回的内容块"——它不在 golden 位置，golden 却是一张路由卡。

### 证据三：现行尺天花板仅 7.8%，且已排除 rerank 主因

`r24_rank_probe_probe64.json`：golden（路由卡）在 rerank 全序 top5 内仅 5/64（ceiling_hit@5=0.0781）；召回层覆盖 49/64=76.6%（median rank 34）；窗口 20→50 扩窗零变动、hyde 0/39 变动、rank 全序净提升 30:18 非主瓶颈（R24 结论：**真瓶颈=golden 形态+召回侧**）。形态不改，任何 rerank 侧优化都无法把尺子数字拉起来。

---

## 2. 变更内容

### 2.1 golden 主目标改为内容块（content_block）

**新定义**：golden 主目标 = **逐字含问句，或直接回答该问句的内容块（chunk）**。

- **逐字含问句**（首选）：normalized(query) 是 chunk content 的子串。R24 实证语料中存在原题块（worst-10 的 top1），Milvus 直查原题文本可达（本次实测 63/64 cross 样本可直接定位，其中 62 条唯一命中、1 条 33 个重复块）。
- **直接回答该问句**：manual 样本沿用 V1 golden（同会话 assistant 实际投喂的生产 chunk，`resolve_via=production_cited`，sha 对当前库复核）。
- **模块卡降级**：course_module 卡不再作为 golden 主目标；module-level hit（V1 golden 块是否进 final docs）降为**次级指标**随 V2 测量一并产出，不再参与门禁主尺。
- **unresolved 规则**：按新规则重解析后仍无法定位内容块的样本，如实标注 `golden_type=unresolved`，**排除出主尺（不凑数）**，数量与明细入报告。

### 2.2 溯源与纪律（不变量）

- 每条样本必带 `golden_type ∈ {content_block, module_card}`（unresolved 仅存在于 meta 侧账）；
- **independence 溯源保留**：manual/cross 字段、source_chunk_id / source_bank / series_code / source_message_id / cited_rank 等全部继承 V1；
- **禁从目标块循环提取**：V2 重建**冻结复用 V1 的 query 面**（逐字继承，不做任何再提取/再改写）；build 过程不从 golden 块生成新 query。V1 cross 样本的 query 本提取自其 source question 块，V2 golden 落回该块时，此「query 源 = golden 块」事实**显式声明**（`golden_is_query_source=true`）而非隐藏，其测量含义（子串保底偏乐观）在报告 P0 自批判中如实评估；
- golden 双键（chunk_id + doc_sha256=sha256(gt_content utf-8)）不变；query 长度界不变；
- module_card 保留路径（当内容块不可达而路由卡可达时）沿用 V1 全部反圆环校验（golden≠source、query 非子串、matched_terms 必填）。

### 2.3 类型分布断言（R22 反哺）

建集器 V2 模式新增硬断言：**content_block 占比 ≥60%，否则 builder 报错退出**（R22 批判承接：建集器此前缺类型分布检查，形态劣化只能靠事后审计发现）。unresolved 不计入分母但单独披露。

### 2.4 交付物

| 交付物 | 路径 | 性质 |
|---|---|---|
| 变更单（本文） | `contracts/ChangeOrder-eval64v2-golden-form.md` | 新增 |
| V2 评估集 | `edu-agent/scripts/eval/data/r64v2_eval_set64.json` | 新增 |
| V2 测量产物 | `edu-agent/scripts/eval/data/r64v2_runs/*.json` | 新增 |
| V2 基线契约 | `contracts/rag-baseline-eval64-v2.json` | 新增（draft:false） |
| 建集器 V2 模式 | `edu-agent/scripts/eval/build_eval_set64.py` | 原地增能（V1 行为零改动） |
| V2 单测 | `edu-agent/tests/test_build_eval_set64.py` | 追加 |

---

## 3. 双尺口径

- **主尺**：eval64-v2（内容块 golden）——RAG 门禁独立尺，口径仍为实时端到端 retrieve_three_channel 全链（召回150→rerank20→断崖→top5）在 final docs 上算 hit_rate@5 / mrr@5，0-LLM，禁在冻结 candidates 上算指标。
- **对照尺**：旧 eval64（路由卡 golden，`contracts/rag-baseline-eval64.json`）**零改动保留**，继续作路由能力对照与历史代际锚点。
- **两尺并行、禁互相换算**：数字差（「形态错配税」）只作对照披露，不互相推导阈值。
- 新基线冻结为 **pre-fix 现产线实况**（RERANK_CLIFF_V2 on），**无目标预设**；阈值沿用「基线-0.02」持续回归下限公式。

## 4. 回滚方式

- 本变更全部交付物为新增文件 + `build_eval_set64.py` 增量分支（V1 模式代码路径零改动）+ 单测追加；旧契约 `contracts/rag-baseline-eval64.json` 与旧评估集 `data/r22_eval_set64.json` 逐字节不动（git diff 自证）。
- 回滚 = revert 本次 commit：门禁切回 `contracts/rag-baseline-eval64.json`（r23 尺），删除 V2 集/runs/契约即可，无需数据迁移；两尺本就并行，回滚不影响旧尺连续性。

## 5. 验收断言（供 C-01 编排者逐条实证）

1. 旧契约与旧评估集 git diff 为空；
2. V2 集 64 条：golden_type 分布如实（实测预期 content_block=64，含 1 条 production_cited manual），断言 ≥60% 生效（单测覆盖失败路径）;
3. V2 golden 双键 sha 与 gt_content 逐条一致；逐字形态样本 norm(query) ⊆ norm(gt_content) 抽验；
4. worst-10 的 V2 golden 与 `r24_worst10_probe64.json` top1 块 10/10 对齐；
5. V1 模式回归：`tests/test_build_eval_set64.py` 全量通过，V1 集文件 sha 不变；
6. 新契约 draft:false，基线数字与 run 产物逐位一致，双跑 determinism 逐位一致。
