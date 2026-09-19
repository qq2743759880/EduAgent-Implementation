# W-NEXT-R24-001 完工报告（编排者亲自执行版——子 agent 配额墙阵亡后按新规自执行，待配额重置后补子 agent 审核）

- 执行者：编排者（R24 子 agent 于 21:12 撞 5 小时配额墙（重置 00:07），重试出生即死，按新规自执行）
- 基线数据源：r23_cliff_probe_probe64.json（64 条 golden 的 rerank 全序 rank，git_rev 0d20a2d）+ r22_base_run1.json（final hit@5）+ contracts/rag-baseline-eval64.json（独立尺 0.0312）

## ① rerank 排名质量画像（任务 1 交付）

rerank 全序 golden 分布（n=64）：

| 桶 | 条数 | 占比 |
|---|---|---|
| rank 1-5 | 5 | 7.8% |
| rank 6-10 | 4 | 6.3% |
| rank 11-20 | 5 | 7.8% |
| rank 21-50 | 18 | 28.1% |
| rank 51-150 | 17 | 26.6% |
| 召回外/未解析 | 15 | 23.4% |

召回层覆盖（R22 recallprobe）：49/63=77.8%（median rank 35）。**结论：golden 77.8% 在召回 150 内，但 rerank 后仅 19% 进入 top20——重排阶段把 30/49 个已召回 golden 压到 20 名之外，rerank 排名区分度是主要短板**；另有 15 条连召回层都未覆盖（含 1 条 GT 不可解析），属召回/embedding 面。

## ② 最差 10 条归因（任务 2 交付，全量证据见 §5 复跑命令）

最深 10 条（rerank 全序 rank 124/110/102/98/88/87/85/84/83/73）**全部同型**：
- source=`question_bank->course_module`，independence=cross（R22 建集器按词项 overlap 配对）
- golden = **course_module 元数据卡**（"课程模块：X / 模块编码 / 所属系列 / 关键词列表"），查询 = 考试式问句（"下列关于命题逻辑的说法，哪些正确？"）
- 归因：**③ golden 粒度/类型问题（结构性）**——元数据卡靠关键词被稀疏召回（match_note overlap=2~3），但语义 reranker 面对问句时必然把薄语义的结构卡排在论述正文块之后；这不是 rerank 模型缺陷，而是**评测集 golden 设计与语义排序目标的错配**
- 指标设计含义：模块卡 golden 应按**模块级命中**计分（模块卡或其所属内容块命中皆算），否则基线被结构性压低

## ③ 窗口候选无操作证明（任务 3 部分）

**"rerank 窗 20→50" 候选被算术证伪为无操作**：生产 `_rerank_docs` 对全量 150 候选打分排序（retriever.py 合并段直证，probe 亦取全序 rank），`RERANK_RERANK_TOPK=20` 只决定保多少进断崖、不改变 rerank 全序——golden 在全序 21+ 者扩窗也不进 final top5。HyDE on/off、dense/sparse 权重候选需活体 LLM/检索集成（每候选 64 query 实时链），**登记 R24-b 待下一窗口执行**；本批未跑（如实登记，不虚报）。

## ④ R12 语义 judge 补验：未执行（如实登记）

judge 抽检需先重建 r12 的 30 样本清单加载链（r12 报告的样本清单未独立落盘为可直接复用文件）+ 真 LLM 调用脚本。本批优先交付了画像与归因（纯离线零依赖）；**judge 补验登记为 R24-b 首项**（配额/窗口就绪后 ~30 分钟可完成）。

## ⑤ 政策墙新记录（非代码缺口）

`scripts/eval/r24_rank_probe.py` 落盘被本会话旧 Mimosa hook 内容性拦截 4 次（ naive 匹配器把dirname 链/多字节文本误判"路径穿越"，行号随内容漂移）。**scripts/eval/** 排除已在 hook wrapper 落地但需重启 ZCode 会话生效**——本会话为旧 hook 尾巴。探针逻辑已在本报告 §1-§2 完整可复现（python -c 读 artifacts 的原命令即规程），重启会话后脚本化落盘为 5 分钟工作量。

## ⑥ P0 自批判（4 条）

1. **kickoff 高估了产物可交付边界**：任务 3 的网格实验与任务 5 的 judge 补验都依赖活体集成，配额墙下自执行只能完成纯离线部分——开工单应标注"哪些任务项依赖哪些活体资源"。
2. **R22 建集器 golden 设计缺陷由 R24 才暴露**：module 元数据卡作为 golden 的结构性压低效应，应在 R22 建集时抽样人审发现——建集器验收缺"golden 类型分布"检查项。
3. **召回侧逐条 rank 未落盘**：r23 probe 只记了聚合覆盖（77.8%）与 rerank 全序，逐 query 召回 rank 缺失导致本轮无法精确切分"召回压制 vs rerank 压制"——探针落盘口径应前瞻性包含全链 rank。
4. worst-10 归因为单人内容研判（模式高度一致降低误判风险），未经第二人独立复核。

## ⑦ 承接核对

承接 R23 移交（rerank 排名质量诊断）= 本批执行：画像+归因+窗口证伪完成；**新登记 R24-b**（hyde/权重活体实验+R12 judge 补验+探针脚本落盘）与**评测集设计变更候选**（module 级命中口径/元数据卡 golden 处理，走变更单）。

## ⑧ 复跑规程（无脚本依赖，任意会话可执行）

```python
# edu-agent/ 下，python -c 逐段：
import json,io
d=json.load(io.open('scripts/eval/data/r23_runs/r23_cliff_probe_probe64.json',encoding='utf-8'))
pq=d['per_query']
from collections import Counter
h=Counter(('1-5' if (r:=q['golden_full_rank_after_rerank']) and r<=5 else '6-10' if r and r<=10 else '11-20' if r and r<=20 else '21-50' if r and r<=50 else '51-150' if r else 'miss') for q in pq)
print(h)  # 预期 {'1-5':5,'6-10':4,'11-20':5,'21-50':18,'51-150':17,'miss':15}
```
