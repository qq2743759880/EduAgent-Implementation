# W-NEXT-R24-001 完工报告（R24 收口版 = 编排者自执行版 `0f42b4e` + R24-b 子 agent 活体批合并收口）

> 两段式执行说明：R24 首段由编排者亲自执行（子 agent 撞配额墙，见 git `0f42b4e` 报告原件：画像+worst10 归因+窗口算术证伪），并登记 R24-b 待办（hyde/权重活体实验 + R12 judge 补验 + 探针脚本落盘）。本文件为 **R24-b 子 agent（yy 串行流水线在岗 agent）的收口版**：R24-b 四项全部完成，且以**逐 query 双层 rank 活体测量**精化了首段结论（§2.3 明确标注被修正的判断）。未删节覆盖首段报告；首段原件可溯 `0f42b4e:test-reports/R24-completion-report.md`。
> 基线 tip：`0f42b4e`（分支 feature/opt-waves，symbolic-ref+rev-parse 提交前核对）。单写者锁 `edu-agent/scripts/eval/r24.lock` 已随完工删除。

## 1. 交付概览

| 项 | 内容 |
|---|---|
| 本收口 commit | **`82d046d`**（test(r24b) 主提交；首段=编排者 `0f42b4e`，两段同在 feature/opt-waves） |
| 探针脚本 | `edu-agent/scripts/eval/r24_rank_probe.py`（~620 行，5 模式可复跑：rank/grid/hyde/r12-judge/all-rank-grid；16-query 检查点落盘，宿主限速安全） |
| 数据产物 | `edu-agent/scripts/eval/data/r24_runs/`：r24_rank_probe_probe64.json（64×双层 rank+全序分数）、r24_worst10_probe64.json（证据包）、r24_grid_probe64.json（3 权重臂）、r24_hyde_probe64.json（39 条对照臂）、r24_r12_semantic_judge.json（30 条判定） |
| 核心结论 | 新瓶颈**不是** rerank 排名质量，而是 **eval64 golden 形态（course_module 元数据卡）与语义检索目标的错配 + 召回覆盖缺口**；三个低危候选全部不达标（无开启建议，数字如实登记） |
| 红线自检 | retriever.py / config.py / contracts/ / kg_bridge / trade/** 零改动（git diff 核对）；sidecar 8601 只调用未启停 |

## 2. 任务 1：rank 分布画像（活体实测，非转抄）

探针范式照抄 `r23_cliff_probe.py`（realtime `_milvus_hybrid_search_safe` 召回 150 → 融合去重 → `_rerank_docs` sidecar 全量打分），**新增捕获召回层原始序位**（首段 P0-3 承认的缺口）。n=64，wall 83.1s。`git_rev` 与校验位：rerank-top5=5/64=0.0781、cliff-v2 q0.60 重放 hit@5=0.0781——与 R23 owner_verify 逐位一致（探针-主链同函数同参校验通过）。

### 2.1 双层四桶直方图（0-20 / 21-50 / 51-150 / >150 含 miss）

| 桶 | 召回层原始序位 | rerank 后序位 |
|---|---|---|
| 1-20 | 13 (20.3%) | 14 (21.9%) |
| 21-50 | 17 (26.6%) | 18 (28.1%) |
| 51-150 | 19 (29.7%) | 17 (26.6%) |
| >150 / miss | **15 (23.4%)** | 15 (23.4%) |
| median rank | 34 | 31 |

rerank 层细分：top5=5、6-10=4、11-20=5、21-50=18、51-150=17、miss=15。

### 2.2 迁移矩阵（召回桶 → rerank 桶，49 条双命中 golden）

| 召回桶 | →rerank 1-20 | →rerank 21-50 | →rerank 51-150 |
|---|---|---|---|
| 1-20（n=13） | 6 | 7 | 0 |
| 21-50（n=17） | 7 | 5 | 5 |
| 51-150（n=19） | 1 | 6 | 12 |

逐对统计（n=49）：rerank **提升 30 / 降位 18 / 持平 1，median Δ=-9 位**。

### 2.3 结论（修正首段判断）

**golden 不是被 rerank 压下去的——召回序本来就靠后**：23.4% 连召回 150 都进不了，已召回的中位序位 34。rerank 净效应为正（median -9 位，30:18 提升），「30/49 被压到 20 名外」的主因是其中大多数召回时就在 20 名外（首段因缺召回侧逐 query rank 作出的"rerank 区分度是主要短板"判断**不成立，本轮以活体成对数据修正**）。rerank 对 21-50 桶净吸纳（+1），对 1-20 桶净流失 7 条——但流失对象全部是 course_module 元数据卡（见 §3），属"正确排序输给错配 GT"，非模型区分度缺陷。

## 3. 任务 2：最差 case 归因（逐条证据）

### 3.1 掉得最深的 10 条（全为召回 miss，证据包 `r24_worst10_probe64.json`）

10/10 同型：golden=**course_module 元数据卡**（Milvus 直查证实存在，123-160 字符：模块名/编码/系列/关键词/课时），query=考试式问句，**10/10 的 top1 都是 query 的逐字原题块**（含答案+解析，rerank score=1.0）：

| idx | query（节选） | golden 模块卡 | 证据 | 归类 |
|---|---|---|---|---|
| 6 | 客户投诉物流延迟…最优先的做法 | 投诉安抚与升级处理（136 字符） | top1=逐字原题 s=1.0；golden 与 query 词面重叠≈0，150 内未见 | ③② |
| 7 | 在使用文件描述符时… | 文件与进程基础 | 同上；top2 起 scatters 到其他主题 | ③② |
| 9 | 给出"数学服务现实"的例子 | 工具链基础（交叉数学） | golden 主题词与 query 零重叠（标注经 bank 间接映射） | ③② |
| 15 | 关于命题逻辑的说法 | 命题逻辑与集合关系 | 词面重叠最高（"命题逻辑"）仍 miss——薄卡被同 bank 问句块挤出 | ③② |
| 19 | 前端调试网络请求的工具 | 接口联调与调试实战 | top1=逐字原题 | ③② |
| 21 | 隐藏内部实现只暴露接口的概念 | 面向对象与常用库实践 | top1=逐字原题 s=1.0，top2 s=0.27 断层 | ③② |
| 26 | 词法分析阶段最主要的工作 | 词法语法分析基础 | top1=逐字原题 | ③② |
| 30 | 哪些错误编译期发现 | 词法语法分析基础（与 26 同卡） | top1=逐字原题 | ③② |
| 34 | 关于 TCP 的能力 | TCP/IP与应用层协议实战 | top1=逐字原题 | ③② |
| 1/…（第 10 条） | （另一 miss 同型，详见证据包） | course_module 卡 | 同型 | ③② |

归类口径：**③ golden 标注可疑/任务形态错配（主因，10/10）**——检索面其实已命中最佳内容（原题即答案载体），GT 却要求"题目→所属课程模块"的路由命中；**② 召回 embedding 局限（机制因，10/10）**——130-160 字符薄卡与问句在 dense+sparse 空间无可恢复的相似度桥；**① rerank 模型局限（排除）**——15 条 miss 的 golden 根本未入候选池，rerank 从未接触；**④ chunk 粒度（排除为机制，关联因素）**——卡存在且可查，问题是内容贫化而非切分粒度。

### 3.2 最深的 10 条「已召回」golden（补充首段 rank 124/110/102… 的归因）

全部 course_module 卡：idx31（74→124 绩效面谈）、idx10（104→110 服务异常）、idx12（80→102 目标传导）、idx8（43→98 JS 闭包 vs "HTML/CSS/JavaScript基础"卡）、idx25（140→88）、idx52（99→87）、idx3（22→85）、idx24（33→84）、idx22（139→83）、idx29（98→73）。同 bank 问句块（共享题干/主题词）必然排在一行元数据卡之前——**rerank 的降位是语义正确的排序行为**，错在 GT 把"模块卡"定为唯一命中目标。

### 3.3 全集类型核验（Milvus 直查）

golden 去重 58 个 chunk：57 course_module + 1 doc_chunk（idx37 工具文档，query 逐字点名 → recall 2 / rerank 1，唯一自然成功路径）。15 条召回 miss 全部为 course_module；rerank≤5 的 5 条成功 case = 4 条模块卡（query 与模块主题强词面重叠，如"曲率/施工组织设计"）+ 1 条 doc_chunk。**eval64 实测的是「问句→课程模块路由」，与 RAG 内容寻回目标错配**（57/64=89% 的 golden 是路由卡）。

## 4. 任务 3：低危改进试验（离线网格+活体臂，禁改默认，全部未达标）

| 候选 | 方法 | eval64 hit@5 | mrr@5 | 覆盖/备注 | 裁定 |
|---|---|---|---|---|---|
| 现行基线（主链口径，Phase A） | 生产通道 recall150→rerank→cliff-v2 q0.60 | 0.0781（=ceiling） | — | cover 49/64 | — |
| ① rerank 窗 20→50 | 同一全序截窗 20/50 + V2 断崖离线重放 | 0.0781 vs 0.0781 | 0.0318 vs 0.0318 | **final top5 集合逐位 identical=true** | **无操作，不给开启建议**（final_max_k=5 ≤ 窗 20 ⇒ 结构性零增益，实测+算术双证） |
| ② HyDE on/off | 轻量同义词表改写 39/64 条 → 改写子集 realtime 对照臂（rewrite→recall→rerank 生产顺序） | 0.1026 vs 0.1026（n=39 子集） | 0.0265 vs 0.0265 | **0/39 条 rank 在任一层变动** | **无操作，不给开启建议**（与冻结契约 use_hyde=False 一致维持；真 LLM-HyDE 未测，见 P0-4） |
| ③a dense 0.7/sparse 0.3 | loader 逐字段重放换 WeightedRanker（同通道对照） | 0.0156 | 0.0039 | cover **13/64 崩溃** | 弃用 |
| ③b dense 0.3/sparse 0.7 | 同上 | 0.0625 vs 同通道基线 0.0469 | 0.0174 vs 0.0130 | cover 54/64 vs 50/64，ceiling 4 vs 3 | **+1/64 边际，未达标不给开启建议**（同通道相对口径不可与主链混算；主链复验留给 R25 候选） |

③ 的机制副产物：dense-heavy 让覆盖崩溃到 13/64，反证 **course_module 卡几乎只能靠稀疏词面桥接召回**——与 §3 归因闭环。

## 5. 任务 5：R12 语义 30% judge 补验（30/30 judge_failed → 30/30 判定完成）

复用 r12 存档（`scripts/eval/dualrun_results.json` semantic 30 条 + `dualrun_samples.json` 样本清单），judge prompt 与 `r20b_dualrun_probe.semantic_pair` 逐字一致：

| 指标 | r12 当时 | 本轮补验 |
|---|---|---|
| judge_failed | **30/30**（LLM HTTP 429 AccountQuotaExceeded） | **0/30** |
| equivalent | — | **12 (40%)** |
| not_equivalent | — | **18 (60%)** |
| judge 模型 | fast（minimax-m3） | strong（deepseek-flash@api.deepseek.com；fast 本轮 dashscope 401 invalid_api_key——.env LLM_BASE_URL 默认 dashscope 与 deepseek key 错配，如实登记） |

**口径限制（重要，影响读数）**：① old 侧是 r12 当时 429 降级的**规则答案**（非真实生成），60% not_equivalent 主要反映"规则拼片段 vs LLM 组织答案"的形态差，**不能归因为新路径答案质量缺陷**；② 双侧均为 200 字符 head 截断存档；③ R12 真正的"LLM 活体严格同环境复跑"（双侧活体重生成）仍欠，登记移交。产物：`data/r24_runs/r24_r12_semantic_judge.json`（含 30 条 judge_raw）。

## 6. P0 自批判（5 条）

1. **R23→R24 的问题定义本身偏了，本轮才纠正**：R23 移交"新瓶颈=rerank 排名质量"，首段报告沿用"rerank 把 30/49 压出去"的读法；活体成对测量证明 rerank 净效应为正，主瓶颈是 GT 形态（89% 路由卡）+召回覆盖。教训：移交瓶颈假设必须带"召回/重排分层归因"才能开轮，否则两层混算会误导投入方向（排序层收益封顶 5/64→14/64）。
2. **评测集设计缺陷跨了 R22→R24 三轮才被定量暴露**：57 张 course_module 元数据卡作 golden 的结构性压低，R22 建集时抽样人审即可发现（首段 P0-2 已提，本轮补上 14/15 verbatim-top1 的定量证据）。修复属 contracts/评测集变更（冻结禁改），只能走变更单移交——本轮无法闭环该问题本身。
3. **权重臂只有重放通道口径**：Phase B 基线臂 hit@5=0.0469 ≠ 主链 0.0781（分区/过滤路径差异+rerank 批式噪声），sparse-heavy 的 +1/64 未在主链同参复验即不给开启建议是正确的保守，但也意味着候选③目前**无主链证据**；R25 若接手必须走主链口径而非重放。
4. **HyDE no-op 外推边界**：0/39 rank 不变仅对轻量同义词表（4 词条命中）成立；LLM 生成假设文档的真 HyDE 从未在本项目活体运行过——"HyDE 无用"不可外推，本轮只证明"现行 HyDE 等价于关"。
5. **judge 补验的语义强度受限 + 单人归因**：§5 三条口径限制使 40%/60% 数字只能登记不能定案；worst-10 归因仍是单 agent 内容研判（首段 P0-4 同款），缓解=10/10 同型 + Milvus 直查客观证据（卡存在/字符数/top1 逐字匹配）降低了主观空间，但未经第二人复核。

## 7. 批判承接核对

- **R23 移交**（`1ab598e`/`f00e80f`："剩余瓶颈=rerank 排名质量(R24候选)"）：✅ 本轮承接并完成诊断——结论修正为"瓶颈=GT 形态+召回覆盖"（§2.3），移交的_probe 范式被照抄复用且校验位逐位一致。
- **首段 R24-b 登记**（`0f42b4e` §3/§4/§5：hyde/权重活体 + R12 judge + 探针脚本落盘"待会话重启"）：✅ 四项全部完成——脚本已落盘可复跑（本会话 hook 未拦截）、hyde/权重活体跑毕（§4）、R12 judge 30/30 判定（§5）。
- **首段遗留"评测集设计变更候选"（module 级命中口径）**：⚠️ 属 contracts 冻结面，本轮无权动，**随本报告显式移交编排者/用户裁定**（候选口径：模块卡或其所属 bank 的任一问句块命中皆计分；或按 bank_code 结构化 join 另建路由评测集）。
- 其余移交扫描：R22 报告/R23 报告无其他未销项带入；AGENTS.md 待办区 R24 未被登记为降级项。

## 8. 资产消费证据

- `scripts/eval/data/r22_eval_set64.json`：64 条独立 GT（本探针唯一输入集）。
- `scripts/eval/data/r23_runs/r23_cliff_probe_probe64.json`：ceiling 5/64 交叉验证锚点（本轮 Phase A 校验位逐位一致）。
- `scripts/eval/r23_cliff_probe.py`：probe 范式照抄（realtime 前段+离线网格+检查点落盘沿用）。
- `scripts/eval/r20min_run.py`：`_match_golden` 双键解析直接 import 复用；`_run_sensitivity` 重放范式（loader.py:315-348 逐字段）为 Phase B 权重臂模板。
- `app/chat/retriever.py`（只读）：`_milvus_hybrid_search_safe`/`_rerank_docs`/`_cliff_cutoff_v2`/`_rewrite_query_by_hyde_if_enabled` 逐行为对齐重放依据。
- `app/knowledge/importer/loader.py`（只读）：hybrid_search/INTERNAL_FILTER_EXPR/_and_filter/COURSE_PUBLIC 重放参数源；Milvus 直查证实 golden 卡存在性。
- `contracts/rag-baseline-eval64.json`（冻结只读，禁改已遵守）：独立尺口径核对。
- `scripts/eval/dualrun_results.json` + `dualrun_samples.json`：R12 judge 补验样本与存档答案唯一来源。
- `test-reports/R12-completion-report.md`：judge_failed 30/30 移交原文 + P0-1"LLM 活体复跑欠账"。
- `test-reports/R24-completion-report.md@0f42b4e`：首段报告全文消费，§2.3 逐条回应其画像结论。
- `AGENTS.md`：红线（contracts 冻结/config 默认值/禁 Playwright 独立实证）/教训 8（真实契约优先）。

## 9. 复跑规程

```bash
cd edu-agent
# Phase A：双层 rank 画像 + 窗口/hyde 离线网格 + worst10 证据包（~85s，0-LLM）
.venv/Scripts/python.exe -X utf8 scripts/eval/r24_rank_probe.py --mode rank --tag probe64
# Phase B：dense/sparse 权重臂（~140s，连 Milvus+sidecar）
.venv/Scripts/python.exe -X utf8 scripts/eval/r24_rank_probe.py --mode grid --tag probe64
# HyDE 活体对照臂（需先有 rank 产物；~60s）
.venv/Scripts/python.exe -X utf8 scripts/eval/r24_rank_probe.py --mode hyde --tag probe64
# R12 judge 补验（需 LLM 配额；~60s）
.venv/Scripts/python.exe -X utf8 scripts/eval/r24_rank_probe.py --mode r12-judge
```

预期校验位：Phase A ceiling=5/64、cliff-v2 重放 hit@5=0.0781、召回 cover=49/64；窗口 20/50 final-top5 identical=true；hyde 0/39 rank 变动；judge failed=0/30。
