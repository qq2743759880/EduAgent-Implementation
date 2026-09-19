# W-NEXT-R23-001 独立审核报告（W-NEXT-R23-AUDIT）

- 审核者：独立审核子 agent（与执行者不同实例，未采信完工报告任何未复现数字）
- 审核对象：`test-reports/R23-completion-report.md` + commit `818b83d`（分支 feature/opt-waves，HEAD=818b83d 工作区实跑）
- 审核日期：2026-09-19
- 方法：逐断言独立复现（亲跑 probe×2 / pytest×3 / fuzz 5000 组 / git diff 全量对照），全部命令在本机真实执行

## 总判定：PASS（7/7 断言 PASS，新发现 P2×1 措辞瑕疵、无 P0/P1）

---

## 断言 1：门禁数字 — PASS

**eval64 复跑**（`cd edu-agent && .venv/Scripts/python.exe scripts/eval/r23_cliff_probe.py --set eval64 --tag audit_r23`，wall=154.1s，exit 0）：

```
[probe:audit_r23] ceiling rerank-top5=5/64 top10=9 top20=14 v1_replay_hit@5=0.0312
  v2c_quant_0.5  hit@5=0.0781  mrr@5=0.0318  fd={'5': 64} mean=5.0
  v2c_quant_0.6  hit@5=0.0781  mrr@5=0.0318  fd={'5': 64} mean=5.0
  v2c_quant_0.7  hit@5=0.0781  mrr@5=0.0318  fd={'5': 64} mean=5.0
  v2a_floor_0.3  hit@5=0.0625  mrr@5=0.0286
```

- v1_replay=0.0312 与契约 `contracts/rag-baseline-eval64.json` baseline.hit_rate@5=0.0312 **一致** ✓
- v2c_quant_0.6=0.0781=5/64=ceiling（ceiling.golden_in_rerank_top5 实测 5/64，round(5/64,4)=0.0781）✓
- 0.5/0.6/0.7 平台=0.0781（报告 §② 声称复现）✓；v2a_0.3=0.0625（报告 §② 声称复现）✓；mrr 0.0318（报告 §④-5 数字一致）✓

**eval32 复跑**（`--set eval32 --tag audit_r23_32`，wall=92.5s，exit 0）：v2c_quant_0.6 hit@5=0.9688 mrr@5=0.9688；**逐位验证**：对 32 条 per_query 亲算 keep_v1 vs keep_quantile(0.6) 的命中集合，`diffs = []`（31/32 命中逐条相同）→ BITWISE-UNCHANGED ✓

**确定性交叉**：我的 audit 产物 vs 编排者产物 per_query 逐行对照（eval64: `r23_cliff_probe_audit_r23.json` vs `r23_cliff_probe_orch_verify_v2on.json`；eval32: `..._audit_r23_32.json` vs `..._orch_verify32.json`）——score vectors / v1_keep / golden_rank **全部 0 diff，IDENTICAL**。另 v1 fd 分布 `{'2':28,'3':1,'4':1,'5':34}` 与契约 cliff_behavior 逐字段一致。

## 断言 2：灰度默认关 — PASS

实跑 `Settings()`：

```
RERANK_CLIFF_V2 = False
RERANK_CLIFF_V2_QUANT = 0.6
has SCORE_FLOOR attr: False
```

生产路径派发唯一性：`app/chat/retriever.py:702-703` —— `_cliff_cutoff`（V1 入口，唯一调用点 retriever.py:881 `final_docs = _cliff_cutoff(merged, ...)`，输入即 `_rerank_docs` 返回的 top20）内 `if getattr(settings, "RERANK_CLIFF_V2", False): return _cliff_cutoff_v2(...)`。grep 全 `app/` 仅此一处 V2 派发；旧字段 `RERANK_CLIFF_V2_SCORE_FLOOR` 无任何残留引用。

## 断言 3：实现与 probe 逐位一致 — PASS

**静态对照**（`r23_cliff_probe.py:keep_quantile` vs `retriever.py:_cliff_cutoff_v2`）逐条语义一致：

| 语义 | probe (L105-117) | retriever (L729-737) | 一致 |
|---|---|---|---|
| 分位取值 | `xs=sorted(scores); idx=min(int(q*len(xs)), len(xs)-1); floor=xs[idx]` | `xs=sorted(d.score for d in docs); floor=xs[min(int(q*len(xs)), len(xs)-1)]` | ✓ |
| <floor 停 | `if s < floor or kept >= k: break` | `if d.score < floor or len(truncated) >= final_max_k: break` | ✓ |
| 边缘不保留 | `s < floor` 严格小于即停（==floor 保留） | 同 | ✓ |
| top1 恒保 | `kept=1` 起步 | `truncated=[docs[0]]` | ✓ |
| cap | `k`（kept>=k 即停） | `final_max_k`（[:final_max_k] 兜底） | ✓ |

精度同源：生产 `_rerank_docs` 内 `d.score = round(...,6)`（retriever.py:674），probe `scores20 = round(float(d.score),6)`——两侧同为 round6。`int(0.6*20)==12.0`（实测无浮点陷阱）。

**动态 fuzz 实证**：5000 组随机向量（n∈{1..40}、k∈{3,5,8}、q∈{0.1,0.25,0.34,0.5,0.6,0.7,0.9}），生产 `_cliff_cutoff_v2`（settings 注入同源 q）vs probe `keep_quantile`：**mismatches=0，BITWISE-EQUAL**。
（审核过程留痕：第一轮 fuzz 出 mismatch 系审核脚本自身 bug——生产固定 q=0.60 而 probe 传随机 q，不同源所致；抽查 3 个 mismatch case 亲手验算两实现各自输出均正确，修正同源后全同。该 bug 属审核方，与被审代码无关。）

## 断言 4：单测 — PASS

实跑 `pytest tests/test_r23_cliff_v2.py -q` → **12 passed**（5.68s）。

抽查断言语义（分位 idx 亲手验算）：
- `test_v2_on_stops_before_below_quant_edge`：n=5 → idx=int(0.6×5)=3 → xs=[0.18,0.19,0.2,0.9,1.0] → floor=xs[3]=0.9；c1=0.9 不<0.9 保留、c2=0.2<0.9 停 → [c0,c1]。断言注释与验算一致，「边缘不保留」语义锁定正确 ✓
- `test_v2_on_wide_spread_cuts_within_top5`：n=8 → idx=int(4.8)=4 → floor=xs[4]=0.7 → 保 c0..c3（0.7 不<0.7）、c4=0.6<0.7 截断 → 4 条。证明宽分布非恒 cap 补满（报告 §② 语义诚实登记的锁定面）✓
- 附验：idx23 recover（int(0.6×20)=12 → 升序 xs[12]=0.341 → 保 5 条 cap）✓；switch_wiring（n=4 → idx=2 → floor=0.595 → [c0,c1]）✓

## 断言 5：禁动项 — PASS

`git show 818b83d --name-only`：仅 11 个文件——`edu-agent/app/chat/retriever.py`、`edu-agent/app/config.py`、`edu-agent/scripts/eval/r23_cliff_probe.py`、`r23_freeze_eval64.py`、`edu-agent/scripts/eval/data/r23_runs/*.json`（4 个产物）、`edu-agent/test-reports/r23_chat_sse_probe.py`、`edu-agent/tests/test_r23_cliff_v2.py`、`test-reports/R23-completion-report.md`。
- kg_bridge / kg_expand 语义 / embedding 配置 / `loader.py` / `graph.py` / `trade/**` **零触碰** ✓
- retriever.py diff 仅两个 hunk（@@ -679,18、@@ -712,27），全部在断崖函数区（注释块+派发+_cliff_cutoff_v2 重写）；channel_health 组装段（L877 起）零改动 ✓（单测 `test_full_chain_v2_off_vs_on_channel_health_unchanged` off/on 逐字段一致亦锁）

## 断言 6：契约 — PASS

`contracts/rag-baseline-eval64.json`（仓库根；由 WIP `0d20a2d` 引入，`git diff 0d20a2d..HEAD -- contracts/` 为空 = 818b83d 零改动，与报告「前任建，编排者验证」一致）：
- `draft: false` ✓；`golden_double_key: ["chunk_id", "doc_sha256(...)"]` 双键 ✓
- `ruler_note`: "…eval32 圆环尺保留作旧路径一致性对照，两尺并行禁互相换算" ✓
- `params.rerank_cliff_v2: false`（V1 基线口径自洽）✓
- baseline hit_rate@5=0.0312 / mrr@5=0.0195、cliff_behavior {2:28,3:1,4:1,5:34}（28+1+1+34=64）——与我复跑 v1_replay/fd 逐字段一致 ✓
- 与 eval32 契约（`contracts/rag-baseline-eval32.json`）无字段冲突：plan_id 不同（reshape-r-eval64 vs reshape-r-eval）、eval_set 不同文件、thresholds 各自独立且 eval64 rule 显式声明独立尺地位；同名字段 RAG_EVAL_HIT_RATE_MIN 值不同（0.0112 vs 0.9488）但属双尺并行登记的既定设计 ✓

## 断言 7：报告诚实度 — PASS（附 P2 措辞瑕疵）

- **§③「kickoff 目标 ≥0.10 结构性不可达」属实**：我复跑 ceiling rerank-top5=**5/64=0.0781<0.10**（golden 需进 rerank top5 才可命中，final docs 恒为 rerank 全序前缀——probe ceiling note 逻辑核过），目标结构性不可达成立 ✓
- **§④-2 前任数字失真属实**：`0d20a2d` 引入的 retriever.py WIP 注释（`git show 0d20a2d:edu-agent/app/chat/retriever.py` 行 693）声称 "eval64 hit@5 0.0312→0.0781"，而其默认配置为 `RERANK_CLIFF_V2_SCORE_FLOOR=0.30`（v2a，`0d20a2d:config.py` 行 682）；我复跑 v2a_floor_0.3=**0.0625**（非 0.0781）——失真确证，接手者不复跑 probe 即采信会带错数字定稿 ✓
- **P2 瑕疵**：报告称「前任 **commit message** 数字失真」，但 `git show 0d20a2d --format=%B` 全文为 "wip(R23): 模型中断留痕——eval64 基线契约+retriever 断崖修复半成品，接手者审查后续做"，**无任何数字**；失真载体是 0d20a2d 引入的 **WIP 代码注释**，非 commit message。披露实质成立，载体表述不精确。
- 超范围加分核验 §③ 另两行：单测 12/12 ✓（断言 4）；广域回归构成 22（rn2）+7（fusionblind）+12（r23）+37（rmem1_sanitize）=78 逐文件计数核实，亲跑 83 passed（78+额外 test_memory_queue_lifecycle 5 例）✓
- 未独立复现项（不属 7 条必核，数字无矛盾、探针脚本 `edu-agent/test-reports/r23_chat_sse_probe.py` 在 commit 中）：§③ live 主链行（非流式 200/docs=5；SSE start→token×81→done）——采信度：中，留痕脚本可复跑。

---

## 新发现问题

| 级别 | 问题 | 处置建议 |
|---|---|---|
| P2 | 报告 §④-2 将 0d20a2d 的数字失真归为「commit message」，实际载体是 WIP 代码注释（commit message 无数字）。披露实质成立，仅载体表述不精确 | 不阻塞；后续报告引用留痕载体时精确到注释/message |
| — | 无 P0 / 无 P1 | — |

## 审核留痕

- 复跑产物（未 commit，工作区新增）：`edu-agent/scripts/eval/data/r23_runs/r23_cliff_probe_audit_r23.json`、`r23_cliff_probe_audit_r23_32.json`
- fuzz/对拍为一次性内联脚本，未落盘（避免工作区 stray）
- 本报告不 commit（审核者只交报告路径，留痕与否由编排者裁定）

AUDIT_VERDICT: PASS
