# REPORT-EVALFREEZE-B1 — idx31 组命中放宽 + V3 尺契约冻结（验收报告）

- **派单**：TO-EXEC-EVALFREEZE-B1（用户 2026-09-20 已批）
- **执行**：W-NEXT-EVALFREEZE-B1（main agent 亲执行）
- **日期**：2026-09-20
- **结论**：✅ **两工作包全部闭环**。无停手上报情形（双跑逐位一致、golden 家族形态与背景描述吻合）。

---

## 0. 背景复述与一处关键澄清

派单背景把「idx31 组」描述为 33 个重复块。实读代码+活体探针后澄清：
**「组」≠ 与 golden 内容逐字相同的副本**，而是**建集器 `find_verbatim_candidates` 对 `norm(V2 题干)` 子串命中的 33 个兄弟块**——它们逐字共享题干「简述该场景下的处理顺序。」，仅「答案」段不同。

探针初版按 `doc_sha256 == golden_sha` 全等判定会得到「组命中 NONE」（与派单「hit→1.0」矛盾）；纠正为**子串家族语义**后，活体 dump 证实 idx31 的 top5 全部落在该家族内（rank1 score=1.0）。这与编排者「泛化题干家族错配」判断一致，未构成停手条件。

---

## 1. 工作包 A：idx31 组命中放宽

### A-1 实读（已闭环）
- idx31 = v1_idx=31（V2 per_query idx=31；V3 cases 位 30，因 v1_idx=11 被护栏剔除）。
- 打分逻辑：`build_eval_set64.py::_measure_one` → `_match_golden`（r20min_run.py:275）单键解析 → 仅对**解析出的单个 chunk_id** 算 rank。
- V2/V3 集中 `verbatim_dup_count>1` **仅 idx31 一条**（实测枚举），天然毒性隔离。

### A-2 变更单
`contracts/CO-IDX31-GROUPHIT-001.md`（动机/语义/影响面/毒性/回滚/验收六节齐全）。

### A-3 实施（配置化，默认关）
`build_eval_set64.py` 增量：
- 新增 `measure --group-hit` 开关（**默认 False**）；
- 开启时仅 `verbatim_dup_count>1` 的 case 进入新分支：`ranks = [i+1 for doc if norm(V2 题干) ⊆ norm(doc.content)]`，命中路径 `gt_resolve_via="group_hit"`，per_query 留 `group_hit_applied/group_size`；
- 关闭时走原 `_match_golden` 路径**逐行不变**；不改任何评测集 JSON。
- 可复现命令（edu-agent/ 下）：
  ```
  .venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode measure --set scripts/eval/data/r64v2_eval_set64.json --tag r64v2gh_run1 --group-hit
  ```

### A-4 实跑证明（全部附数字）

| 跑 | 口径 | n | hit@5 | mrr@5 |
|---|---|---|---|---|
| `r64v2_base_run1`（已冻结原值） | 单键 | 64 | 0.9844 (63/64) | 0.9414 |
| `r64v2ctl_run1`（本次同环境无 flag 对照） | 单键 | 64 | 0.9844 (63/64) | 0.9414 |
| `r64v2gh_run1`（--group-hit） | 组命中 | 64 | **1.0000 (64/64)** | **0.9570** |

**毒性证明（逐位不变）**：
- 同环境 `ctl_run1` vs `gh_run1` per_query 四元组指纹 `(rank_of_gt,hit@5,rr@5,final_docs)`：**diff 仅 idx=31 一行**（ctl: `(None,False,0,5) via=miss` → gh: `(1,True,1.0,5) via=group_hit, group_size=33`）；其余 63 条逐位一致。
- `ctl_run1` vs 已冻结 `r64v2_base_run1`：**diff=0**（64/64 指纹全同）——同时证明本次 rerank 走进程内回退（sidecar 8601 未起）未造成环境漂移。
- 预估 mrr→0.9594，实测 0.9570，**偏差 0.0024 < 0.005 阈值**，不触发解释义务（差异源于预估对组内最佳排名的粗略假设，实测组内 rank=1）。

---

## 2. 工作包 B：V3 尺契约冻结

### B-1 双跑（含放宽，终版形态）
```
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode measure --set scripts/eval/data/r64v3_eval_set64.json --tag r64v3gh_run1 --group-hit
.venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode measure --set scripts/eval/data/r64v3_eval_set64.json --tag r64v3gh_run2 --group-hit
```
- `r64v3gh_run1` / `run2` per_query 指纹**逐位一致=True**（未触发停手）。
- 放宽前 V3（`r64v3_base_run1`）：62/63=0.9841, mrr=0.9683；
- 放宽后 V3：**63/63=1.0000, mrr@5=0.9841, hit@3=1.0**；idx=30（v1_idx31）`group_hit_applied=True, rank=1, rr=1.0, group_size=33`；n_group_applied=1。
- 放宽前 vs 放宽后逐行 diff：**仅 idx=30 一行** `(None,False,0)→(1,True,1.0)`。

### B-2 契约 `contracts/rag-baseline-eval64-v3.json`（draft:false）
由 `scripts/eval/freeze_eval64v3.py`（仿 r23_freeze_eval64.py）生成：
- baseline hit@5=1.0, mrr@5=0.9841, n=63；
- thresholds：`RAG_EVAL_HIT_RATE_MIN=0.98`、`RAG_EVAL_MRR_MIN=0.9641`（基线-0.02）；
- determinism_check.per_query_identical=true；
- `idx31_group_hit` 块显式二选一登记：**V3 含放宽=终版形态**（applied=true, change_order 指向 CO-IDX31-GROUPHIT-001）；
- `ruler_note`：三尺并行禁换算——V1 路由卡 0.0781 / V2 内容块 0.9844（单键）/ V3 改写面 1.0（含放宽）；
- eval_set sha256=`2b6d275d…c6d94`（评测集文件逐字节未改）。

---

## 3. 铁律遵守自检
- 禁 DB 直写：measure 只读 retrieve_three_channel，零写库 ✅
- 不 push：仅本地 commit ✅
- 单 commit：见下 ✅
- 未触碰旧契约 `rag-baseline-eval64.json` / `rag-baseline-eval64-v2.json`（git status 无改动）✅
- 双跑不一致/golden 形态不符 → 未触发，无停手 ✅

## 4. 资产消费证据
- 消费派单 TO-EXEC-EVALFREEZE-B1 全部锚点：建集器/冻结器先例/评测集/双跑产物/V2 契约/tracker 段落均已实读引用。
- 产物：变更单 1、冻结脚本 1、V3 契约 1、探针 1、跑产物 4（v2gh/v2ctl/v3gh×2）。

## 5. 批判承接
**无承接项**（本批为用户已批的落地与冻结，无新增批判反哺；毒性隔离已由同环境对照跑实证）。
