# R22 去圆环评估集 + 阈值头寸测量 · 完工报告（W-NEXT-R22-001）

> 任务书：编排者派单（C-01：编排者逐断言独立实证验收前的执行轮）· 开工基线资产：`.ai-hub/plans/artifacts/kickoff-R20min-W0.md`
> 执行：W-NEXT-R22-001 执行 agent · 日期：2026-09-18 · 分支 feature/opt-waves · **开工 git_rev=f77877534a711250e9e0f71812d05613abd53e4c**
> 交付 commit：`feat(r)/R22-decircle-evalset64`（单一 commit，未 push；**hash 自指不可写入自身 commit 内容**，收单时以 `git log -1 --grep=R22 --format=%H` 复核，hash 同步回执在执行 agent 交付消息中）

## 0. 结论速览

| 断言 | 结果 |
|---|---|
| ① 去圆环：64 条新集，golden query 不从目标 chunk 自身提取，independence 溯源 | ✅ `scripts/eval/data/r22_eval_set64.json`（manual=1 / cross=63，58 个不同 golden，双键 golden，反圆环不变量全量机验 0 违规） |
| ② 头寸测量：新集跑现检索链（R20-min 范式，0-LLM），分布+95% CI | ✅ hit_rate@5=**0.0312**（Wilson95 [0.0086, 0.107]），mrr@5=**0.0195**（bootstrap95 [0, 0.0547]）；两跑 per_query 逐位全同 |
| ③ 不落门 | ✅ 未改 contracts/**（rag-baseline-eval32.json 与开工前逐字节一致）、未改 check-demo/veclock 门槛、未改 retriever/app/**、config.py、build_eval_set32.py 行为 |
| ④ 生成器单测 | ✅ `tests/test_build_eval_set64.py` 25/25（离线 0.5s：independence 强制/去重配额/双键/反圆环/规则改写/CI/退化判别） |
| ⑤ 未贴天花板 | ✅ 与 Crit-3 预设方向相反——独立 GT 下 hit_rate@5 距天花板 0.9688，「区分度不足」分支未触发，分级指标仍全量产出 |

**一句话结论**：同一条检索链、同一套冻结参数，圆环 GT（eval_set32）测出 0.9688，去圆环 GT（eval_set64）测出 0.0312——R20-min 基线的 0.9688 中约 **0.94 是方法论自证成分**（Crit-1 定量坐实）；阈值 0.9488 只对圆环 GT 有意义，对独立 GT 无头寸可言（Crit-3 定量坐实）。

## 1. 两批判承接说明（本轮即承接）

承接源：`.opencode/plans/critique-backlog-tracker.md` §「R20-min 验收(2026-09-14,双环)」L544 Crit-1 / L546 Crit-3。

### Crit-1 golden 圆环自证 → 本轮去圆环构造
- 原批判：eval_set32 的 query 从 chunk 自身提取 → 命中全 rank1、mrr==hit_rate 退化分布，基线测的是"能否找回引文"。
- 承接动作：新建 `scripts/eval/build_eval_set64.py`，golden 与 query 强制分离：
  - **manual**（independence=manual）：query=chat_message 真实用户问句（规则 regex 改写去寒暄，禁 LLM）；golden=同会话 assistant 回复 `rag_docs_json` 中生产实际投喂 chunk（RetrievedDoc.doc_id==Milvus chunk_id，retriever.py:266 实读核实），且经当前库内容 sha 复核+强特征词重叠校验。
  - **cross**（independence=cross）：query=题库 question chunk 题干（只读复用 `build_eval_set32._extract_query`，不改其行为）；golden=同域课程 course_module chunk（73/73 bank→series 归一化对齐实测；互证规则=标题+关键词行词重叠≥2 或单词≥4 字、次优边际严格），golden≠source chunk（id+sha 双验）、query 非 golden 子串。
- 去圆环形态学证据：新集 rank 分布 {rank1:1, rank4:1, miss:62}，mrr@5(0.0195)≠hit_rate(0.0312)，`degeneracy_check` 判 **informative(有区分度)**——不再是对 eval_set32 的 rank1 退化形。

### Crit-3 阈值头寸退化 → 本轮头寸测量
- 原批判：0.9688 贴天花板，阈值 0.9488=基线-0.02 无法区分真回归与测量噪声。
- 承接动作：新集全量跑实时端到端链（同冻结契约参数），产出分布+CI+确定性对照+分级指标（见 §4）。**未贴天花板**：gap_to_ceiling=0.9688。若在新集沿用"基线-0.02"规则得等价阈值 0.0112，低于 mrr bootstrap CI 下界——**"基线-0.02"规则在独立 GT 集上不可用**，门禁头寸问题需改用 CI 口径或分层指标（hit@3/mrr@10/distinct-doc），裁定权在编排者，本任务不落门。

## 2. 资产消费证据

| 资产 | 实读发现 |
|---|---|
| `.ai-hub/plans/artifacts/kickoff-R20min-W0.md` | 测量仪范式全部继承：实时端到端禁冻结候选算指标、双键 golden、确定性两跑、灵敏度通道只做相对对照 |
| `contracts/rag-baseline-eval32.json`（**禁改遵守**，仅读） | 基线 0.9688/阈值 0.9488/params（recall150/rerank20/final5/cutoff0.4/hyde off/graph on/nprobe10/rrf60/cuda/student）逐字段对齐进 `build_eval_set64.PARAMS` |
| `edu-agent/scripts/eval/build_eval_set32.py` | `_extract_query` 只读导入复用（r20min_run.py 同例）；其 docstring 自证了圆环设计的由来 |
| `edu-agent/scripts/eval/r20min_run.py` | `_match_golden` 双键解析（chunk_id→id_map→doc_sha256）只读复用；PARAMS 源头 |
| `edu-agent/scripts/eval/data/rag_eval_set32.json` | 圆环证据：32 条 golden 全为 question chunk 自身（如 `question_senior_transition_bank_q019`），query 即该 chunk 题干 |
| `edu-agent/scripts/eval/data/task32_eval_set.json` | 旧口径遗留（recall_topk=300/100 条），未混淆进本轮 |
| `edu-agent/scripts/eval/r20b_dualrun_probe.py` | chat_message 真采 SQL 口径同源（role=user/长度≥10/会话 yn=1/会话配额≤3/SQL 相对序+种子内洗牌） |
| `.opencode/plans/critique-backlog-tracker.md` | L544/L546 两条批判原文（承接源） |
| `app/chat/retriever.py`、`app/chat/rag_evaluator.py`、`app/knowledge/importer/loader.py`、`app/rerank_service/main.py` | 签名核对：`retrieve_three_channel`/`evaluate_retrieval`/`_data_hash`；RetrievedDoc.doc_id=chunk_id（retriever.py:266）；sidecar 启动方式 `uvicorn app.rerank_service.main:app --port 8601` |
| `AGENTS.md` | 教训 7（查询/入库 embedding 同为 BGE-M3）、教训 2（禁 Playwright、独立实证）、教训 8（实测契约优先） |

## 3. 环境自证（第 0 步）
- Milvus：`get_milvus_client().list_collections()` 含 `edu_knowledge` ✅（实测 content_type 分布：question 1751 / doc_chunk 762 / course_module 657 / course_intro 219）
- MySQL：`init_mysql()` 连接池 localhost:3306 ✅；`chat_message` 236 user / 236 assistant（yn=1 会话），`rag_docs_json` 全部落在 assistant 侧（user 侧 0）→ manual 配对按 (session, created_at, id) 相对序取"紧随 assistant"
- Embedding：EMBED_BACKEND=cuda（.env），BGE-M3 本地，GPU 8G 卡与 8000 后端共存（后端常驻 ~2.9G，本测量进程+sidecar 峰值共用 <5G，未触 cpu 降级）
- Rerank sidecar：8601 手动拉起（`uvicorn app.rerank_service.main:app`），health=model_loaded=true, device=cuda, gpu_mem=1092MB ✅
- LLM：全程 0 调用（规则改写=纯 regex；互证=纯字符串规则；改写/互证/检索均无 LLM 依赖）✅

## 4. 头寸分布数字（全部可复现）

### 4.1 主口径（与冻结契约同参，实时端到端 `retrieve_three_channel` 全链）
| 指标 | eval_set64（本轮新集 n=64） | eval_set32（冻结基线，圆环 GT） |
|---|---|---|
| hit_rate@5 | **0.0312**（2/64） | 0.9688 |
| hit_rate@5 Wilson 95% CI | [0.0086, 0.107] | — |
| mrr@5 | **0.0195** | 0.9688 |
| mrr@5 bootstrap 95% CI（B=10000, seed=20260918） | [0.0000, 0.0547] | — |
| rank 分布 | rank1=1, rank4=1, miss=62 | 命中 31/32 全 rank1（Crit-1 记录） |
| 退化形态判别 | informative（mrr≠hit_rate） | degenerate（mrr==hit_rate 且全 rank1） |

确定性：`r22_base_run1` vs `r22_base_run2` **per_query 逐位全同**（rank_of_gt/hit@5 全同；wall 121.2s/116.9s），与 W0 同规格。

分组：manual（n=1）1/1 命中（CI [0.21,1]，n=1 无统计力，如实标注）；cross（n=63）1/63。

### 4.2 分级窗口（top_k=final_max_k=10，其余同契约；口径单独披露）
- hit@3=0.0156，hit@5=0.0312，hit@10=0.0469，mrr@10=0.0218（bootstrap95 [0, 0.0592]）
- rank 直方图：rank1=1, rank4=1, rank7=1, miss=61
- **distinct-doc 覆盖：3/64**（去重命中 golden 的文档数/样本数）——多 query 挤同一 doc 的退化暴露维度

### 4.3 分层归因（recallprobe 独立直连通道，loader.hybrid_search 同参重放，召回层口径不与主链混算）
- **golden 在召回 top150 内：49/63（77.8%）**；golden 召回排名 min=2 / median=35 / max=139
- 同一批 golden 走完全链后 hit@5 仅 3.1%：**49 个被召回的独立 golden 中 46 个死于 rerank+断崖层**
- 断崖行为旁证：run1 中 28/64 query 断崖后 final_docs=2（cutoff_drop_ratio=0.4 在 rerank 分数集中时激进收缩，top5 窗口实际常为 top2）

### 4.4 头寸判定（产物 `data/r22_position_measure.json`）
- verdict=**headroom_measured(有头寸)**——「区分度不足」分支未触发（未贴 1.0），分级指标仍全量产出备用
- 阈值头寸：冻结阈值 0.9488 对本集 margin=-0.9176；"基线-0.02"规则在新集等价 0.0112，低于 CI 下界 → 规则不可迁移，需编排者裁定门禁口径

## 5. 独立 golden 5 条抽检（人读判定，全部判定"相关"）

| # | 源 | query | golden 内容（截断） | 人读判定 |
|---|---|---|---|---|
| 1 | manual | 请使用 knowledge_import 工具把示例文档导入知识库（visibility=private） | `## 4. 实现规划要点 / - knowledge_import_task：task_id PK、task_type、tenant_id、visibility…`（cited_rank=1） | ✅ 相关（工具问句→实现文档） |
| 2 | cross | 如果样式在某个页面里失效了，你会怎么排查？ | 课程模块：页面结构与样式体系（frontend_development_foundation_m1；matched=[样式,页面] margin=1） | ✅ 相关 |
| 3 | cross | 在多进程与多线程的对比中，哪一项更符合线程的典型特点？ | 课程模块：进程线程与并发控制（systems_programming_practice_m1；matched=[线程,进程]） | ✅ 相关 |
| 4 | cross | 复试表达中，哪些做法通常更受欢迎？ | 课程模块：结构化表达与临场应对（postgraduate_retest_practice_m1；matched=[复试,表达]） | ✅ 相关 |
| 5 | cross | 关于前端异步编程，哪些说法正确？ | 课程模块：异步编程与模块化开发（web_programming_languages_practice_m1；matched=[异步,编程]） | ✅ 相关 |

另：全部 64 条经 `validate_case` 全量机验（golden≠source id+sha、query 非 golden 子串、双键一致、溯源字段齐全）**0 违规**；数据集内 58 个不同 golden、单一 golden ≤2 次、40 个不同 source bank。

## 6. P0 自批判（≥3 条，全部附证据）

- **S-1 cross GT 是"覆盖该知识点的教学材料"，不是"答案文档"**：本题库的答案内嵌于 question chunk 自身（选项+答案+解析），任何非自身 golden 都是代理 GT。0.0312 的绝对值只能解读为"教学材料浮出率"，不能与 0.9688 直接比大小得出"检索崩坏"——但结构性结论（圆环自证成分≈0.94）不依赖 GT 完美：召回层 77.8% 覆盖+5/5 抽检相关已证 golden 与 query 语义相关，瓶颈在 rerank+断崖层而非"golden 乱指"。
- **S-2 manual 模式固有偏置+样本塌缩至 n=1**：manual golden=生产链自产引用，本质测"链自一致性"而非"相关性"；且 chat_message 为测试语料——69 对有效（223 对中 154 对 assistant 带 rag_error 被原则性排除）、104 个被引 doc 仅 40 个仍在当前库（180 次 doc 级失配）、强证据规则后唯一池仅 1 条。n=1 的 95% CI [0.21,1] 无信息量。chat 侧真实问句规模化 labeling 是长期解（需 LLM 或人工，均在本任务禁区）。
- **S-3 jieba 词袋校验脆弱（已实证双向翻车）**：弱重叠通道曾放进无关 golden（"用两句话介绍一下一般过去时"配上"复试自我介绍"chunk、"现在完成时"配上"工作汇报"chunk——被 5 条抽检人工兜住后关闭弱通道）；强通道又因分词粒度两侧不一致误杀好 golden（"牛顿第二定律"整词 vs doc 侧"牛顿/第二/定律"分片）。零 LLM 约束下无更强校验器，这是本范式已认知上限，已写入 meta 供后续接 LLM-as-judge 时重校。
- **S-4 断崖层"黑洞"现象未经专门批判**：28/64 query 断崖后 final_docs=2，意味着 hit@5 判定实际常在 top2 上做。本任务只做了归因测量未做参数批判（cutoff_drop_ratio 是否应有最小保留数属检索正产改动，越界禁碰），已具备的数据在 `r22_runs/*.json` trace 中，供 R23/检索域批判接手。
- **S-5 测量环境单卡共享**：8G 卡上 8000 后端 BGE-M3 常驻与本测量进程共存，sidecar 为本任务手动拉起（生产拓扑件，非正产改动），测量后已停；与冻结基线执行期环境（sidecar 常驻、GPU 独占度不同）存在硬件级噪声差异，两跑逐位一致说明进程内确定性成立，跨环境绝对值迁移需复跑。

## 7. 批判承接核对（硬闸门输出）

```
$ node D:/.ai-hub/skills/tt/scripts/critique-backlog-next.mjs --task "评估基线 R20 检索指标"
…
承接判定: HIT_NONE（无落点与本任务重叠；完工报告「批判承接核对」段如实写"无承接项"即可）
[FAIL] 批判承接硬闸门：C-10,C-11,C-12 缺少后续任务文档，禁止派单开工
```
- 形式判定 **HIT_NONE**：C-16..C-24 及 C-10/11/12 为部署/CLI/派单域批判，与评估基线无落点重叠（闸门 FAIL 项为 backlog 自身的任务文档缺失登记问题，非本任务承接范围）。
- **实质承接**：本任务即 R20-min 验收 Crit-1/Crit-3 的承接轮（tracker 该两条为验收批判、无 critique-<Cxx>-task.md 文档，故关键词匹配器不命中）——承接证据见 §1，建议编排者收单后将 tracker 两条处置栏标注 ✅（tracker 归编排者所有，执行 agent 不代改）。

## 8. 不落门自证
- `git status` 对照：本轮未触碰 `contracts/**`（rag-baseline-eval32.json 无 diff）、`retriever/app/**`、`config.py`、`trade/**`、`build_eval_set32.py`（内容零改动，仅 import 复用）、check-demo/veclock 门槛文件
- 新数字仅存在于：`data/r22_eval_set64.json`、`data/r22_runs/r22_base_run{1,2}.json`、`data/r22_runs/r22_graded10.json`、`data/r22_position_measure.json`、`data/r22_recall_layer_probe.json` 与本报告
- 工作树中两处**非本轮**的既有脏文件（`scripts/eval/dualrun-baseline.md`、`edu-frontend/next-env.d.ts`，开工前已存在）未纳入本 commit

## 9. 产物清单
| 文件 | 说明 |
|---|---|
| `edu-agent/scripts/eval/build_eval_set64.py` | 生成器+测量仪+recallprobe+spotcheck（6 模式）；纯逻辑层模块级可离线单测 |
| `edu-agent/tests/test_build_eval_set64.py` | 25 用例，离线 0.5s |
| `edu-agent/scripts/eval/data/r22_eval_set64.json` | 64 条（manual=1/cross=63），双键 golden+independence 溯源+yield 全统计 |
| `edu-agent/scripts/eval/data/r22_runs/r22_base_run{1,2}.json` | 主口径两跑 per_query 全量（确定性对照） |
| `edu-agent/scripts/eval/data/r22_runs/r22_graded10.json` | 分级窗口 top10 |
| `edu-agent/scripts/eval/data/r22_position_measure.json` | 头寸汇总（CI+确定性+分级+verdict） |
| `edu-agent/scripts/eval/data/r22_recall_layer_probe.json` | 召回层归因 63 行 |
| `test-reports/R22-completion-report.md` | 本报告 |

复现命令（edu-agent/ 下）：
```
.venv/Scripts/python.exe -m pytest tests/test_build_eval_set64.py -q
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode build
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode measure --tag <tag>
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode position --runs r22_base_run1 r22_base_run2 --graded-tag r22_graded10
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode recallprobe
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode spotcheck
```
