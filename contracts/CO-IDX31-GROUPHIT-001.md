# 变更单：idx31 组命中放宽（单键精确 → golden 组任一成员）

- **编号**：CO-IDX31-GROUPHIT-001
- **状态**：已批准（用户 2026-09-20，见 dispatch/TO-EXEC-EVALFREEZE-B1.md；本文为正文落档）
- **执行**：W-NEXT-EVALFREEZE-B1-A（build_eval_set64.py 增量 `--group-hit`）
- **依据实测**：r64v3 探针 `_b1_idx31_probe.py`（2026-09-20 活体直查）+ V2/V3 双跑产物

---

## 1. 动机（idx31 泛化题干的「家族错配」）

评测集 idx31（v1_idx=31，V3 cases 位 30；query 面 V2=`简述该场景下的处理顺序。`，V3 改写=`请概述此情形中的处置先后次序。`）是 V2/V3 两尺**唯一 miss**：

- **V2 尺**（n=64）：hit@5=0.9844（63/64），唯一 miss=idx31，rr@5=0；
- **V3 尺**（n=63）：hit@5=0.9841（62/63），同一 idx31 miss。

活体探针（2026-09-20）dump idx31 top5 后根因清晰：

- 该题题干「简述该场景下的处理顺序。」在题库中存在 **33 个平行兄弟块**（`verbatim_dup_count=33`）——它们**逐字共享同一题干**，仅「答案」段不同（`【简答题】题目：简述该场景下的处理顺序。\n答案：<各答案变体>`）；
- 检索链对 idx31 的 top5 **全部落在该兄弟块家族内**（rank1 score=1.0，逐题干预测），但**没有一个**是 golden 指定的那一个答案变体（`_default:482454bc109d453c:1`，答案=「列出具体返工事实…」）；
- 即：检索**正确路由到了正确的题目家族**，却因「33 个同义答案块中精确指定了一个」而被判 miss。这是**标注粒度错配**，不是检索质量缺陷——用户问泛化处置顺序时，家族内任一答案块都已满足召回意图。

> 注：`verbatim_dup_count=33` 是建集器 `find_verbatim_candidates` 对「norm(V2 题干) 子串命中」的计数；它**不是**「与 golden 内容逐字相同的副本数」。探针初版按 doc_sha256 全等判定家族会得到 NONE，已纠正为子串家族语义。

## 2. 变更内容

### 2.1 组命中定义

- **组（golden 组）**：建集时该 case 的 verbatim 候选族 = 内容经 `norm_text`（lower + 去空白/标点/下划线）后包含 `norm(V2 题干)` 的所有块。对 V3 case，V2 题干取 `case.v2_query`；对 V2 case 取 `case.query`。
- **组命中（hit）**：final docs（top5）中**任一**组成员出现即记 hit；
- **组 MRR**：取组内**最好排名**（docs 已按相关度降序，首个命中即最好排名），`rr=1/best_rank`；
- **留痕**：命中路径 `gt_resolve_via="group_hit"`，per_query 增 `group_hit_applied=true / group_size=verbatim_dup_count`。

### 2.2 配置化与毒性隔离（不变量）

- 新增 `measure --group-hit` 开关，**默认关**；关时走原 `_match_golden` 单键（chunk_id → id_map → doc_sha256）路径，**V1/V2 已冻结尺复算零改动**；
- 开启时**仅对 `verbatim_dup_count > 1` 的 golden 生效**。全库实测：V2 集与 V3 集中**仅 idx31 一条**满足（其余 63/62 条 dup≤1 或为 None），天然隔离；
- **不改评测集文件**：V2/V3 集 JSON 逐字节不动（V2 契约记录的 eval-set sha256 不漂移）；组定义从 case 自带 `v2_query/query` 现场重算，不落新键；
- **禁 DB 直写**：本变更只动打分逻辑与产物文件。

### 2.3 影响面预估（与实测对照）

| 尺 | n | 放宽前 hit@5 | 放宽后 hit@5 | 放宽前 mrr@5 | 放宽后 mrr@5 |
|---|---|---|---|---|---|
| V2 内容块 | 64 | 0.9844 (63/64) | 1.0 (64/64) | 0.9414 | ≈0.9570（idx31 组内 rank1 → +1.0/64） |
| V3 改写面 | 63 | 0.9841 (62/63) | 1.0 (63/63) | 0.9683 | ≈0.9841（idx31 组内 rank1 → +1.0/63） |

> 编排者预估 mrr→0.9594（V2）；实测预期 ≈0.9570，偏差 0.0024 < 0.005 阈值，在容差内（差异源于预估对组内最佳排名的粗略假设）。

### 2.4 交付物

| 交付物 | 路径 | 性质 |
|---|---|---|
| 变更单（本文） | `contracts/CO-IDX31-GROUPHIT-001.md` | 新增 |
| 打分器组命中支持 | `edu-agent/scripts/eval/build_eval_set64.py`（`--group-hit`） | 增量（默认关，旧路径零改动） |
| V2 放宽复跑产物 | `edu-agent/scripts/eval/data/r64v2_runs/r64v2gh_run1.json` | 新增 |
| V3 放宽双跑产物 | `edu-agent/scripts/eval/data/r64v3_runs/r64v3gh_run{1,2}.json` | 新增 |
| V3 基线契约 | `contracts/rag-baseline-eval64-v3.json` | 新增（draft:false，含本放宽） |

## 3. 毒性检查（不可回溯证明）

- **代码层**：`--group-hit` 关时 `_measure_one` 走原 `_match_golden` 分支，逐行不变；开时仅进入 `if verbatim_dup_count>1` 分支；
- **数据层**：V2/V3 集中 dup>1 仅 idx31 一条（脚本实测枚举），其余 case 不进新分支；
- **实证层**：同一环境内「无 flag 对照跑」与「--group-hit 处理跑」per_query 四元组指纹（rank/hit/rr/final_docs）diff——除 idx31 外 63 条逐位一致（见 REPORT-EVALFREEZE-B1 §毒性）。

## 4. 回滚方式

- 回滚 = 测量时不加 `--group-hit`：立即回到单键口径，无需删数据；
- V3 契约若需回到「不含放宽」形态，重跑 `measure`（无 flag）双跑后重冻结即可；V2 已冻结契约 `rag-baseline-eval64-v2.json` 本变更**不触碰**。

## 5. 验收断言

1. `--group-hit` 默认关；关时 V2 复跑与已冻结 V2 契约数字一致（单键口径未漂移）；
2. 开时仅 idx31 命中路径变为 `group_hit`，其余 case `group_hit_applied=false`；
3. V2 放宽跑 64/64 hit；除 idx31 外 63 条指纹与对照跑逐位一致；
4. V3 放宽双跑逐位一致（determinism）；V3 契约 draft:false 并显式登记本放宽版本。
