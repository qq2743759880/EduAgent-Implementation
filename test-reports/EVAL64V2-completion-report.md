# W-NEXT-EVAL64V2-001 完工报告：eval64-v2 golden 形态重铸（变更单 CO-EVAL64V2-001 执行收口）

> 执行 agent：yy 串行流水线在岗 agent。开工单 `.ai-hub/plans/artifacts/kickoff-EVAL64V2-golden-reform.md`（用户 2026-09-19 批准变更）。
> 基线 tip：`8d33ced`（feature/opt-waves；三跑实测 git_rev 均为 `8d33ced46c00a8bc06a6761f70fe74150ccfaffb`）。单写者锁 `edu-agent/scripts/eval/reval64v2.lock` 已随完工删除。
> 主提交 hash 补记：本报告随主提交入库，hash 由紧随的补记 commit 回填下节（仓库惯例，先例 `5594b96` 补记 `82d046d`）。

## 0. 主提交 hash（补记）

**`b04e32d`**（eval(r64v2)/W-NEXT-EVAL64V2-001 收口主提交，feature/opt-waves，父 `8d33ced`）

## 0b. 交付概览

| 项 | 内容 |
|---|---|
| 主提交 | （本文件随主提交入库，hash 补记于下节） |
| 变更单 | `contracts/ChangeOrder-eval64v2-golden-form.md`（正文落档，用户已批准注明） |
| 新契约 | `contracts/rag-baseline-eval64-v2.json`（draft:false，sha256 算法=仓库 sha256_utf8 同源；eval_set 文件级 sha256=877d5d9c06692c1e…） |
| V2 评估集 | `edu-agent/scripts/eval/data/r64v2_eval_set64.json`（64 条，v1_idx 与 V1 文件序对齐） |
| V2 测量产物 | `data/r64v2_runs/r64v2_base_run{1,2}.json`（双跑，随 commit 入库）；V1 对照 `data/r22_runs/r64v1_ctrl_run1.json` |
| 建集器 | `edu-agent/scripts/eval/build_eval_set64.py` 增 `buildv2`/`measure --set`/`freezev2`；**V1 既有行为零改动**（build/position/spotcheck/recallprobe 原路径不动，V1 单测 25/25 原样通过） |
| 单测 | `tests/test_build_eval_set64.py` 47/47 通过（V1 回归 25 + V2 新增 22，全离线） |
| 红线自检 | `contracts/rag-baseline-eval64.json` 与 `data/r22_eval_set64.json` git diff 为空；retriever/app/**、config.py、kg_bridge、trade/** 零改动 |

## 1. 变更单要点（§详文见变更单本体）

- **动机（R24 三证据，本次全部独立复核）**：
  1. V1 golden 89%（57/64）为 course_module 路由卡——本任务用 Milvus 直查复核 `57 course_module + 1 doc_chunk`，与开工单数字一致；
  2. worst-10 全部 miss 且 rerank top1=逐字原题块（score=1.0 含答案）——本任务逐条比对 `r24_worst10_probe64.json` 的 rerank_top5[0] 与 V1 集 source_chunk_id，**10/10 对齐**；
  3. V1 尺天花板 7.8%（golden_in_rerank_top5=5/64），扩窗/hyde/权重三臂均不达标——R24 判定真瓶颈=golden 形态+召回侧。
- **变更内容**：golden 主目标=内容块（逐字含问句或直接回答该问句的 chunk）；module 卡降为 module-level hit 次级指标；`golden_type` 溯源必填；unresolved 排除主尺不凑数。
- **双尺口径**：eval64-v2 主尺 + 旧 eval64 零改动保留对照，两尺并行禁互相换算。
- **回滚**：revert 本 commit 即回 r23 尺，无数据迁移（详见变更单 §4）。

## 2. 类型分布数字（建集器 V2 模式实测）

| 指标 | 数字 |
|---|---|
| 输入（V1 冻结集） | 64 条 |
| **content_block（verbatim 逐字）** | **63**（63 条 cross 全部命中其 source 原题块：62 条唯一命中 + idx31 在 33 个逐字重复块中按「source 优先」规则命中；golden_is_query_source=true 共 63 条） |
| **content_block（production_cited）** | **1**（idx37 manual：V1 生产投喂 doc_chunk，当前 Milvus sha 复核一致） |
| module_card 兜底 | 0 |
| unresolved | **0**（开工单预置的 15 条 recall-miss 样本按新规则**全部成功重解析**——其逐字原题块均在语料中，Milvus 直查可达；无需排除出主尺） |
| content_block 占比 | **100%**（断言阈值 ≥60%，`assert_type_distribution` 硬门） |
| 逐字验证 | 63/63 verbatim 样本 norm(query) ⊆ norm(gt_content)（独立复核，非采信 builder 回执） |
| 双键校验 | 64/64 doc_sha256 == sha256(gt_content utf-8) |
| 重复块特例 | idx31（「简述该场景下的处理顺序。」）在语料有 **33** 个逐字重复块，golden 取其 source 块，`verbatim_dup_count=33` 如实入档 |
| query 面纪律 | 64/64 query 与 V1 逐字相同（冻结复用，禁从目标块循环提取）；provenance 字段全继承；case 顺序=v1_idx 对齐 |

worst-10 对齐：V2 golden 与 `r24_worst10_probe64.json` top1 块 **10/10 相等**（变更单验收断言 §5-4）。

## 3. 新基线数字（现产线 V2 cliff on，pre-fix 如实冻结，无目标预设）

契约 `contracts/rag-baseline-eval64-v2.json`（draft:false，git_rev=8d33ced）：

| 指标 | 数值 |
|---|---|
| **hit_rate@5** | **0.9844**（63/64） |
| **mrr@5** | **0.9414** |
| hit@3 | 0.9688 |
| rank 分布 | rank1=59、rank3=3、rank4=1、miss=1 |
| miss 明细 | 仅 idx31（33 重复块的泛化题干「简述该场景下的处理顺序。」）——恰是逐字包含信号最弱的形态 |
| final_docs 分布 | {5: 64}（V2 断崖 quant=0.60 全量保满 5；R22 时代 final_docs=2 收缩形态已不存在） |
| determinism | run1/run2 四元组指纹**逐位一致**（hit_rate_equal/mrr_equal/per_query_identical 全 true） |
| 延迟 | median 1428.4 ms/query，0-LLM，realtime retrieve_three_channel 全链 |
| 阈值 | 基线-0.02：hit≥0.9644 / mrr≥0.9214（持续回归下限；门禁适用范围裁定权在编排者） |
| module_level_secondary（次级，非门禁） | module_hit@5=0.0781、module_mrr@5=0.0318（=V1 golden 路由卡在 final docs 的命中率） |

## 4. V1/V2 尺对照（同产线、同日、同参，量化「形态错配税」）

| 尺 | golden 形态 | run | hit_rate@5 | mrr@5 | rank1 命中 | miss |
|---|---|---|---|---|---|---|
| **V1 尺**（路由卡 golden，r23 契约口径） | course_module 卡 57/64 | r64v1_ctrl_run1 | **0.0781**（5/64） | **0.0318** | 1 | 59 |
| **V2 尺**（内容块 golden，本变更） | 内容块 64/64 | r64v2_base_run1 | **0.9844**（63/64） | **0.9414** | 59 | 1 |
| **差值（形态错配税）** | — | — | **+0.9063** | **+0.9096** | — | — |

三重一致性交叉验证：① V1 ctrl run（独立进程）hit/mrr = 0.0781/0.0318；② V2 run 的 module_level_secondary（同一批请求里顺带测 V1 golden）= 0.0781/0.0318，与 ① 逐位相同；③ R24 probe ceiling（另一日另一脚本）= 5/64 = 0.0781。**同一产线同一 golden 口径三源归一**，对照表数字可信。

**读法约束（重要）**：0.0781→0.9844 **不是检索质量提升**——链路零改动，变的只是尺子刻度（测什么）。它量化的是旧尺因 golden 形态错配而**看不见**的内容寻回能力（90+ 个百分点）。两尺契约均已写入「禁互相换算」，门禁适用范围裁定权在编排者。

## 5. P0 自批判（≥3 条，如实）

1. **P0-1 子串保底偏乐观，V2 尺天花板风险**：63/64 的 V2 golden 是 query 的提取源块本身（`golden_is_query_source=true`，逐字继承面固有），query ⊆ golden 由构造保证。V2 尺实际测的是「给题干找回原题块」——59/63 命中压在 rank1、hit 0.9844 贴高区，**与 R22 批判 eval_set32 圆环自证的形态学距离不远**（degeneracy 检查 verdict=informative：mrr≠hit_rate 且存在 rank3/4，未达 R22 定义的 degenerate 判定线，但 headroom 仅 1 个 miss）。含义：① 后续小幅真回归可能被子串保底掩盖；② 持续爬升空间耗尽后新尺将失去区分度。缓释：module-level 次级指标随跑产出、V1 尺保留、degeneracy 形态学检查随 _summarize 常驻。**移交候选**：下一代 query 面引入改写/用户侧问句（打破同块派生），登记给编排者。
2. **P0-2 对照表误读风险**：§4 的 +0.9063 极易被读成「改进 90 个点」。已在 §4 与两契约写死读法约束（不是改进，是尺子刻度差）；但报告读者仍可能断章引用。后续任何引用本对照的文档必须携带「链路零改动」限定语。
3. **P0-3 V2 尺的召回层归因缺口**：R24 的「召回覆盖 49/64、15 条 recall miss」是对路由卡 golden 的测量；V2 golden 下的召回层独立归因本轮未做（measure 只记 final 层 rank，idx31 的 miss 无法区分召回 miss 还是 rerank/断崖丢弃）。`r24_rank_probe.py` 探针基建可复跑但需按 V2 golden 重放——**本轮未闭环，如实登记**，不影响基线冻结（基线只冻结 final 层口径）。
4. **P0-4 V1 对照单跑**：V1 ctrl 在 V2 cliff 产线下仅 1 跑（V2 基线为双跑）。缓释：§4 三源交叉归一（独立 ctrl run / V2 run 内嵌次级测量 / R24 探针另一日 ceiling 全等），风险可控；如编排者要求，r64v1_ctrl_run2 可随时补跑。

## 6. 批判承接核对

| 移交项 | 状态 |
|---|---|
| **R24 移交「评测集设计变更候选」**（`R24-completion-report.md` §移交：golden 形态属 contracts 冻结面，只能走变更单移交用户裁定；候选口径=模块卡或所属 bank 任一问句块命中） | ✅ 本轮承接闭环：用户批准变更单 → golden 主目标落内容块（比候选口径更彻底：直接以逐字原题块为 golden，模块卡降次级）；worst-10 证据逐条消费（10/10 对齐） |
| R24 判定「真瓶颈=golden 形态 + 召回侧」 | ✅ 形态半边本轮闭环（V2 尺 63/64）；⚠️ 召回侧半边（对内容块 golden 的召回归因）未单独复测，见 P0-3 登记 |
| R22 批判「建集器缺类型分布检查」（R22 反哺） | ✅ `assert_type_distribution` 硬断言落地（<60% 报错退出），失败路径有单测 |
| AGENTS.md 教训 | 遵循：验收独立实证（全部数字本 agent 用 Milvus/运行产物直接复核，不采信回执）；禁 Playwright；lock 随完工删除 |

## 7. 资产消费证据

| 资产 | 消费方式 |
|---|---|
| `data/r24_runs/r24_worst10_probe64.json` | worst-10 rerank_top5[0] 与 V1 source_chunk_id 逐条比对 → 10/10 对齐；V2 golden 天然来源实证 |
| `data/r24_runs/r24_rank_probe_probe64.json` | ceiling 5/64、召回层 49/64/median 34、rerank_full_scores 结构（浮点分数表，无 id 列——据此放弃离线投影改 realtime 实测） |
| `build_eval_set64.py`（R22 版） | V1 全部纯逻辑函数只读复用（dedup_and_cap/make_golden/sha256_utf8/_milvus_content_map）；`_extract_query` 未触碰 |
| `contracts/rag-baseline-eval64.json`（冻结） | 只读对照（metric_scope/ruler_note/id_map_note 承袭措辞），git diff 为空 |
| `contracts/rag-baseline-eval32.json` | 冻结格式参照（r23 同源） |
| R24 完工报告 | 移交项承接（§6）、瓶颈结论修正脉络 |

## 8. 可复跑命令（edu-agent/ 下）

```bash
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode buildv2
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode measure --tag r64v2_base_run1 --set scripts/eval/data/r64v2_eval_set64.json
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode measure --tag r64v1_ctrl_run1        # V1 尺对照（V1 集缺省路径）
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode freezev2 --runs r64v2_base_run1 r64v2_base_run2
.venv/Scripts/python.exe -m pytest tests/test_build_eval_set64.py -q   # 47/47
```
