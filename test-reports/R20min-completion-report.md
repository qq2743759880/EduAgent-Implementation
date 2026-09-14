# R20-min 评估基线冻结 · 完工报告（W0）

> 任务详档：`.ai-hub/plans/tasks/taskR20min-eval-baseline.md`（v1.2）· 开工包：`.ai-hub/plans/artifacts/kickoff-R20min-W0.md`
> 执行：R20-min 执行 agent · 日期：2026-09-14 · 分支 feature/opt-waves · **git_rev=d9aab44dbd469eed9fdaf3f8e5dd8ae72303afbd**
> 交付 commit：`feat(r)/R20min-eval-baseline`（单一 commit，未 push）

## 结论速览
| GWT | 结果 |
|---|---|
| ① 32 条 eval set 产出且含双键 golden | ✅ `scripts/eval/data/rag_eval_set32.json`（chunk_id+doc_sha256 双键，16 bank×≤2，seed=20260914） |
| ② 同配置重跑两次指标一致 | ✅ base_run1/base_run2：hit_rate@5=0.9688、mrr@5=0.9688，**per_query 逐位全同**（hit/rr/rank/top5 全同） |
| ③ nprobe=1 灵敏度实验指标可见下降 | ✅ PASS（dense 单通道 32→28 命中，掉点 4；融合层不掉点=稀疏通道补偿，如实记录） |
| ④ 基线+阈值文件入库 | ✅ `contracts/rag-baseline-eval32.json`（draft=false；阈值 HIT/MRR_MIN=0.9488=基线-0.02） |
| ⑤ 指标判定基于实时端到端链路+层级 trace | ✅ 全程走 `retrieve_three_channel`；trace 表见 §5 |

## 1. 资产消费证据
实读资产（开工前全文阅读）：
- `edu-agent/scripts/eval/build_eval_set32.py`——发现：query 提取口径（第一问句优先）与抽样分桶逻辑可直接复用；其 frozen_candidates 段设计仅供 A/B 对照，佐证详档"禁用其算指标"的判断；旧落盘 `task32_eval_set.json` 为 recall_topk=300/100 条旧口径且从未入库，与本次产物无冲突。
- `edu-agent/app/chat/retriever.py`——发现：主入口 `retrieve_three_channel`；nprobe 硬编码在 loader（→D-3）；rerank sidecar 优先、断崖无最小保留数（→D-4）。
- `edu-agent/app/knowledge/importer/loader.py`——发现：hybrid_search 的 dense nprobe=10/RRF k=60 为字面量（D-3）；RRF 融合后 raw_retrieved_count 口径（retriever.py:535）即"召回层"trace 值。
- `edu-agent/app/chat/rag_evaluator.py`——发现：`evaluate_retrieval`（hit_rate/mrr/ndcg，top-k 口径）与 `_data_hash` 可复现指纹直接复用，未重造轮子。
- `contracts/reshape-r-eval-draft.json`——发现：C-R-EVAL 草案与详档口径一致，本次冻结即其"draft→false"动作。
- 自检发现并修掉的自身问题：①执行器首版残留被否决的 monkeypatch 死代码块（已清理）；②MilvusClient.search 参数名误用 `param`（应为 `search_params`，已修）；③freeze 灵敏度判定把 rank 64→34（改善）误标回归（已修正语义）；④smoke 首查因 BGE-M3 冷加载 18s 落入 `wait_for(8s)` 窗口导致假性超时（补显式预热，与生产 warmup 等价）。

## 2. 批判承接核对（硬闸门输出）
```
$ node D:/.ai-hub/skills/tt/scripts/critique-backlog-next.mjs --task "评估基线 R20 检索指标"
…
承接判定: HIT_NONE（无落点与本任务重叠；完工报告「批判承接核对」段如实写"无承接项"即可）
```
**无承接项**（C-16..C-24 为部署/性能域批判，与评估基线无落点重叠）。

## 3. 环境自证（第 0 步）
- Milvus：`get_milvus_client().list_collections()` = `['user_memory', 'edu_knowledge', 'pf_bagu_kb']` ✅（VM 已恢复）
- Embedding：EMBED_BACKEND=cuda；BGE-M3 本地加载 `E:/stu/ai-models/bge-m3`（device=cuda）✅；**.env 盘符漂移见 D-2**
- Rerank sidecar：`http://127.0.0.1:8601/health` = model_loaded=true, device=cuda（执行期以进程 env 指向 E 盘模型启动，属生产拓扑件非正产代码改动）
- Neo4j：bolt://192.168.85.101:7687 连接成功（图通道活）
- LLM：本任务全程未调用（纯检索层，符合详档禁项）

## 4. 基线数字与灵敏度实验原始输出
- **基线（32 条实时端到端，两次独立进程）**：hit_rate@5 = **0.9688**（31/32），mrr@5 = **0.9688**；唯一 miss = idx#22（"简述该场景下的处理顺序。"——泛化短句无主题词，检索不可区分属数据特性非链路缺陷，抽检详见 §6）。
- **确定性**：run1/run2 per_query hit/rr/rank_of_gt/top5_ids **逐位全同**（脚本对比输出 True×4）；gate 模式第三次复跑同值 0.9688。
- **灵敏度（nprobe=1，独立同参重放通道）**：
  - 融合层：base(nprobe=10) 32/32 → probe 32/32，掉点 0（稀疏通道补偿，与 C5 批判"BM25 双路增益"结论一致，如实记录不掩盖）
  - dense 单通道（nprobe 直接受影响组件）：base 32/32 → probe **28/32，掉点 4**；GT 排名回归 0、改善 1（idx#8: 64→34）
  - verdict=**PASS 指标可见下降**（判定式：融合掉点 OR dense 掉点；rank 波动只记录不判定）
- **延迟参考**（非门槛）：P50≈1155ms/query（串行 GPU 口径），max≈4741ms。

## 5. 层级 trace 佐证（GWT⑤，32 条全量在 base_run1.json per_query[].trace）
trace 结构：`recall_layer`(融合召回数) → `rerank_layer`(rerank 保留数) → `final_layer`(断崖+截断后)。
样例（idx#0）：recall_layer=150 → rerank_layer=20 → final_layer=2，degraded_reason=None。
全量分布：recall_layer=150×32；final_layer∈{2×18, 5×14}（断崖 0.4 激进截断属正产行为，见 D-4）；3 例 degraded_reason="Neo4j 扩展跳过（ValidationError）"（仅图通道实体丢失，见 D-1）。

## 6. golden 抽检对照（5 条，query→GT 内容人读判定）
| idx | 判定 | query | GT 内容（截断） | rank |
|---|---|---|---|---|
| 0 | 合理 | 化学方程式总是写错时，最该加强的是？ | 【单选题】…化学方程式总是写错…答案：A（记录反馈并据此改进） | 1 |
| 7 | 合理 | 关于部门里有两名员工能力突出，但培养方向还不明确。的处理… | 【多选题】…做能力盘点/匹配岗位要求/设计成长路径 答案：A,B,D | 1 |
| 15 | 合理 | 说明方差和标准差之间的关系。 | 【简答题】…方差是偏差平方的平均，标准差是方差的平方根 | 1 |
| 22 | 合理（数据特性） | 简述该场景下的处理顺序。 | 【简答题】…说明延迟原因；告知预计时间；给出补救安排 | miss（query 无主题词，检索不可区分非标注错误） |
| 31 | 合理 | 权责发生制下，收入一定要等到现金收到后才能确认。 | 【判断题】…答案：B（按业务发生确认，不以现金收付为唯一标准） | 1 |
抽样集覆盖 16 个 bank（每 bank ≤2 条，seed 确定性洗牌）。

## 7. 交付物清单
| 类型 | 路径 |
|---|---|
| 执行器（唯一新增脚本） | `edu-agent/scripts/eval/r20min_run.py`（mode: smoke/build/eval/freeze/gate；exit-1 门逻辑已实现，W0 不接线拦截——详档步骤 4） |
| 评估集（双键 golden） | `edu-agent/scripts/eval/data/rag_eval_set32.json` |
| 运行记录 | `edu-agent/scripts/eval/data/r20min_runs/{base_run1,base_run2,nprobe1_probe,gate_check}.json` |
| 冻结契约 | `contracts/rag-baseline-eval32.json`（draft=false，git_rev 内嵌） |
| 越界上浮 | `.ai-hub/handoffs/R20min-discrepancy.md`（D-1 Neo4j QuestionTag ValidationError / D-2 模型路径盘符漂移 / D-3 nprobe 硬编码 / D-4 断崖无最小保留） |

## 8. 完工前自检（三视角）
- **边界**：miss 例如实保留不计入伪造；nprobe 探针与主链口径隔离并在 JSON 内显式标注（"isolated_replay: 召回层布尔口径"）；dual 通道对照 base 与 probe 同进程产出（消除环境漂移）。
- **错误反馈**：3 例图通道 ValidationError 有降级留痕并上浮 D-1；Milvus/Neo4j 断链走既有降级链路未掩盖。
- **可复现**：seed/params/git_rev 全部入产物；重跑命令仅需 env 覆盖两行（`RERANKER_PATH`/`BGE_M3_PATH` 指 E 盘模型）+ `.venv/Scripts/python.exe scripts/eval/r20min_run.py --mode eval --tag <tag>`；冻结契约 threshold 与基线数字一致可机验。
- 遗留声明：sidecar 进程为本任务拉起（后台），验收后可保留供 R20-b 使用；除该进程外无其他环境残留，正产代码零改动。

## 完工状态
**DONE**（等编排者独立复验+批判，过门后解锁 W1；未接 R20-b/后续任务）。
